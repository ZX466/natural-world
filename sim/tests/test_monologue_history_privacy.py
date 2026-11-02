"""心声历史账本的投递面同源：thought 私密面不得随快照漏给旁观视角。

根因（2026-11-02 实测）：`ws.py::monologue_history_push` 无条件把**每一条**
`npc.monologue` 事件塞进 `_MONO_HISTORY`，不看 `route_monologue` 的投递面。
于是村民嘟囔与三个专属角色（赵铁/小满/苏婉）的 thought 虽然实时投递被丢弃
（定向发往 `villager_02` 无人接收），却随每次 full_snapshot 整表出站——
前端 `ws.ts` 逐条喂 `onMonologue`，`runtime.ts` 见 `form !== 'bubble'` 即
`pushMonologue`，全部落进陈默的「心之声」面板。

量级：三个专属角色 18 条/分钟 + 陈默 1 条/分钟 → 20 条环形缓冲里约 19 条
不是陈默的，面板每 ~63 秒被别人的内心话冲干净一次。

修法口径（与 `route_monologue` 同源，不另立规矩）：
- `bubble` / `plan` 是广播面 → 任何视角都可见；
- `thought` 是私密面 → 只有**本人视角**可见；快照的视角由服务端按
  `_protagonist_id(loop)` 定（不采客户端自报）。
"""

from __future__ import annotations

from collections import deque
from typing import Any

import pytest

pytestmark = pytest.mark.t1

PROTAGONIST = "chenmo"


@pytest.fixture(autouse=True)
def _fresh_history(monkeypatch: pytest.MonkeyPatch) -> Any:
    import sim.api.ws as ws

    monkeypatch.setattr(ws, "_MONO_HISTORY", deque(maxlen=20))
    yield ws


def _events() -> list[Any]:
    from sim.core.events import npc_monologue_event

    return [
        npc_monologue_event(1, PROTAGONIST, "thought", "先去药铺看看。"),
        npc_monologue_event(1, "villager_02", "thought", "我蹲在墙角没人留意，听见有人哭。"),
        npc_monologue_event(1, "villager_02", "bubble", "凭什么，干活的是我。"),
    ]


def _loop(*entity_ids: str) -> Any:
    from sim.core.clock import GameClock
    from sim.core.events import world_create_event
    from sim.core.tick import TickLoop
    from sim.core.world import WorldState, build_default_bus

    loop = TickLoop(GameClock(speed=1), build_default_bus(), WorldState(world_seed=1))
    if entity_ids:
        loop.enqueue(world_create_event(tick=0, seed=1, entity_ids=entity_ids))
    return loop


def _contents(frames: list[dict[str, Any]]) -> list[tuple[str, str]]:
    return [(f["form"], f["content"]) for f in frames]


class TestHistoryDeliveryFace:
    def test_protagonist_thought_is_kept(self, _fresh_history: Any) -> None:
        ws = _fresh_history
        loop = _loop(PROTAGONIST, "villager_02")
        ws.monologue_history_push(_events())
        kept = _contents(ws.monologue_history_payload(loop))
        assert ("thought", "先去药铺看看。") in kept

    def test_other_npc_thought_is_not_kept(self, _fresh_history: Any) -> None:
        ws = _fresh_history
        loop = _loop(PROTAGONIST, "villager_02")
        ws.monologue_history_push(_events())
        kept = _contents(ws.monologue_history_payload(loop))
        assert ("thought", "我蹲在墙角没人留意，听见有人哭。") not in kept

    def test_bubble_is_kept_for_any_viewer(self, _fresh_history: Any) -> None:
        ws = _fresh_history
        loop = _loop(PROTAGONIST, "villager_02")
        ws.monologue_history_push(_events())
        assert ("bubble", "凭什么，干活的是我。") in _contents(ws.monologue_history_payload(loop))

    def test_no_protagonist_drops_all_thoughts(self, _fresh_history: Any) -> None:
        """世界无实体（尚未 world.create）→ 无视角 → thought 一律不出站（fail-closed）。"""
        ws = _fresh_history
        loop = _loop()
        ws.monologue_history_push(_events())
        kept = _contents(ws.monologue_history_payload(loop))
        assert not any(form == "thought" for form, _ in kept)
        assert ("bubble", "凭什么，干活的是我。") in kept


class TestSnapshotCarriesFilteredHistory:
    """full_snapshot 是主要泄漏面——它必须按同一口径过滤。"""

    def test_snapshot_history_excludes_foreign_thoughts(self, _fresh_history: Any) -> None:
        from sim.api.main import _fallback_map
        from sim.api.ws import snapshot_payload

        ws = _fresh_history
        loop = _loop(PROTAGONIST, "villager_02")
        ws.monologue_history_push(_events())
        history = snapshot_payload(loop, _fallback_map())["monologue_history"]
        kept = _contents(history)
        assert ("thought", "先去药铺看看。") in kept
        assert ("thought", "我蹲在墙角没人留意，听见有人哭。") not in kept
