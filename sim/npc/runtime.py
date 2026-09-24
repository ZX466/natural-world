"""sim.npc.runtime — NPC 装配入口（M2-A1 §1.3；世界循环每 tick 调一次）。

NpcRuntime.tick(tick, hidden_states=..., context_of=...) → 本 tick 事件批次（NPC_ACT）。
职责链（固定序，C5）：
  0. 隐藏档触发窗口重估（HiddenState.evaluate 每 tick，self-unknown §2；纯函数）
  1. 需求推进（needs.advance_needs，DEFAULT_DECAYS）
  2. L1 效用打分（utility.evaluate_batch，向量化）
  3. 事件产出（npc_act_event；params 只带白名单键）

不做：SQL（数据访问归 NpcStore，opencode M2-D2；物化走 sim/npc/assemble.py）、
LLM 调用（L2 在 sim/agent/）、LOD 升降格判定（事件驱动，本批只按 lod 字段过滤 L0）。
frozen 态：tick 只产出事件与新 profile dict；hidden_states 的窗口按 tick 原地替换
（HiddenState frozen → evaluate 返回新实例，dict 引用由调用方持有）。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field, replace

from sim.core.events import WorldEvent, hidden_emerge_event, npc_act_event
from sim.npc.actions import ACTION_PAYLOAD_KEYS
from sim.npc.contract import HiddenState
from sim.npc.model import NpcProfileData
from sim.npc.needs import advance_needs
from sim.npc.utility import UtilityModel, evaluate_batch


@dataclass
class NpcRuntime:
    """50 NPC 装配（§1.3）：内存态 = {npc_id: NpcProfileData}（物化产物）。"""

    profiles: dict[str, NpcProfileData]
    utility: UtilityModel
    _order: list[str] = field(default_factory=list, init=False)

    def __post_init__(self) -> None:
        # 固定 NPC 序（dict 序可能因物化顺序漂移；排序保证 C5 确定性）
        self._order = sorted(self.profiles.keys())
        if self.utility.n_npc != len(self._order):
            msg = f"utility.n_npc={self.utility.n_npc} 与 profiles 数 {len(self._order)} 不一致"
            raise ValueError(msg)

    def tick(
        self,
        tick: int,
        *,
        hidden_states: dict[str, HiddenState] | None = None,
        context_of: Callable[[str], str] | None = None,
    ) -> list[WorldEvent]:
        """推进一 tick：隐藏档重估(+E1 浮现事件) → 需求 → 效用 → 事件批次（顺序固定，可重放）。

        hidden_states：物化产物 {npc_id: HiddenState}；传入时第 0 步按
        context_of(npc_id) 重估触发窗口（frozen.evaluate 返回新实例，原 dict 更新）。
        context_of：npc_id → 自身处境文本（感知帧叙事+内感受）；缺省恒空 =
        无情境触发（窗口照旧）。
        E1（F2 收口，m3-evidence-chain §3）：重估后 delta = 新进触发窗口的属性，
        非空 → 每 NPC 合并一条 npc.hidden_emerge 事件，先于 NPC_ACT（证据链根
        先行）；attr_ids 排序（frozenset 序漂移禁入事件流，C5）。witnesses 由
        感知层装配（evidence.witnesses_of_emerge）——runtime 无感知帧，留空，
        随世界循环接线批次补齐（witnessed 判定须三要素齐，空 witnesses 自然
        不构成目击，fail-closed）。
        """
        events: list[WorldEvent] = []

        # 0. 隐藏档触发窗口重估（每 tick；hidden.py §2 纯函数）+ E1 浮现事件
        if hidden_states is not None:
            for nid in self._order:
                if nid in hidden_states:
                    prev = hidden_states[nid]
                    ctx = context_of(nid) if context_of is not None else ""
                    now = prev.evaluate(ctx)
                    hidden_states[nid] = now
                    delta = now.triggered - prev.triggered
                    if delta:
                        events.append(
                            hidden_emerge_event(
                                tick=tick,
                                npc_id=nid,
                                attr_ids=tuple(sorted(delta)),
                            )
                        )

        # 1. 需求推进（frozen：replace 生成新元组）
        advanced: dict[str, NpcProfileData] = {}
        for npc_id in self._order:
            p = self.profiles[npc_id]
            advanced[npc_id] = replace(p, needs=advance_needs(p.needs))

        # 2. L0 统计档不做决策（不建对象语义）；其余按固定序参与批量打分
        active_ids = [nid for nid in self._order if advanced[nid].lod > 0]
        if not active_ids:
            self.profiles = advanced
            return []
        decisions = evaluate_batch([advanced[nid] for nid in active_ids], self.utility)

        # 3. 事件产出：params 只带白名单键（eat/rest/wander/move 无参数动作 → 空 params）
        for nid, d in zip(active_ids, decisions, strict=True):
            allowed = ACTION_PAYLOAD_KEYS[d.action]
            params = {k: str(v) for k, v in d.scores.items() if k in allowed}
            events.append(
                npc_act_event(
                    tick=tick,
                    npc_id=nid,
                    action=d.action,
                    target=d.target,
                    params=params,
                )
            )

        self.profiles = advanced
        return events
