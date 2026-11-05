"""Town landmarks shared by NPC destinations and diegetic directions."""

from dataclasses import dataclass
from types import MappingProxyType


@dataclass(frozen=True)
class Landmark:
    pos: tuple[int, int]
    name: str
    tags: frozenset[str]


LANDMARKS = MappingProxyType(
    {
        "peach_gate": Landmark((15, 18), "桃门", frozenset({"gate", "leisure"})),
        "ancestral_hall": Landmark((40, 18), "祖屋", frozenset({"craft", "home"})),
        "stream_bridge": Landmark((66, 19), "溪桥", frozenset({"fishing"})),
        "old_school": Landmark((93, 19), "村塾", frozenset({"education"})),
        "terraced_fields": Landmark((122, 19), "梯田", frozenset({"farming"})),
        "signal_hill": Landmark((18, 52), "钟山", frozenset({"forestry"})),
        "guest_yard": Landmark((44, 53), "客栈院", frozenset({"food", "service"})),
        "craft_market": Landmark((72, 52), "染坊市集", frozenset({"food", "trade", "craft"})),
        "village_square": Landmark((100, 52), "村广场", frozenset({"leisure"})),
        "archive_room": Landmark((124, 52), "藏书房", frozenset({"service"})),
    }
)


def landmarks_text() -> str:
    places = "、".join(f"{site.name}（{site.pos[0]},{site.pos[1]}）" for site in LANDMARKS.values())
    return f"你知道这些去处：药铺（100,53，你的铺子）、{places}。想去哪就 move_to 它的坐标。"
