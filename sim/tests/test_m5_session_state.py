"""M5-K3 批次 B：session 首帧（D-5 连接期初值 + D-6 分叉告知，合并一帧）。

判据（裁 21-A §A D-5/D-6/D-7）：
- 一帧 `session_state` 同时承载**连接期初值**（刻度 / 暂停态 / 游标指针）与
  **分叉告知**（叙事化一行）——两处需求合并，避免两次新增消息。
- **零原始数值**：`speed` 只在 {1,4,16}（暂停时 = 恢复后倍率，不是 0）、游标指针只有
  `name` + `story_label`、告知是戏内口语行；`tick`/`seq`/`branch_id`/`entity_id` 零出现。
- 读档成功 → **两帧**（`session_state` 告知 + `full_snapshot`）；失败 → 仍单帧 error
  且不断线（K4 §3.3）。
- **D-7**：重同步一律全量，本帧不含任何 diff/游标键。
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

from sim.api import ws as ws_mod
from sim.api.ws import (
    ControlState,
    fork_notice,
    handle_client_message,
    register_anchor_id,
    session_state_payload,
)
from sim.core.events import world_create_event
from sim.core.tick import TickLoop
from sim.core.world import WorldState, build_default_bus
from sim.llm.prompts.banned_words import Hit, ScanResult
from sim.llm.prompts.banned_words import scan as real_scan
from sim.world.map import CHUNK_SIZE, Chunk, TileMap
from sim.world.pathfinding import Pathfinder

#: `SessionStateMessage` 允许的键（信封四键 + 四载荷键）。
SESSION_STATE_KEYS = {
    "type",
    "channel",
    "v",
    "ws_seq",
    "speed",
    "paused",
    "anchor",
    "notice",
}


@pytest.fixture(autouse=True)
def _clean_anchor_registry() -> Iterator[None]:
    ws_mod.reset_anchor_registry()
    yield
    ws_mod.reset_anchor_registry()


@pytest.fixture()
def loop() -> TickLoop:
    loop = TickLoop(clock=_clock(), bus=build_default_bus(), state=WorldState(world_seed=42))
    loop.enqueue(world_create_event(tick=0, seed=42, entity_ids=("chenmo",)))
    loop.drain_events()
    return loop


def _clock():
    from sim.core.clock import GameClock

    return GameClock(speed=1.0)


@pytest.fixture()
def tile_map() -> TileMap:
    chunks = {}
    for cy in range(2):
        for cx in range(2):
            chunks[(cx, cy)] = Chunk(
                cx=cx,
                cy=cy,
                ground=(1,) * (CHUNK_SIZE * CHUNK_SIZE),
                collision=(True,) * (CHUNK_SIZE * CHUNK_SIZE),
            )
    return TileMap(width=32, height=32, chunks=chunks)


@pytest.fixture()
def pf(tile_map: TileMap) -> Pathfinder:
    return Pathfinder(tile_map)


@pytest.fixture()
def control() -> ControlState:
    return ControlState()


class TestSessionStatePayload:
    def test_shape_and_channel(self) -> None:
        frame = session_state_payload(speed=4, paused=False)
        assert frame["type"] == "session_state"
        assert frame["channel"] == "session"
        assert set(frame) == SESSION_STATE_KEYS
        assert frame["speed"] == 4
        assert frame["paused"] is False
        assert frame["anchor"] is None
        assert frame["notice"] is None

    def test_anchor_pointer_keeps_only_narrative_fields(self) -> None:
        """供数侧多带 `tick`（内部列）时，帧里必须只剩叙事化两项。"""
        pointer: dict[str, Any] = {
            "name": "初到临河",
            "story_label": "第二日 · 清晨",
            "tick": 12345,
        }
        frame = session_state_payload(
            speed=1, paused=False, anchor=pointer, notice="你回到了那段日子"
        )
        assert frame["anchor"] == {"name": "初到临河", "story_label": "第二日 · 清晨"}
        assert frame["notice"] == "你回到了那段日子"

    def test_paused_reports_remembered_speed_not_zero(self) -> None:
        """暂停态 speed = 恢复后倍率（schema 枚举无 0，也比 0 更有用）。"""
        control = ControlState(speed_before_pause=16.0, paused=True)
        frame = session_state_payload(speed=control.effective_speed(), paused=control.paused)
        assert frame["speed"] == 16
        assert frame["paused"] is True

    def test_no_banned_world_values(self) -> None:
        """零原始数值：递归查键名与值；`ws_seq` 是传输序号，不在禁列。"""
        frame = session_state_payload(
            speed=16, paused=True, anchor={"name": "档", "story_label": "第三日"}, notice="回来了"
        )
        banned_keys = {"seq", "tick", "world_tick", "branch_id", "entity_id", "seed", "branch"}
        banned_value_words = ("branch", "snapshot", "tick")

        def walk(node: Any) -> None:
            if isinstance(node, dict):
                for key, value in node.items():
                    assert key not in banned_keys, f"越界键：{key}"
                    walk(value)
            elif isinstance(node, str):
                lowered = node.lower()
                for word in banned_value_words:
                    assert word not in lowered, f"值里带系统词：{word} @ {node}"

        walk(frame)


class TestForkNotice:
    def test_names_the_anchor(self) -> None:
        assert "初到临河" in fork_notice("初到临河")

    def test_falls_back_without_name(self) -> None:
        assert fork_notice("")


class TestLoadAnchorEmitsSessionState:
    """D-6：读档成功 = 告知帧 + 全量快照两帧；失败仍单帧 error。"""

    def test_failure_message_is_terminal_scanned(
        self, loop: TickLoop, pf: Pathfinder, control: ControlState, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Case A：玩家可见的物化失败文案必须在最终边界调用 scan()。"""
        scanned: list[str] = []

        def observe(text: str) -> ScanResult:
            scanned.append(text)
            return real_scan(text)

        monkeypatch.setattr(ws_mod, "scan", observe)
        reply = handle_client_message(
            {"type": "load_anchor", "channel": "session", "anchor_id": "nope"},
            loop,
            pf,
            control,
        )

        assert isinstance(reply, dict)
        assert reply["type"] == "error"
        assert reply["message"] in scanned
        assert not real_scan(reply["message"]).hits

    def test_failure_message_hit_degrades_to_clean_fallback(
        self, loop: TickLoop, pf: Pathfinder, control: ControlState, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Case A：命中时退化，不把原因或命中文案放给玩家。"""
        primary = "这个档读不出来了。"
        fallback = "档打不开。"
        warnings: list[tuple[str, str]] = []

        class Logger:
            def warning(self, event: str, *, reason: str) -> None:
                warnings.append((event, reason))

        def inject_hit(text: str) -> ScanResult:
            if text == primary:
                return ScanResult(
                    hits=(Hit(word="injected", start=0, end=1, kind="meta"),),
                    cleaned=text,
                )
            return real_scan(text)

        monkeypatch.setattr(ws_mod, "scan", inject_hit)
        monkeypatch.setattr(ws_mod, "logger", Logger())
        reply = handle_client_message(
            {"type": "load_anchor", "channel": "session", "anchor_id": "nope"},
            loop,
            pf,
            control,
        )

        assert isinstance(reply, dict)
        assert reply["message"] == fallback
        assert not real_scan(reply["message"]).hits
        assert warnings == [("ws.anchor_load_message_degraded", "banned_message_outbound")]

    def test_failure_message_tries_next_fallback_after_hit(
        self, loop: TickLoop, pf: Pathfinder, control: ControlState, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """案 A：固定兜底候选命中时继续终扫，不提前放弃为无文案。"""
        primary = "这个档读不出来了。"
        first_fallback = "档打不开。"

        def inject_hit(text: str) -> ScanResult:
            if text in {primary, first_fallback}:
                return ScanResult(
                    hits=(Hit(word="injected", start=0, end=1, kind="meta"),),
                    cleaned=text,
                )
            return real_scan(text)

        monkeypatch.setattr(ws_mod, "scan", inject_hit)
        reply = handle_client_message(
            {"type": "load_anchor", "channel": "session", "anchor_id": "nope"},
            loop,
            pf,
            control,
        )

        assert isinstance(reply, dict)
        assert reply["message"] == "读不了。"

    def test_success_returns_notice_then_snapshot(
        self, loop: TickLoop, pf: Pathfinder, control: ControlState
    ) -> None:
        register_anchor_id("a1", name="初到临河", story_label="第二日 · 清晨")
        reply = handle_client_message(
            {"type": "load_anchor", "channel": "session", "anchor_id": "a1"},
            loop,
            pf,
            control,
        )
        assert isinstance(reply, list)
        assert [f["type"] for f in reply] == ["session_state", "full_snapshot"]
        notice_frame, snapshot = reply
        assert notice_frame["anchor"] == {"name": "初到临河", "story_label": "第二日 · 清晨"}
        assert notice_frame["notice"] is not None
        assert set(notice_frame) == SESSION_STATE_KEYS
        assert snapshot["channel"] == "render"

    def test_failure_stays_single_error_frame(
        self, loop: TickLoop, pf: Pathfinder, control: ControlState
    ) -> None:
        reply = handle_client_message(
            {"type": "load_anchor", "channel": "session", "anchor_id": "nope"},
            loop,
            pf,
            control,
        )
        assert isinstance(reply, dict)
        assert reply["type"] == "error"
        assert reply["code"] == "load_failed"

    def test_success_without_registered_labels_still_narrated(
        self, loop: TickLoop, pf: Pathfinder, control: ControlState
    ) -> None:
        """只有 id 供数（老注册点）时告知退化，但帧与全量仍两帧。"""
        register_anchor_id("a2")
        reply = handle_client_message(
            {"type": "load_anchor", "channel": "session", "anchor_id": "a2"},
            loop,
            pf,
            control,
        )
        assert isinstance(reply, list)
        assert reply[0]["type"] == "session_state"
        assert reply[0]["anchor"] == {"name": "", "story_label": ""}
        assert reply[0]["notice"] is not None
