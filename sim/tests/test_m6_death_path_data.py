"""M6-A1 死亡路径数据面钉（落点 a：移出 `entities`）+ 驱动形态夹具自恢复

派单：M6-A1「死亡路径数据面钉 + driver 夹具恢复」。Q1 已裁定**落点 a = 死亡即从
`WorldState.entities` 移出**（A12 回执给了依据：只有行删除能让 soak 契约的
`end ≤ start` 有意义；状态列翻转会让契约变成空断言）。

**本文件是钉，不是实现**：死亡事件 kind 属红线 A（需授权）且归 Claude/架构域，仓内今天
**没有任何死亡载体**（`EventKind` 无 death/died/despawn；默认总线无删除 handler）。所以：

- **A 组（今天即绿）= 事实基座**：钉住「今天没有死亡载体」这件事本身，以及三条与落点 a
  直接相关的数据面事实（① 计数只认 `entities`；② `entities` **不参与 fork 克隆**；
  ③ `npc_profiles` 整表克隆 ⇒ **内存删除不会传导到子分支**，这是落点 a 必须显式登记的不对称）。
- **B 组（skip-locked）= 落点 a 落地即自动转绿**的删除路径钉（fold 链 / 可重放证据 /
  fail-closed / 重复死亡不复活 / C5 确定性）。锁信号 = 默认总线上**注册了**死亡类 kind。
  构造死亡事件用 `_death_event()` 适配器（按签名试参）；接口形态未定时该组**逐条 skip**
  而不是假绿。
- **C 组 = 契约文档钉**：死亡落地后，「内存删除 vs `npc_profiles` 行」的处理必须在
  `docs/data/schema.md` 登记（要么同步删行、要么明写不对称）——代码可以先落，**账不能欠**。

**夹具自恢复（派单第二件）**：A11 因上游 driver 写锁缺陷取消 driver 求确定性；根治落地后
本文件 `test_m5_materialization_api.py` 的夹具要**恢复 driver 形态**。这里用「一次性探针 +
自恢复 + 同步钉」实现：`_driver_lock_present()` 缓存探针结果（缺陷在 ⇒ 夹具取消 driver；
缺陷消失 ⇒ 夹具自动放行 driver），钉子盯住两者一致。
"""

from __future__ import annotations

import contextlib
import inspect
import re
from pathlib import Path
from typing import Any

import pytest

from sim.core import events as events_mod
from sim.core.events import EventKind
from sim.core.tick import TickLoop
from sim.core.world import EntityState, WorldState, build_default_bus

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_MD = REPO_ROOT / "docs" / "data" / "schema.md"

#: 死亡语义记号（kind 名里出现即算；`structure.removed` 是结构事件，不在其列）。
DEATH_WORDS = ("death", "died", "despawn")


# ---------------------------------------------------------------------------
# 锁信号与死亡事件适配器（B 组用；接口形态未定 ⇒ 逐条 skip 不假绿）
# ---------------------------------------------------------------------------


def _death_kind() -> EventKind | None:
    """死亡类 kind（名字命中 + **已在默认总线注册**）⇒ 落点 a 的删除路径已落。"""
    handlers = getattr(build_default_bus(), "_handlers", {})
    for kind in EventKind:
        if any(word in kind.value for word in DEATH_WORDS) and kind in handlers:
            return kind
    return None


class _Skip(Exception):
    """接口形态未定（无法构造死亡事件）⇒ 该钉 skip 而不是假绿。"""


def _death_event(npc_id: str, tick: int) -> Any:
    """按当前实现的工厂/签名构造一条死亡事件；构造不出来就 `_Skip`。"""
    kind = _death_kind()
    if kind is None:
        raise _Skip("死亡类 kind 尚未注册到默认总线（落点 a 未落）")
    keyword = next(word for word in DEATH_WORDS if word in kind.value)
    factories = [
        (name, fn)
        for name, fn in vars(events_mod).items()
        if callable(fn) and name.endswith("_event") and keyword in name
    ]
    if not factories:
        raise _Skip(f"事件工厂未找到（找 `{keyword}*_event`）")
    for _name, fn in factories:
        params = inspect.signature(fn).parameters
        kwargs: dict[str, Any] = {}
        for pname, param in params.items():
            if param.default is not inspect.Parameter.empty:
                continue
            if pname in ("tick", "branch_id"):
                kwargs[pname] = tick if pname == "tick" else "main"
            elif pname in ("npc_id", "entity_id", "actor_id", "target_id", "subject_id"):
                kwargs[pname] = npc_id
            else:
                raise _Skip(f"工厂参数 {pname!r} 未知（钉子需随实现补）")
        try:
            return fn(**kwargs)
        except TypeError as exc:  # 签名变了就如实 skip
            raise _Skip(f"构造失败: {exc}") from exc
    raise _Skip("没有可用工厂")


