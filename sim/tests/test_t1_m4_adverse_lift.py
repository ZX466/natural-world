"""M4-D1 巧合连锁 T1 钉子（DESIGN §11；m4-plan 批次 D；S2 预审+裁 16 口径）。

**巧合连锁** = 不利事件暂时抬高后续不利概率（运气状态对 Agent 完全不可见——
它只觉得今天不顺）。实现 = 熵流 `mix.adverse`（裁 16-V1 定名）：
- 不利事件 → 产 ENTROPY_INJECT(material="cd"*16, stream="mix.adverse") →
  RngRegistry.reseed 推进材料哈希链 → 该流后续抽签分布改变 =「抬升」；
- **状态零驻留**：抬升不存在任何内存/表状态——它就是事件流本身（重放重建，
  裁 14-5「运气=事件流既成事实」）；
- Agent 零可见：mix.adverse 流的抽取只进世界内部判定（天气/事件掷点），
  感知帧/prompt/独白三面零词面零字段（S2 预审值零可见口径）。
"""
from __future__ import annotations

import pytest

from sim.core.events import EventKind, WorldEvent, entropy_event
from sim.core.rng import RngRegistry


def _adverse_event(*, tick: int = 50) -> WorldEvent:
    """不利事件 → 巧合连锁注入（magnitude 编码在材料 hex 里，S2 §V1 采信）。"""
    return entropy_event(tick=tick, stream="mix.adverse", payload_hex="cd" * 16)


@pytest.mark.t1
class TestAdverseLift:
    def test_adverse_event_kind_exists(self) -> None:
        ev = _adverse_event()
        assert ev.event_type is EventKind.ENTROPY_INJECT
        assert ev.payload["stream"] == "mix.adverse"

    def test_reseed_changes_stream_material(self) -> None:
        # 不利注入 → mix.adverse 流材料推进 → 后续抽签分布改变（「抬升」的机制面）
        reg = RngRegistry(world_seed=42)
        before = reg.draw_key("mix.adverse")
        reg2 = reg.reseed("mix.adverse", bytes.fromhex("cd" * 16))
        assert reg2.draw_key("mix.adverse") != before
        # 其他流不受影响（分流隔离，M0 语义）
        assert reg2.draw_key("world.weather") == reg.draw_key("world.weather")

    def test_replay_bit_exact(self) -> None:
        # C5/T2：同一事件序列重放 → 逐位一致
        reg = RngRegistry(world_seed=42)
        r1 = reg.reseed("mix.adverse", b"a" * 32).reseed("mix.adverse", b"b" * 32)
        r2 = RngRegistry(world_seed=42).reseed("mix.adverse", b"a" * 32).reseed(
            "mix.adverse", b"b" * 32
        )
        assert r1.draw_key("mix.adverse") == r2.draw_key("mix.adverse")

    def test_lift_state_survives_only_in_event_stream(self) -> None:
        # 状态零驻留：registry 只持材料 hex（重放重建），无「抬升概率」字段
        reg = RngRegistry(world_seed=42).reseed("mix.adverse", b"x" * 32)
        assert set(reg.materials.keys()) == {"mix.adverse"}
        assert "lift" not in reg.model_fields and "adverse" not in reg.model_fields


@pytest.mark.t1
class TestAdverseZeroLeak:
    """S2 值零可见：mix.adverse 三面（感知帧/prompt/独白）零词面零字段。"""

    def test_perception_frame_has_no_adverse_field(self) -> None:
        from sim.perception.frame import Observation, PerceptionFrame

        assert "adverse" not in PerceptionFrame.model_fields
        assert "luck" not in PerceptionFrame.model_fields
        assert "adverse" not in Observation.model_fields

    def test_monologue_payload_schema_has_no_lift(self) -> None:
        from sim.core.events import NpcMonologuePayload

        assert "lift" not in NpcMonologuePayload.model_fields
        assert "magnitude" not in NpcMonologuePayload.model_fields

    def test_adverse_stream_name_never_in_agent_visible(self) -> None:
        # 流名 mix.adverse 是戏外坐标：只进事件 payload 与 dev 日志；
        # 生产 agent/npc/llm/prompts 模块源码零引用（构造隔离扫描，X2 同款）。
        from pathlib import Path

        for mod in ("sim/agent", "sim/npc", "sim/llm/prompts", "sim/perception"):
            leaked = [
                p.name
                for p in Path(mod).glob("*.py")
                if "mix.adverse" in p.read_text(encoding="utf-8")
            ]
            assert leaked == [], f"{mod} 泄漏 mix.adverse 流名: {leaked}"
