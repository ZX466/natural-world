"""读档编排链补全：`diagnose → materialize → fork(kind="anchor")`（M5-A11，批次 E 收官件）

A10 交了物化器的**数据面**（`anchor_package.py`：包读写 + 次序铁律 + 五判据）与
`fork.py` 的 `kind` 参数化；本模块把三步串成**一次调用**，并留出 `MaterializationHooks`
的注入缝。

## 三步链（批处理范式，与 `main.py::_drain_loads` 同构）

```text
locate_anchor → diagnose（只读、拿原因码） → materialize（次序铁律） → fork(kind="anchor")
                                                                          → register_child
```

- **diagnose 先于 materialize**：不可物化的档（老档无包 / rng 不可得 / 事件有洞）在**分叉
  之前**就被拒 ⇒ 不产生子分支行、不动父分支（返回部分包 = 禁止）。上层（`_drain_loads`）
  既有 `except Exception → load_failed` 降级体例自然接管，本模块不新增消息类型。
- **游标一致性**：包游标必须与 anchor 行逐项相符——判据交给 `fork.py`（同一处判据，不重复
  实现）；诊断层只负责把「不可物化」与「游标不符」分开报。
- **hooks 缺省 = 现行 head 分叉**（`hooks=None`）：读**当前档**的语义逐字不变。要走历史点
  读档就必须显式给 hooks（显式优于隐式：悄悄换语义比报错更坏）。

## hooks 注入缝（语义归 ws/决策层，缝归本层）

A10 的 `MaterializationHooks` 是四步的**顺序契约**，语义实现需要「快照 dict → WorldState」
这类读档反向函数——仓内**今天没有**这个函数（`snapshot_payload` 是写方向）。因此本模块：

1. 提供 `set_materialization_hooks()` / `get_materialization_hooks()` 模块级注册缝
   （与 `ws.py::set_anchor_load_hook` 同款：依赖方向 单向，上层注册、下层取用）；
2. 缺省 hooks 是 **fail-closed 桩**（四步都抛 `AnchorLoadUnavailable("hooks_unavailable")`）
   ——**不假装能展开世界态**。未注入前历史点读档必然被拒，这是诚实态而不是半成品态；
3. 回执列「待注入清单」（每步该调哪个现行 world 函数、缺哪个反向函数）。

## 四步语义的归属（供注入方对照）

- `expand_world(payload, window)`：快照 dict + 窗口事件 → 世界态 —— **ws/世界层**；
  今天**缺反向函数**（`snapshot_payload` 只写不读）。
- `apply_override(world, override)`：展开后套 agent 身份覆盖 —— **决策层**；
  缺（覆盖副本今天恒 `{}`）。
- `load_corpus(corpus)`：包内语料行值灌进**世界态对象** —— **决策层**；数据面已由
  `fork.py` 同行事务写库，本步是「喂给会话对象」。
- `restore_rng(blob)`：恢复抽签进度 —— **混沌流**（Claude 域）；`restore_rng_state`
  已在（`sim/core/rng_state.py`），缺「谁持有 registry + 抽签 cache」的暴露。
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from sim.core.persistence.anchor_package import (
    Materialization,
    MaterializationHooks,
    diagnose_anchor_materialization,
    materialize_anchor,
)
from sim.core.persistence.fork import ForkResult, fork_from_anchor
from sim.core.persistence.store import SqlEventStore

logger = structlog.get_logger(__name__)

#: hooks 未注入时的原因码（**编排层**原因码，与物化五判据分开，避免两套码混谈）。
HOOKS_UNAVAILABLE = "hooks_unavailable"


@dataclass(frozen=True)
class AnchorLocation:
    """anchor 表行的世界线定位（零世界状态内容，纯指针）。"""

    branch_id: str
    seq: int
    tick: int


class OrchestrationError(RuntimeError):
    """编排层失败（定位/换线），与 ForkError（事务层）分型。"""


class AnchorLoadUnavailable(OrchestrationError):
    """历史点读档**不可用**（fail-closed）：原因码在 :attr:`reason`。

    上层（`main.py::_drain_loads`）既有 ``except Exception → load_failed`` 降级体例接管；
    本层只负责把「为什么不可用」说清楚（诊断面与日志同源）。
    """

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason
        self.detail = detail


async def locate_anchor(
    session_factory: async_sessionmaker[AsyncSession], anchor_id: str
) -> AnchorLocation:
    """anchor 表行 → 世界线指针。

    anchor 行由 K7 落库路径写入（`(branch_id, seq)` 指针，不复制世界态）；
    tick 由事件流回查（分叉点 tick 是克隆截断判据之一）。
    """
    async with session_factory() as session:
        row = (
            await session.execute(
                text("SELECT branch_id, seq FROM player_anchors WHERE id = :aid AND protected = 0"),
                {"aid": anchor_id},
            )
        ).first()
        if row is None:
            raise OrchestrationError(f"anchor 不存在: {anchor_id!r}")
        branch_id, seq = str(row[0]), int(row[1])
        tick = (
            await session.execute(
                text("SELECT tick FROM events WHERE branch_id = :b AND seq = :s"),
                {"b": branch_id, "s": seq},
            )
        ).scalar_one_or_none()
    if tick is None:
        raise OrchestrationError(
            f"anchor {anchor_id!r} 指向的事件不存在（branch={branch_id!r}, seq={seq}）"
        )
    return AnchorLocation(branch_id=branch_id, seq=seq, tick=int(tick))


# ---------------------------------------------------------------------------
# hooks 注入缝（模块级注册；缺省 fail-closed 桩）
# ---------------------------------------------------------------------------


def _unavailable(step: str) -> Awaitable[Any]:
    async def _raise() -> Any:
        raise AnchorLoadUnavailable(
            HOOKS_UNAVAILABLE,
            f"物化钩子 `{step}` 未注入：读档需要「快照 dict → 世界态」等语义实现，"
            "属 ws/决策层（见本模块 docstring 的待注入清单）",
        )

    return _raise()


def unavailable_hooks() -> MaterializationHooks:
    """缺省 hooks：四步全部 fail-closed（**不假装能展开世界态**）。"""

    async def _expand(payload: Mapping[str, Any], window: Sequence[Mapping[str, Any]]) -> Any:
        return await _unavailable("expand_world")

    async def _override(world: Any, override: Mapping[str, Any]) -> Any:
        return await _unavailable("apply_override")

    async def _corpus(corpus: Mapping[str, Sequence[Mapping[str, Any]]]) -> Any:
        return await _unavailable("load_corpus")

    async def _rng(blob: str) -> Any:
        return await _unavailable("restore_rng")

    return MaterializationHooks(
        expand_world=_expand, apply_override=_override, load_corpus=_corpus, restore_rng=_rng
    )


_hooks_singleton: MaterializationHooks = unavailable_hooks()


def set_materialization_hooks(hooks: MaterializationHooks | None) -> None:
    """注册真实语义实现（进程级；与 `ws.py::set_anchor_load_hook` 同款注册缝）。

    传 ``None`` 复位成 fail-closed 缺省桩（测试与「撤回注入」用）。
    """
    global _hooks_singleton
    _hooks_singleton = unavailable_hooks() if hooks is None else hooks


def get_materialization_hooks() -> MaterializationHooks:
    """取当前注册的 hooks（未注入 ⇒ 缺省 fail-closed 桩）。"""
    return _hooks_singleton


# ---------------------------------------------------------------------------
# 编排链
# ---------------------------------------------------------------------------


async def orchestrate_materialized_load_anchor(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    anchor_id: str,
    flush_in_flight: Callable[[], Awaitable[None]],
    hooks: MaterializationHooks | None = None,
    vec_conn: Any = None,
    register_child: Callable[[str], None] | None = None,
    store: SqlEventStore | None = None,
    new_branch_id: str | None = None,
) -> tuple[ForkResult, Materialization]:
    """历史点读档全链：定位 → 诊断 → 物化 → 分叉 → 登记（返回 ``(fork, 物化)``）。

    Args:
        hooks: 四步语义实现；``None`` ⇒ 取模块注册的（未注册即 fail-closed 桩）。
        store: 事件库视图（诊断/物化要用 ``latest_snapshot``）；缺省按 ``session_factory``
            包一个（``SqlEventStore`` 只是工厂的薄壳，不新建引擎）。
        new_branch_id: 子分支 id（缺省 uuid4；钉子用固定值便于断言）。

    Raises:
        AnchorLoadUnavailable: 不可物化（``reason`` 来自诊断面）或 hooks 未注入。
        OrchestrationError: anchor 定位失败。
        ForkError: 事务层失败（含「包游标与分叉参数不符」，判据唯一处在 fork.py）。
    """
    active = get_materialization_hooks() if hooks is None else hooks
    event_store = SqlEventStore(session_factory) if store is None else store
    loc = await locate_anchor(session_factory, anchor_id)

    diagnosis = await diagnose_anchor_materialization(event_store, anchor_id)
    if not diagnosis.ready:
        raise AnchorLoadUnavailable(
            str(diagnosis.reason),
            f"anchor {anchor_id!r} 不可物化（快照引用 {diagnosis.snapshot_seq}）",
        )

    materialization = await materialize_anchor(event_store, anchor_id=anchor_id, hooks=active)
    result = await fork_from_anchor(
        session_factory,
        parent_branch_id=loc.branch_id,
        fork_seq=loc.seq,
        fork_tick=loc.tick,
        preflush=flush_in_flight,
        new_branch_id=new_branch_id or uuid.uuid4().hex,
        vec_conn=vec_conn,
        kind="anchor",
        package=materialization,
    )
    if register_child is not None:
        register_child(result.new_branch_id)
    logger.info(
        "fork.load_anchor_materialized",
        anchor_id=anchor_id,
        new_branch_id=result.new_branch_id,
        parent_branch_id=loc.branch_id,
        forked_from_seq=loc.seq,
        replay_from_seq=materialization.replay_from_seq,
        cloned_rows=dict(result.cloned_rows),
        vec_pending=result.vec_pending,
    )
    return result, materialization


async def orchestrate_load_anchor(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    anchor_id: str,
    flush_in_flight: Callable[[], Awaitable[None]],
    vec_conn: Any = None,
    register_child: Callable[[str], None] | None = None,
    hooks: MaterializationHooks | None = None,
) -> ForkResult:
    """一次读档调用：定位 → preflush → fork → 登记子分支。

    Args:
        session_factory: 异步 session 工厂（与 fork_from_anchor 同源）。
        anchor_id: 玩家档 id（不透明串）。
        flush_in_flight: **必填** P1 动作——冲掉父分支 in-flight 批次使投影追平
            （driver 侧=把当前事件批 flush 落库；漏传即不可分叉）。
        vec_conn: 同 fork_from_anchor（不给 → vec_pending，召回降级不泄漏）。
        register_child: 子分支 id 登记回调（WS 侧挂 register_anchor_id + 新分支
            可载性；编排层不 import 网关模块——依赖方向网关→编排单向）。
        hooks: **给了** ⇒ 走历史点物化链（`kind="anchor"`，语义见
            :func:`orchestrate_materialized_load_anchor`）；**不给** ⇒ 现行 head 分叉
            （读当前档，行为逐字不变）。

    Returns:
        ForkResult（克隆事实清单）。

    Raises:
        OrchestrationError: 定位失败。
        AnchorLoadUnavailable: 物化链上的 fail-closed（不可物化 / hooks 未注入）。
        ForkError: 事务层失败（整批回滚，无半写）。
    """
    if hooks is not None:
        result, _materialization = await orchestrate_materialized_load_anchor(
            session_factory,
            anchor_id=anchor_id,
            flush_in_flight=flush_in_flight,
            hooks=hooks,
            vec_conn=vec_conn,
            register_child=register_child,
        )
        return result

    loc = await locate_anchor(session_factory, anchor_id)
    result = await fork_from_anchor(
        session_factory,
        parent_branch_id=loc.branch_id,
        fork_seq=loc.seq,
        fork_tick=loc.tick,
        preflush=flush_in_flight,
        new_branch_id=uuid.uuid4().hex,
        vec_conn=vec_conn,
    )
    if register_child is not None:
        register_child(result.new_branch_id)
    logger.info(
        "fork.load_anchor",
        anchor_id=anchor_id,
        new_branch_id=result.new_branch_id,
        parent_branch_id=loc.branch_id,
        forked_from_seq=loc.seq,
        cloned_rows=dict(result.cloned_rows),
        vec_pending=result.vec_pending,
    )
    return result
