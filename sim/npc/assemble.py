"""sim.npc.assemble — NPC runtime 装配入口（M2-A2 第三批；m2-npc-cognition §1.3）。

数据域（opencode NpcStore）与架构域（NpcRuntime）之间的装配缝：
一次 async 物化（profiles + 隐藏档各一次查询，禁逐 NPC）→ 纯内存 NpcRuntime
+ {npc_id: HiddenState}。本模块不做 SQL、不做 tick 推进——那是 runtime 的事。
"""

from __future__ import annotations

from sim.core.persistence.npc_store import NpcStore
from sim.npc.contract import HiddenState
from sim.npc.runtime import NpcRuntime
from sim.npc.utility import UtilityModel


async def assemble_runtime(
    store: NpcStore, npc_ids: list[str] | None = None
) -> tuple[NpcRuntime, dict[str, HiddenState]]:
    """物化 50 NPC（L0→L1）+ 隐藏档 → (runtime, hidden_states)。

    npc_ids None = 物化本分支全部（MVP=50）。utility 按实得 NPC 数建
    （n_npc 必须与 profiles 数一致，runtime.__post_init__ 校验）。
    """
    profiles = await store.materialize(npc_ids)
    hidden_rows = await store.materialize_hidden(
        list(profiles) if npc_ids is not None else None
    )
    # 无隐藏档 NPC 补恒等值（零分支透传：全员有键，消费点免 KeyError 分支）
    hidden = {nid: hidden_rows.get(nid, HiddenState.empty()) for nid in profiles}
    runtime = NpcRuntime(profiles=profiles, utility=UtilityModel(n_npc=len(profiles)))
    return runtime, hidden
