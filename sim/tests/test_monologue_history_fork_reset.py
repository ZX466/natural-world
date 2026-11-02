"""读档（分叉）必须清空进程内心声历史账本。

根因（2026-11-02 实测）：`ws.py::_MONO_HISTORY` 是模块级 `deque`，**全仓没有任何
`.clear()`**。读档成功路径 `main.py` 会 `broadcast_json(snapshot_payload(...))`，
而 `snapshot_payload` 带 `monologue_history`（`ws.py:570`）——客户端 `ws.ts:178`
逐条喂 `onMonologue` 且不清空本地面板。

⇒ 读档后心之声面板先灌进**旧分支**最近 20 条。这与 D 修的是同一类问题：
D 修的是「别人的内心话」（按投递面过滤），本条修的是「**旧世界线的**内容」
（按分支生命周期清账）。修完 D 之后残留的正是这一层：`bubble` 面全过过滤，
所以旧分支的村民嘟囔会整批出现在新分支的面板上。

口径：分叉 = 进程内账本全部失效（与 `npc_l2.reset()` / `chat_ledger.reset()` 同批，
见 `main.py` 读档成功块）。事件仍在库里，历史可重放，只是不再跨分支残留。
"""

from __future__ import annotations

from collections import deque
from typing import Any

import pytest

pytestmark = pytest.mark.t1


@pytest.fixture(autouse=True)
def _fresh_history(monkeypatch: pytest.MonkeyPatch) -> Any:
    import sim.api.ws as ws

    monkeypatch.setattr(ws, "_MONO_HISTORY", deque(maxlen=20))
    yield ws


def _push(ws: Any, *contents: str) -> None:
    from sim.core.events import npc_monologue_event

    ws.monologue_history_push(
        [npc_monologue_event(1, "villager_07", "bubble", text) for text in contents]
    )


class TestClearOnFork:
    def test_clear_empties_the_ledger(self, _fresh_history: Any) -> None:
        ws = _fresh_history
        _push(ws, "旧分支嘟囔一", "旧分支嘟囔二")
        assert len(ws._MONO_HISTORY) == 2
        ws.monologue_history_clear()
        assert len(ws._MONO_HISTORY) == 0

    def test_cleared_ledger_yields_empty_snapshot_history(self, _fresh_history: Any) -> None:
        """清账后快照的 `monologue_history` 必须是空数组（面板不再被旧线灌满）。"""
        from sim.api.main import _fallback_map
        from sim.api.ws import snapshot_payload

        ws = _fresh_history
        _push(ws, "旧分支嘟囔")
        ws.monologue_history_clear()
        loop = _loop()
        assert snapshot_payload(loop, _fallback_map())["monologue_history"] == []

    def test_clear_is_idempotent_and_allows_new_pushes(self, _fresh_history: Any) -> None:
        """清空不是一次性开关：之后的新分支内容照常记账。"""
        ws = _fresh_history
        ws.monologue_history_clear()
        ws.monologue_history_clear()
        _push(ws, "新分支嘟囔")
        assert len(ws._MONO_HISTORY) == 1

    def test_clear_does_not_touch_anchor_registry(self, _fresh_history: Any) -> None:
        """只清心声账本——别的进程态（存档 id 集等）不归它管。"""
        ws = _fresh_history
        ws.register_anchor_id("a1", "旧日河风", "风吹河面")
        ws.monologue_history_clear()
        assert ws._ANCHOR_LABELS["a1"]["name"] == "旧日河风"


def _loop() -> Any:
    from sim.core.clock import GameClock
    from sim.core.tick import TickLoop
    from sim.core.world import WorldState, build_default_bus

    return TickLoop(GameClock(speed=1), build_default_bus(), WorldState(world_seed=1))