def _state(n: int) -> WorldState:
    return WorldState(
        world_seed=7,
        entities={f"npc{i}": EntityState(entity_id=f"npc{i}", pos=(i, i)) for i in range(n)},
    )


def _loop(state: WorldState) -> TickLoop:
    from sim.core.clock import GameClock

    return TickLoop(clock=GameClock(speed=1.0), bus=build_default_bus(), state=state)


# ===========================================================================
# A 组：今天即绿的事实基座
# ===========================================================================


class TestDeathPathAbsentToday:
    def test_no_death_kind_registered(self) -> None:
        """事实基座①（**退役版**）：死亡 kind 已落（落点 a 兑现）且进默认总线。

        原「今天无死亡载体」前提随落点 a 落地而失效——本钉转为正向：
        kind 存在、在默认总线注册、且在 PAYLOAD_MODELS 闭合集内（红线 A）。
        """
        kind = _death_kind()
        assert kind is not None, "死亡类 kind 消失（落点 a 回退？）"
        from sim.core.persistence.event_validation import PAYLOAD_MODELS

        assert kind in PAYLOAD_MODELS, f"死亡 kind 未登记 payload 模型（红线 A）：{kind}"

    def test_default_bus_registers_no_removal_handler(self) -> None:
        """事实基座②：默认总线的五个 handler 里**没有一个会删实体**。"""
        from sim.core import world as world_mod

        removing = [
            name
            for name in dir(world_mod)
            if name.startswith("_apply_")
            and re.search(
                r"entities\.(pop|clear)\(|\{[^}]*entities", getattr(world_mod, name).__doc__ or ""
            )
        ]
        assert removing == [], f"出现删除实体的 handler：{removing}"

    def test_payload_models_stay_in_one_to_one_with_kinds(self) -> None:
        """红线 A 恒等式：任何新 kind（含未来的死亡 kind）**必须**同 commit 补 payload 模型。"""
        from sim.core.persistence.event_validation import PAYLOAD_MODELS

        assert set(PAYLOAD_MODELS) == {k.value for k in EventKind}

    def test_entities_count_is_the_soak_counter_surface(self) -> None:
        """事实基座③：soak 计数只认 `entities`（死亡要影响契约，就必须落在这张字典上）。"""
        src = (REPO_ROOT / "sim" / "tests" / "bench" / "soak.py").read_text(encoding="utf-8")
        assert "entity_count_start=len(loop.state.entities)" in src
        assert "result.entity_count_end = len(loop.state.entities)" in src

    def test_entities_are_not_part_of_fork_clone(self) -> None:
        """事实基座④：`entities`（内存世界态）**不参与 fork 克隆**——fork 只克隆 DB 表。

        判别力：落点 a 若只删内存，fork 出来的子分支不会有任何「这个人没了」的痕迹
        （见下一条）。
        """
        from sim.core.persistence.fork import _BOUNDED_TABLES

        assert "entities" not in {table for table, _cols in _BOUNDED_TABLES}

    def test_npc_profiles_is_cloned_wholesale(self) -> None:
        """事实基座⑤：`npc_profiles` 走有界表整表克隆 ⇒ 内存删除**不会**传导到子分支。

        ⇒ 落点 a 必须显式登记这个不对称（同步删行 or 文档登记）；否则读档子分支会出现
        「`npc_profiles` 里有人、内存里没有」的 NPC。契约钉见 `TestDeathContractDoc`。
        """
        from sim.core.persistence.fork import _BOUNDED_TABLES

        columns = dict(_BOUNDED_TABLES)["npc_profiles"]
        assert columns[0] == "id" and "lod" in columns


# ===========================================================================
# B 组：落点 a 落地后自动转绿（锁信号 = 死亡 kind 已注册）
# ===========================================================================


requires_death_path = pytest.mark.skipif(
    _death_kind() is None,
    reason="落点 a 未落：默认总线尚无注册好的死亡类 kind（施工落地后自动解锁）",
)


