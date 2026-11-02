"""专属角色只消费感知帧；信息优势与约束不读取世界秘密。"""

from sim.core.events import WorldEvent, npc_monologue_event
from sim.perception.frame import Channel, PerceptionFrame

ROLES = {
    "villager_01": ("赵铁", 41, "镖师"),
    "villager_02": ("小满", 14, "乞丐"),
    "villager_03": ("苏婉", 34, "药铺掌柜"),
}


def _as_clause(description: str) -> str:
    """感知描述 → 可嵌进 `听见…，…` 的**从句**（2026-11-02 修）。

    `narrate_sound`（`perception/narrate.py:63`）产出的描述是**完整句**，自带句号：
    `"传来一阵脚步声，像是奚船家。"`。直接拼进 `听见{clue}，先记在心里。`
    就得到 `"听见传来一阵脚步声，像是奚船家。，先记在心里。"`——句号后紧跟逗号。
    真实库 `npc.monologue` 实测：209 条里 **60 条**命中（= thought 面全部 60 条）。
    去尾句号/问号/感叹号即可（只剥一层，不动中间的标点）。
    """
    return description.rstrip().rstrip("。？！")


def role_events(npc_id: str, frame: PerceptionFrame | None, tick: int) -> list[WorldEvent]:
    if npc_id not in ROLES or frame is None:
        return []
    heard = [o.description for o in frame.observations if o.channel is Channel.HEARING]
    if not heard:
        return []
    clue = _as_clause(heard[0][:120])
    if npc_id == "villager_02":
        content = f"我蹲在墙角没人留意，听见{clue}，先记在心里。"
    elif npc_id == "villager_03":
        content = f"听见{clue}，事情牵着事情，究竟怎样还是说不准。"
    else:
        if not any(word in "".join(heard) for word in ("行凶", "救命", "动手", "打斗")):
            return []
        content = "镖局的规矩叫我守住差事，可见人遇险，得先救下来。"
    return [npc_monologue_event(tick=tick, npc_id=npc_id, form="thought", content=content)]
