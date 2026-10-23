"""sim.npc.assemble — NPC runtime 装配入口（M2-A2 第三批；m2-npc-cognition §1.3）。

数据域（opencode NpcStore）与架构域（NpcRuntime）之间的装配缝：
一次 async 物化（profiles + 隐藏档各一次查询，禁逐 NPC）→ 纯内存 NpcRuntime
+ {npc_id: HiddenState}。本模块不做 SQL、不做 tick 推进——那是 runtime 的事。
"""

from __future__ import annotations

from collections.abc import Mapping

from sim.core.persistence.npc_store import NpcStore
from sim.core.persistence.power_store import PowerState
from sim.npc.contract import HiddenState
from sim.npc.runtime import NpcRuntime
from sim.npc.utility import UtilityModel


async def assemble_runtime(
    store: NpcStore,
    npc_ids: list[str] | None = None,
    *,
    external_controller_ids: frozenset[str] = frozenset(),
) -> tuple[NpcRuntime, dict[str, HiddenState]]:
    """物化 50 NPC（L0→L1）+ 隐藏档 → (runtime, hidden_states)。

    npc_ids None = 物化本分支全部（MVP=50）。utility 按实得 NPC 数建
    （n_npc 必须与 profiles 数一致，runtime.__post_init__ 校验）。
    专用控制器拥有的实体不参与效用装配；归属由装配方显式声明，与档案出现时序无关。
    """
    profiles = await store.materialize(npc_ids)
    profiles = {
        nid: profile for nid, profile in profiles.items() if nid not in external_controller_ids
    }
    hidden_rows = await store.materialize_hidden(
        list(profiles) if npc_ids is not None or external_controller_ids else None
    )
    # 无隐藏档 NPC 补恒等值（零分支透传：全员有键，消费点免 KeyError 分支）
    hidden = {nid: hidden_rows.get(nid, HiddenState.empty()) for nid in profiles}
    runtime = NpcRuntime(profiles=profiles, utility=UtilityModel(n_npc=len(profiles)))
    return runtime, hidden


def attach_power(runtime: NpcRuntime, states: Mapping[str, PowerState]) -> None:
    """权力快照装配（M4-D15 补线：M6 批次 C 机制 → 实况面开闸）。

    PowerStore.materialize 产物 → runtime.power（效用面权力列偏置随即生效，
    utility.py: power × POWER_MAX_BIAS 只加社交两列）。装配语义：

    - **空表 = 不赋**：无行（或全为在册外 id）保持 None——「无行 ≡ 0」库口径
      下 0 值权力与 None 打分逐位相等（test_m6_power_utility 已钉），装配面
      逐位同旧，不破既有确定性钉（C5）；
    - **只认在册 id**：跨分支残留行（profiles 外）不进快照（装配面只服务
      实况在册人员，幽灵 id 拒之门外）；
    - 纯内存赋值，零 IO（物化由调用方 async 完成——本模块不做 SQL）。
    """
    snapshot = {
        nid: float(state.power_level) for nid, state in states.items() if nid in runtime.profiles
    }
    if not snapshot:
        return
    runtime.power = snapshot
