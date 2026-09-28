"""读档 = 分叉的 driver 编排（M5 批次 B 行为面收口，裁 25-B②/裁 26-A⑥）。

持久层 `fork_from_anchor`（opencode D3-b）给出事务与克隆；本模块是**编排缝**：
把「定位 anchor → preflush → fork → 换世界线 → 注册新 branch」串成一次调用，
供 `_ANCHOR_LOAD_HOOK` 生产注册方与未来 HTTP 读档路由共用。

职责边界（§12 + fork.py 模块注）：
- 定位：anchor → `(parent_branch_id, fork_seq, fork_tick)`（当前由 anchor 表行给出；
  anchor 落库路径 K7 已写 `(branch_id, seq)`——tick 由事件流回查）；
- preflush：冲掉父分支 in-flight 批次（P1 必填动作）——driver 的 flush 是 on_flush
  回调，这里直接 await 它（drain 语义见 run_world_driver 注）；
- fork：调 `fork_from_anchor`（事务+克隆+vec 字节拷贝）；
- 换线：TickLoop 换 `branch_id` 视角（世界态是投影，读档后 world.db 行即真相）；
- 登记新 branch 的 anchor 可载性（后续读档链）。

**分叉点只支持父分支头部**（fail-closed，fork.py 模块注）：历史点分叉需要裁 7 的
`*.written` 事件或 anchor 世界态物化（M5 均未落）——本编排不做近似重置。
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from sim.core.persistence.fork import ForkResult, fork_from_anchor

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class AnchorLocation:
    """anchor 表行的世界线定位（零世界状态内容，纯指针）。"""

    branch_id: str
    seq: int
    tick: int


class OrchestrationError(RuntimeError):
    """编排层失败（定位/换线），与 ForkError（事务层）分型。"""


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
                text(
                    "SELECT branch_id, seq FROM player_anchors WHERE id = :aid AND protected = 0"
                ),
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


async def orchestrate_load_anchor(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    anchor_id: str,
    flush_in_flight: Callable[[], Awaitable[None]],
    vec_conn: Any = None,
    register_child: Callable[[str], None] | None = None,
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

    Returns:
        ForkResult（克隆事实清单）。

    Raises:
        OrchestrationError: 定位失败。
        ForkError: 事务层失败（整批回滚，无半写）。
    """
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
