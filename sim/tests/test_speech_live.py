"""S4: 语域进入对白和决策尾段，身份锚不变且不传权力数值。"""

from sim.agent.dialogue import template_line
from sim.content.protagonist import build_anchor
from sim.llm.prompts.assembler import (
    InputSlice,
    MemorySlice,
    PlanSlice,
    SituationSlice,
    assemble_prompt,
)
from sim.llm.prompts.banned_words import scan
from sim.npc.speech_register import SpeechContext


def test_dialogue_uses_derived_register():
    for tick in range(20):
        rough = template_line(
            "speaker", "小满", tick, speech_context=SpeechContext("平民", in_circle=False)
        )
        refined = template_line(
            "speaker", "小满", tick, speech_context=SpeechContext("士绅", in_circle=True)
        )
        assert rough != refined and "您" in refined
        assert scan(rough).ok and scan(refined).ok


def test_speech_context_changes_only_prompt_tail():
    def prompt(context):
        return assemble_prompt(
            build_anchor(),
            MemorySlice(),
            SituationSlice(),
            PlanSlice(),
            InputSlice(),
            "speech",
            speech_context=context,
        )

    rough = prompt(SpeechContext("平民", in_circle=False))
    refined = prompt(SpeechContext("士绅", in_circle=True))
    assert rough.messages[0] == refined.messages[0]
    assert rough.messages[1] != refined.messages[1]
    assert "粗" in rough.messages[1]["content"] and "文雅" in refined.messages[1]["content"]
    assert scan(refined.messages[1]["content"]).ok


def test_live_npc_chat_consumes_static_register_and_social_circle():
    from pathlib import Path

    from sim.core.world import EntityState, WorldState
    from sim.npc.chat_ledger import ChatLedger
    from sim.npc.model import Need, NpcProfileData
    from sim.npc.runtime import NpcRuntime
    from sim.npc.sim_exec import npc_events_for_tick
    from sim.npc.utility import UtilityModel
    from sim.world.map import TileMap
    from sim.world.pathfinding import Pathfinder

    scholar = NpcProfileData(
        "scholar", "先生", class_register="士绅", needs=(Need("social", 1.0, 1.0),)
    )
    runtime = NpcRuntime({scholar.npc_id: scholar}, UtilityModel(1))
    state = WorldState(
        entities={nid: EntityState(entity_id=nid, pos=(100, 53)) for nid in ("scholar", "friend")}
    )
    ledger = ChatLedger()
    ledger.adjust("scholar", "friend", kind="chat")
    town = TileMap.from_json_file(Path(__file__).resolve().parents[1] / "content/linhe-town.json")
    events = npc_events_for_tick(
        runtime,
        state,
        12 * 3600,
        Pathfinder(town),
        seed=42,
        chat_last={},
        chat_ledger=ledger,
        display_name_of={"friend": "小满"},
    )
    lines = [str(e.payload["line"]) for e in events if e.event_type.value == "npc.chat"]
    assert lines and all("您" in line for line in lines)


def test_persisted_language_boundary_reaches_runtime_profile():
    from sim.content.villagers import _profile_row
    from sim.core.persistence.models import NpcProfile
    from sim.core.persistence.npc_store import _row_to_profile_data
    from sim.npc.model import NpcProfileData

    row = NpcProfile(**_profile_row(NpcProfileData("scholar", "先生", class_register="士绅")))
    assert _row_to_profile_data(row).class_register == "士绅"
