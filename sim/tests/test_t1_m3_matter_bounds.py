"""T1 RED 钉子 ②— C2 MatterPayload 域约束缝（M3-S1，docs/security/m3-preplan.md §2/C2）。

**RED 状态（本文件按 M3-S1 任务书零实现提交，预期失败即验收）**：

- m3-plan.md 批次 C4（opencode）：`Field(ge/le) + allow_inf_nan=False` 实现后转绿。
- 现状（2026-09-23 实测留痕）：
  - `MatterPayload` 五个数值字段（x/y/amount/durability/decay_rate）无任何域约束；
  - `MatterPayload(matter_id='w', durability=float('nan'))` → 通过；
  - `matter_event(...)` 工厂 → `model_dump(mode='json')` 落出 `nan` 字面量；
  - `NpcStore.flush_tick([nan 事件])` → **整链通过**，matter_state.integrity 被写。
  （integrity 行为：NaN 插入路径走 `1.0 if durability < 0` 兜底 = 1.0；
    Infinity 更险——`max(0,min(1,inf))=1.0` 伪造满耐久，全部静默接受。）

为什么这是 T1 边界缝（m3-preplan §2 C2）：

- Python `json.loads` 接受 NaN/Infinity 字面量；`ws.receive_json` 与事件落库
  均不设防 → 一条伪造 WS 帧/越权调用即可把 NaN/±inf 送进 matter_state；
- `np.clip(NaN)=NaN`（结算路径）与 `max(0,min(1,inf))=1`（投影路径）都会把
  非法值固化进「事件重放逐位重建」的世界状态，且 append-only 无法删行修复
  （memory-scan.md 同款不可修复性：只有治理列，没有改 content）；
- M4 建造玩法开放客户端/LLM 输入面后，这是 §16 不变量 6（材料守恒）与
  「历史不可销毁」的直接攻击面。

契约锁定（C4 实现的验收形）：

| 字段 | 契约 | 依据 |
|---|---|---|
| amount | 有限数；∈[-1,1]（单 tick 变化量上限，账本 clip 同语义） | matter.py clip(0,1) |
| durability | 有限数；∈[-1,1]（-1=不变更哨兵；≥0 为 0..1） | MatterPayload docstring |
| decay_rate | 有限数；∈[-1,1]（-1=不变更哨兵，≥0 静态率） | §17.2 方案 A |
| x / y | 整数 ∈[-1,4096)（-1=哨兵；上界=寻路界，gate.py 同源） | revalidate out_of_bounds |
| note | 保持 str（字面治理走 C7 服务端生成 only，不在本钉子） | m3-preplan C7 |

失败指纹（实现前运行，全部 RED）：
- TestMatterPayloadBounds 四组参数化用例 → ValidationError 未抛（今天全放行）；
- test_factory_rejects_nan_durability / test_factory_rejects_infinity_amount
  → 同上；
- test_store_row_rejects_nan_durability
  → `validate_store_row` 对 MATTER_* 的 NaN payload 现在不抛（实测留痕：
    `validate_store_row: NaN ACCEPTED`）；
- test_flush_tick_rejects_nan_end_to_end
  → `NpcStore.flush_tick` 全链通过并写库（实测留痕：
    `NaN damage ACCEPTED; integrity now = 1.0`）。

**M3-D1 钉子修正留痕（opencode，2026-09-23）**：原 TestMatterEndToEndBounds 把
`matter_event(...)` 写在 `pytest.raises(EventValidationError)` **之外**，与
`test_factory_rejects_nan_durability`（同调用要求抛 ValidationError）**自相矛盾**——
任何实现都无法同时满足。已按 Claude 裁决将工厂调用移入 `with` 并放宽为
`(EventValidationError, ValidationError)`（工厂/store 任一层拒绝即算通过，defense in depth）。
实现后 C2 全绿 29/29。

实现归属：opencode C4（批次 C）。
CI：test_t1_m3_* 前缀随 `-m "not bench"` 全量跑。
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from sim.core.events import EventKind, MatterPayload, matter_event
from sim.core.persistence.database import init_database
from sim.core.persistence.event_validation import EventValidationError, validate_store_row
from sim.core.persistence.npc_store import NpcStore
from sim.core.persistence.store import SqlEventStore

# ---------------------------------------------------------------------------
# 钉子 ②a：MatterPayload 模型域约束（pydantic 层，C4 直接落点）
# ---------------------------------------------------------------------------


@pytest.mark.t1
class TestMatterPayloadBounds:
    """C2 契约：数值域外/非有限值一律 ValidationError（RED：今天全放行）。"""

    @pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
    def test_durability_rejects_non_finite(self, bad: float) -> None:
        with pytest.raises(ValidationError):
            MatterPayload(matter_id="w", durability=bad)

    @pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
    def test_amount_rejects_non_finite(self, bad: float) -> None:
        with pytest.raises(ValidationError):
            MatterPayload(matter_id="w", amount=bad)

    @pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
    def test_decay_rate_rejects_non_finite(self, bad: float) -> None:
        with pytest.raises(ValidationError):
            MatterPayload(matter_id="w", decay_rate=bad)

    @pytest.mark.parametrize(
        ("field", "bad"),
        [
            ("durability", 1.5),  # >1 越界（伪造满耐久）
            ("durability", -1.5),  # <-1（哨兵-1 之外负值）
            ("amount", 1.5),
            ("amount", -1.5),
            ("decay_rate", 1.5),  # >1 静态率无意义
            ("decay_rate", -1.5),  # <哨兵
            ("x", 4096),  # 寻路上界（gate.py out_of_bounds 同源）
            ("y", 4096),
            ("x", -2),  # -1=未定位哨兵，-2 越界
            ("y", -2),
        ],
    )
    def test_fields_reject_out_of_range(self, field: str, bad: float) -> None:
        kwargs: dict[str, object] = {field: bad}
        with pytest.raises(ValidationError):
            MatterPayload(matter_id="w", **kwargs)  # type: ignore[arg-type]

    def test_sentinels_and_valid_values_still_pass(self) -> None:
        """正向控制：哨兵与合法值不得误伤（防线不过严）。"""
        p = MatterPayload(matter_id="w", x=-1, y=-1, amount=0.0, durability=-1.0, decay_rate=-1.0)
        assert p.durability == -1.0
        q = MatterPayload(matter_id="w", x=100, y=200, amount=-0.5, durability=0.7, decay_rate=0.01)
        assert q.durability == 0.7 and q.decay_rate == 0.01


# ---------------------------------------------------------------------------
# 钉子 ②b：工厂与落库链（C4 契约对事件层的传导）
# ---------------------------------------------------------------------------


@pytest.mark.t1
class TestMatterEventFactoryBounds:
    """matter_event 工厂必须把 MatterPayload 的域约束传导到事件构造。"""

    def test_factory_rejects_nan_durability(self) -> None:
        with pytest.raises(ValidationError):
            matter_event(
                tick=1, kind=EventKind.MATTER_BUILD, matter_id="w", durability=float("nan")
            )

    def test_factory_rejects_infinity_amount(self) -> None:
        with pytest.raises(ValidationError):
            matter_event(tick=1, kind=EventKind.MATTER_DAMAGE, matter_id="w", amount=float("inf"))

    def test_factory_valid_still_passes(self) -> None:
        ev = matter_event(tick=1, kind=EventKind.MATTER_BUILD, matter_id="w", durability=0.5)
        assert ev.payload["durability"] == 0.5


@pytest.mark.t1
class TestMatterRowValidationBounds:
    """store 行校验（validate_store_row）必须拒绝非有限/越界 MATTER_* payload。

    实测留痕（RED 依据）：今天 `validate_store_row` 对 NaN durability 不抛。
    """

    @pytest.mark.parametrize("bad", [float("nan"), float("inf")])
    def test_store_row_rejects_non_finite_durability(self, bad: float) -> None:
        row = {
            "tick": 1,
            "event_type": "matter.build",
            "payload": {"matter_id": "w", "durability": bad, "amount": 0.0},
        }
        with pytest.raises(EventValidationError):
            validate_store_row(row)

    def test_store_row_rejects_out_of_range_decay_rate(self) -> None:
        row = {
            "tick": 1,
            "event_type": "matter.decay",
            "payload": {"matter_id": "w", "decay_rate": 99.0},
        }
        with pytest.raises(EventValidationError):
            validate_store_row(row)


@pytest.mark.t1
class TestMatterEndToEndBounds:
    """端到端：flush_tick 全链（factory → flush_rows → append 校验 → 投影）拒非有限值。

    实测留痕（RED 依据）：今天 NaN/Infinity durability 一路写进 matter_state。
    """

    @pytest.fixture
    async def engine(self):
        eng = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
        await init_database(eng)
        yield eng
        await eng.dispose()

    @pytest.fixture
    def store(self, engine):
        sf = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        return SqlEventStore(sf)

    async def test_flush_tick_rejects_nan_end_to_end(self, store) -> None:
        ns = NpcStore(store)
        # M3-D1 钉子修正（codex 原稿：工厂调用在 with 之外 → 与
        # test_factory_rejects_nan_durability 自相矛盾，无法同时满足）。
        # 语义对齐「链上任一层拒绝非有限值」：工厂层抛 pydantic ValidationError、
        # store 层抛 EventValidationError，二者皆算通过（defense in depth）。
        with pytest.raises((EventValidationError, ValidationError)):
            ev = matter_event(
                tick=1,
                kind=EventKind.MATTER_BUILD,
                matter_id="wall",
                amount=0.0,
                durability=float("nan"),
            )
            await ns.flush_tick([ev])

    async def test_flush_tick_rejects_infinity_update(self, store) -> None:
        """已存在行上的 Infinity durability（update 路径）同样拒绝。"""
        ns = NpcStore(store)
        ok = matter_event(
            tick=1, kind=EventKind.MATTER_BUILD, matter_id="wall", amount=0.0, durability=0.5
        )
        await ns.flush_tick([ok])
        with pytest.raises((EventValidationError, ValidationError)):
            bad = matter_event(
                tick=2,
                kind=EventKind.MATTER_BUILD,
                matter_id="wall",
                amount=0.0,
                durability=float("inf"),
            )
            await ns.flush_tick([bad])

    async def test_valid_build_still_persists(self, store) -> None:
        """正向控制：合法建造不受影响。"""
        ns = NpcStore(store)
        ev = matter_event(
            tick=1, kind=EventKind.MATTER_BUILD, matter_id="hut", amount=0.0, durability=0.8
        )
        await ns.flush_tick([ev])
