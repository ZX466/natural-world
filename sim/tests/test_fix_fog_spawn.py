"""迷雾修复验证(2026-10-12 实况反馈):出生块揭示 + 快照 fog 全集含出生块。

Bug 1:创世 issue_move 落 spawn 后 fog_seen 空——主角站的 chunk 未揭示,
开局快照 fog.revealed 空 → 前端全图压暗(走一步才亮一格)。
Bug 2:重连 reset 后前端 fog 清空,后端快照 fog 全集是对的,但出生块
不在(同 bug 1)→ 重连后连主角站的地方都是黑的。

修复:TickLoop.issue_move 在主角移动到新 chunk 时同样记账本(与逐格
移动同口径);创世 spawn 走 issue_move → 自动覆盖。
"""

from sim.core.clock import GameClock
from sim.core.events import world_create_event
from sim.core.tick import TickLoop
from sim.core.world import WorldState, build_default_bus


def _loop() -> TickLoop:
    return TickLoop(
        clock=GameClock(speed=1.0), bus=build_default_bus(), state=WorldState(world_seed=42)
    )


def test_spawn_issue_move_reveals_protagonist_chunk():
    """主角 issue_move 落位 → fog_seen 含落点 chunk(开局不黑)。"""
    loop = _loop()
    loop.enqueue(world_create_event(tick=0, seed=42, entity_ids=("chenmo", "villager_01")))
    loop.advance_frame(1.0)
    loop.issue_move("chenmo", [(0, 0), (30, 46)])
    loop.advance_frame(1.0)
    assert (30 // 16, 46 // 16) in loop.fog_seen  # chunk (1, 2)
    # 村民移动不揭示（裁 40-4：迷雾=陈默观察面）
    loop.issue_move("villager_01", [(0, 0), (70, 72)])
    loop.advance_frame(1.0)
    assert (70 // 16, 72 // 16) not in loop.fog_seen


def test_snapshot_fog_contains_spawn_chunk():
    """快照 fog 全集含主角落点 chunk(前端开局只有主角周围亮)。"""
    from sim.api.main import _default_map
    from sim.api.ws import snapshot_payload

    loop = _loop()
    loop.enqueue(world_create_event(tick=0, seed=42, entity_ids=("chenmo",)))
    loop.advance_frame(1.0)
    loop.issue_move("chenmo", [(0, 0), (30, 46)])
    loop.advance_frame(1.0)
    payload = snapshot_payload(loop, _default_map())
    revealed = {(c["cx"], c["cy"]) for c in payload["fog"]["revealed"]}
    assert (30 // 16, 46 // 16) in revealed