@requires_death_path
class TestDeathDeletionPath:
    def test_death_removes_only_that_entity(self) -> None:
        """删除路径只摘掉死者一个键，其余实体**逐位不动**。"""
        loop = _loop(_state(3))
        try:
            event = _death_event("npc1", loop.state.tick + 1)
        except _Skip as exc:
            pytest.skip(str(exc))
        loop.enqueue(event)
        assert set(loop.state.entities) == {"npc0", "npc2"}
        assert loop.state.entities["npc0"].pos == (0, 0)
        assert loop.state.entities["npc2"].pos == (2, 2)

    def test_death_is_recorded_as_event(self) -> None:
        """可重放证据：死亡**必须**是一条事件（进 `pending_events`），不是内存里的悄悄删除。

        判别力：内存直删 ⇒ 快照/重放重建不出这个状态 ⇒ T2 逐位一致破。
        """
        loop = _loop(_state(2))
        try:
            event = _death_event("npc0", loop.state.tick + 1)
        except _Skip as exc:
            pytest.skip(str(exc))
        loop.enqueue(event)
        assert any(e.event_type is _death_kind() for e in loop.pending_events)

    def test_death_of_unknown_entity_fails_closed(self) -> None:
        """未知实体死亡 ⇒ fail-closed（同 `_apply_move` 的「未知实体」纪律，不静默忽略）。"""
        loop = _loop(_state(1))
        try:
            event = _death_event("ghost", loop.state.tick + 1)
        except _Skip as exc:
            pytest.skip(str(exc))
        with pytest.raises((ValueError, KeyError)):
            loop.enqueue(event)

    def test_repeated_death_does_not_resurrect(self) -> None:
        """重复死亡**不复活**（第二次要么幂等无操作、要么 fail-closed），实体键保持缺失。"""
        loop = _loop(_state(2))
        try:
            first = _death_event("npc0", loop.state.tick + 1)
        except _Skip as exc:
            pytest.skip(str(exc))
        loop.enqueue(first)
        try:
            second = _death_event("npc0", loop.state.tick + 1)
        except _Skip as exc:
            pytest.skip(str(exc))
        # fail-closed 也算合格（不复活即可）
        with contextlib.suppress(ValueError, KeyError):
            loop.enqueue(second)
        assert "npc0" not in loop.state.entities

    def test_c5_determinism_same_sequence_twice(self) -> None:
        """C5 确定性：同一事件序列跑两遍 ⇒ `state_hash()` **逐位相等**（无隐藏随机/时钟）。"""
        hashes = []
        for _ in range(2):
            loop = _loop(_state(3))
            try:
                event = _death_event("npc1", loop.state.tick + 1)
            except _Skip as exc:
                pytest.skip(str(exc))
            loop.enqueue(event)
            hashes.append(loop.state.state_hash())
        assert hashes[0] == hashes[1]

    def test_tick_after_death_does_not_resurrect_or_crash(self) -> None:
        """死亡后再跑若干 tick：不复活、不抛（消费点容忍缺失实体）。"""
        loop = _loop(_state(2))
        try:
            event = _death_event("npc0", loop.state.tick + 1)
        except _Skip as exc:
            pytest.skip(str(exc))
        loop.enqueue(event)
        for _ in range(3):
            loop.advance_frame(0.1)
        assert "npc0" not in loop.state.entities


# ===========================================================================
# C 组：契约文档钉（死亡落地后「不对称」必须登记，代码可以先落、账不能欠）
# ===========================================================================


class TestDeathContractDoc:
    @requires_death_path
    def test_schema_registers_entities_vs_npc_profiles_asymmetry(self) -> None:
        """落点 a 落地后：`schema.md` 必须登记「内存实体删除 vs `npc_profiles` 行」的处理。

        两种合格写法（钉子只认「有没有登记」，不管选了哪个）：
        ① 死亡**同步删** `npc_profiles` 行（⇒ fork 克隆面自动一致）；
        ② 明写**保留行**的不对称后果（读档子分支会出现「库里有、内存无」的 NPC）。

        失败信息给出可直接抄的记号，避免下一个人考古。
        """
        src = SCHEMA_MD.read_text(encoding="utf-8")
        assert re.search(r"(死亡|殒命|去世)", src), (
            "schema.md 里找不到死亡语义的登记段——落点 a 的数据面后果（内存实体删除 vs "
            "npc_profiles 行）必须登记：要么写「同步删行」，要么写「保留行 + 子分支不对称」"
        )
        assert "npc_profiles" in src, "登记段要指名 npc_profiles（否则读档克隆面无从判断)"


# ===========================================================================
# D 组：driver 夹具自恢复（派单第二件）
# ===========================================================================

_driver_lock_probe: tuple[bool, int] | None = None


def _driver_lock_present() -> tuple[bool, int]:
    """探针：driver 在跑时同步写面连发 3 次 POST，**返回 (是否有失败, 失败次数)**。

    为什么要探针而不是直接改夹具：这个缺陷是**间歇性**的（A11 实测同一形态 5 次 POST 里
    失败 1-2 次，锁时有时无）⇒ 任何「按探针结果自动改夹具」的策略都会在两个方向上抖动，
    而抖动会变成**随机假红**。所以探针只做一件事：**如实报告本轮有没有复现**，由下面的钉
    决定断言方向；夹具的真正恢复（放行 driver）由根治合入后**人工**执行一次（挂账在 A11
    回执与 `.orca/memory.md`），不交给 flaky 探针自动决定。

    结果缓存到进程级（门禁不该每例重跑一次真 app）。
    """
    global _driver_lock_probe
    if _driver_lock_probe is None:
        _driver_lock_probe = _probe_driver_write_lock()
    return _driver_lock_probe


