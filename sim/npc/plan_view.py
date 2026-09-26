"""plan 状态传播最小账本（M5-K7；判据 docs/arch/m4-plan.md §6 裁 14-3）。

裁 14-3 原文：**计划看板归属：整块落前端域**——三形态中计划看板数据源=PlanSlice/
Intent 流，渲染归前端；**后端只保证 plan 状态进 state_delta**（kilo 协议面已就绪）。

本模块是「后端保证 plan 状态进 state_delta」的最小落点：进程内
`{entity_id: 当前计划文本}` 账本。**不是**真实计划状态机——M4 真实执行器
（intent → plan → 回填）尚未接 WS，由它显式声明写入；本模块只做传播契约
（谁写、写什么形状、按 rtoken 出）。

纪律：
- 内部键用 entity_id（等于账本的私有世界真相）；出 WS 前一律转 rtoken
  （出戏边界：禁 entity_id 进载荷，见 ws.py `_rtoken`）。
- 空串 = 明确无计划（前端收起看板）；None = 从没报过（不发该项）。两种状态
  不可合并——合并会让「首次出现」与「被清空」在协议面同形。
- 模块级单例（同 ws.py `_ANCHOR_IDS` 模式）：分发表是同步纯函数，不能 await
  异步 DB；npc 域执行器与 WS 分发表共享同一账本，靠 reset_plan_registry()
  在测试中清零。
"""

from __future__ import annotations


class PlanDeltaStore:
    """进程内 plan 账本（不可变值语义：写即覆盖，无历史）。"""

    def __init__(self) -> None:
        self._plans: dict[str, str] = {}
        # 上一次广播出去的内容（增量过滤基准）。None=尚未广播过。
        self._broadcast: dict[str, str] | None = None

    def set_plan(self, entity_id: str, plan_text: str) -> None:
        """登记/覆盖某实体的当前计划（空串=明确无计划）。"""
        if not isinstance(plan_text, str):
            msg = f"plan_text must be str, got {type(plan_text).__name__}"
            raise TypeError(msg)
        if not entity_id or not isinstance(entity_id, str):
            msg = "entity_id must be a non-empty str"
            raise ValueError(msg)
        self._plans[entity_id] = plan_text

    def plan_of(self, entity_id: str) -> str | None:
        """当前计划文本；None=该实体从没报过计划。"""
        return self._plans.get(entity_id)

    def clear_plan(self, entity_id: str) -> None:
        """注销该实体的计划（不存在时静默——注销幂等）。"""
        self._plans.pop(entity_id, None)

    def entries(self) -> dict[str, str]:
        """全量账本快照（调用方不得原地改）。"""
        return dict(self._plans)

    def drain_changes(self) -> list[dict[str, str]]:
        """自上次调用以来内容有变化的实体 [{entity_id, plan}]。

        增量过滤：内容不变（含空串对空串）的项不再重复广播——协议面
        state_delta 是增量语义，无变化不该产生流量。
        """
        current = dict(self._plans)
        if self._broadcast is None:
            changed = [{"entity_id": eid, "plan": plan} for eid, plan in current.items()]
        else:
            changed = [
                {"entity_id": eid, "plan": plan}
                for eid, plan in current.items()
                if self._broadcast.get(eid) != plan
            ]
        self._broadcast = current
        return sorted(changed, key=lambda item: item["entity_id"])

    def mark_broadcast(self) -> None:
        """把全量账本标记为已广播（EXTEND 模式下由 WS 驱动调用）。"""
        self._broadcast = dict(self._plans)


#: 模块级单例（npc 域执行器与 ws.py 共享；测试用 reset_plan_registry 清零）。
_REGISTRY = PlanDeltaStore()


def set_plan(entity_id: str, plan_text: str) -> None:
    """模块级登记入口（M4 执行器写入点）。"""
    _REGISTRY.set_plan(entity_id, plan_text)


def plan_of(entity_id: str) -> str | None:
    """模块级查询入口。"""
    return _REGISTRY.plan_of(entity_id)


def clear_plan(entity_id: str) -> None:
    """模块级注销入口。"""
    _REGISTRY.clear_plan(entity_id)


def entries() -> dict[str, str]:
    """模块级全量快照。"""
    return _REGISTRY.entries()


def registry() -> PlanDeltaStore:
    """拿模块单例（装配/测试用；勿直接改内部）。"""
    return _REGISTRY


def reset_plan_registry() -> None:
    """测试辅助：清空账本与广播基准。"""
    _REGISTRY._plans.clear()
    _REGISTRY._broadcast = None


#: band → cue 表现映射（M5-K7 §2 钩子缝；§2.1 表）。
#: WillingnessExpression.band（will.py 四档）→ ImpulseFeedbackMessage.cue 四值。
#: ws.py `_impulse_cue` 的旧占位是纯词面启发式（问号→hesitation）；本表是
#: M4 真实执行器接入后的替换点——真实 band 接入时只改这一处，ws.py 分发不变。
_BAND_CUE: dict[int, str] = {
    0: "accepted",  # 0.0-0.3 自然接受
    1: "hesitation",  # 0.3-0.6 轻微迟疑
    2: "complaint",  # 0.6-0.8 明显抱怨
    3: "resistance",  # 0.8-1.0 强烈抵触
}


def band_to_cue(band: int) -> str:
    """意愿表现档 → cue（越界/未知档按最强表现 resistance；负数按 accepted）。

    防御性映射：band 值域由 will.py 四档固定，但 cue 词表一旦扩展（§5.1 加码）
    这里必须是兜底而非抛错——分发块不能因档位未知而崩。
    """
    if not isinstance(band, int):
        msg = f"band must be int, got {type(band).__name__}"
        raise TypeError(msg)
    if band < 0:
        return _BAND_CUE[0]
    return _BAND_CUE.get(band, _BAND_CUE[3])
