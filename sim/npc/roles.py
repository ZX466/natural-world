"""专属角色只消费感知帧；信息优势与约束不读取世界秘密。"""

from sim.core.events import WorldEvent, npc_monologue_event
from sim.perception.frame import Channel, PerceptionFrame

ROLES = {
    "villager_01": ("赵铁", 41, "镖师"),
    "villager_02": ("小满", 14, "乞丐"),
    "villager_03": ("苏婉", 34, "药铺掌柜"),
}


def role_events(npc_id: str, frame: PerceptionFrame | None, tick: int) -> list[WorldEvent]:
    if npc_id not in ROLES or frame is None:
        return []
    heard = [o.description for o in frame.observations if o.channel is Channel.HEARING]
    if not heard:
        return []
    clue = heard[0][:120]
    if npc_id == "villager_02":
        content = f"我蹲在墙角没人留意，听见{clue}，先记在心里。"
    elif npc_id == "villager_03":
        content = f"听见{clue}，事情牵着事情，究竟怎样还是说不准。"
    else:
        if not any(word in "".join(heard) for word in ("行凶", "救命", "动手", "打斗")):
            return []
        content = "镖局的规矩叫我守住差事，可见人遇险，得先救下来。"
    return [npc_monologue_event(tick=tick, npc_id=npc_id, form="thought", content=content)]