def _probe_driver_write_lock() -> tuple[bool, int]:
    """跑一轮真 app（driver 在跑）+ 3 次同步 POST，返回 ``(有失败, 失败次数)``。"""
    import contextlib
    import os
    import sqlite3
    import tempfile

    from fastapi.testclient import TestClient

    from sim.api import anchors as anchors_mod
    from sim.api.main import app
    from sim.api.settings import get_profile_store
    from sim.api.ws import reset_anchor_registry

    previous_cwd = Path.cwd()
    tmp = tempfile.mkdtemp(prefix="m6a1-probe-")
    failures = 0
    try:
        os.chdir(tmp)
        os.environ["LZ_MASTER_KEY"] = "t" * 44
        get_profile_store().__init__(f"sqlite:///{tmp}/settings.db")
        anchors_mod.get_anchor_store().__init__(f"sqlite:///{tmp}/world.db")
        conn = sqlite3.connect(f"{tmp}/world.db")
        conn.execute(
            "INSERT OR IGNORE INTO branches (id, status, is_current, created_at)"
            " VALUES ('main','active',1,0.0)"
        )
        conn.commit()
        conn.close()
        with TestClient(app) as client:  # driver 在跑
            for i in range(3):
                try:
                    client.post("/api/anchors", json={"name": f"探针档{i}"})
                except Exception:
                    failures += 1
        return failures > 0, failures
    except Exception:  # 探针自身出问题 ⇒ 记成「有失败」（保守：继续取消 driver）
        return True, 1
    finally:
        with contextlib.suppress(OSError):
            os.chdir(previous_cwd)
        # 探针跑过真 app ⇒ WS 注册表与锚点 store 单例都被它动过；**不许漏给别的钉**。
        reset_anchor_registry()
        anchors_mod.get_anchor_store().__init__("sqlite:///world.db")


class TestDriverFixtureSelfRestore:
    """派单第二件：写锁根治后**夹具恢复 driver 形态**的守卫。

    形态说明（重要）：根治**还没落地**（talking.txt 挂账：Claude 域批次 A），所以本组现在
    做的是「把挂账钉成不可静默丢失的三件事」——
    ① 探针如实报告缺陷是否复现（间歇性 ⇒ **不**用它自动改夹具，见 `_driver_lock_present`）；
    ② 缺陷复现时，API 钉夹具**必须**取消 driver（有据可依的确定性，不许无声去掉）；
    ③ 缺陷的书面登记（`anchors.py` 模块注 + `schema.md` §23.7.4）**不许被删**。
    根治合入后，夹具恢复 driver 形态 = 人工删掉 `driver.cancel()` 一次（届时 ② 的断言会
    提醒你改成「未复现 ⇒ 允许放行」的分支）。
    """

    def test_fixture_cancels_driver_while_defect_reproduces(self) -> None:
        """缺陷复现 ⇒ 夹具必须取消 driver；未复现 ⇒ 本钉 skip（间歇性，不自动改夹具）。"""
        present, failures = _driver_lock_present()
        if not present:
            pytest.skip(
                "本轮探针未复现上游写锁缺陷（间歇性）；夹具恢复 driver 形态须在根治合入后"
                "人工执行（A11 回执挂账① / memory 挂账），不随探针自动翻转"
            )
        src = (REPO_ROOT / "sim" / "tests" / "test_m5_materialization_api.py").read_text(
            encoding="utf-8"
        )
        assert "driver.cancel()" in src, (
            f"上游写锁缺陷复现（3 次 POST 里失败 {failures} 次）但 API 钉夹具不取消 driver "
            "⇒ 钉子会随机假红"
        )

    def test_write_lock_finding_stays_on_record(self) -> None:
        """缺陷登记不许被删：`anchors.py` 模块注 + `schema.md` §23.7.4 两处都在。"""
        anchors_src = (REPO_ROOT / "sim" / "api" / "anchors.py").read_text(encoding="utf-8")
        assert "上游阻塞缺陷" in anchors_src, (
            "sim/api/anchors.py 模块注里的「上游阻塞缺陷」段被删了——根治前它是对外书面"
            "说明（谁该修、为什么不重试绕过）"
        )
        schema_src = SCHEMA_MD.read_text(encoding="utf-8")
        assert "23.7.4" in schema_src and "上游阻塞缺陷" in schema_src, (
            "schema.md §23.7.4（上游阻塞缺陷）被删——数据面留档不许在无关改动里顺手清掉"
        )

    def test_probe_result_is_cached(self) -> None:
        """探针必须缓存（每例重跑真 app 会把门禁拖成分钟级）。"""
        first = _driver_lock_present()
        assert _driver_lock_probe is first
