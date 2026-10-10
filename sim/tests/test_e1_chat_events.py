"""E1：npc.chat 事件契约（工厂校验 + PAYLOAD_MODELS 登记 + bus 可重放）。"""

import pytest

from sim.core.events import EventKind, npc_chat_event
from sim.core.persistence.event_validation import PAYLOAD_MODELS, validate_store_row
from sim.core.world import TickContext, WorldState, build_default_bus


def test_npc_chat_event_factory_shape():
    ev = npc_chat_event(tick=10, npc_id="chenmo", to_id="villager_01", line="掌柜的，抓副药。")
    assert ev.event_type is EventKind.NPC_CHAT
    assert ev.actor_id == "chenmo"
    assert ev.payload["npc_id"] == "chenmo"
    assert ev.payload["to_id"] == "villager_01"
    assert ev.payload["line"] == "掌柜的，抓副药。"


def test_npc_chat_event_rejects_banned_line():
    with pytest.raises(ValueError, match="banned"):
        npc_chat_event(tick=10, npc_id="chenmo", to_id="villager_01", line="你是不是AI模型")


def test_npc_chat_payload_registered():
    assert PAYLOAD_MODELS[EventKind.NPC_CHAT].model_validate(
        {"npc_id": "a", "to_id": "b", "line": "x"}
    )


def test_npc_chat_store_row_validates():
    ev = npc_chat_event(tick=1, npc_id="a", to_id="b", line="吃了么")
    validate_store_row(ev.to_store_dict())


def test_npc_chat_fold_is_noop_hash_stable():
    bus = build_default_bus()
    state = WorldState(world_seed=42)
    ctx = TickContext()
    ev = npc_chat_event(tick=0, npc_id="a", to_id="b", line="吃了么")
    before = state.state_hash()
    result = bus.apply(state, ev, ctx)
    assert result.state.state_hash() == before  # no-op：hash 逐位不变
