"""批次 D6（感知进陈默 prompt）钉子。

缝：run_perception_step 每 tick 为全员装帧（键=rtoken），driver.decide_once
的 perception_text 恒空——把 PerceptionFrame.narrated() 接进决策循环。

面：
1. sim/agent/driver.py 增 perception_provider 注入（Callable[[], str]）；
2. main.py 装配：rtoken_of("chenmo") → loop.perception_frames → narrated()；
3. 降级：帧缺失/空感知 → 空文本（prompt [处境] 段省略——既有行为）。
"""

from __future__ import annotations

import asyncio

import pytest

pytestmark = pytest.mark.t1


class TestPerceptionIntoPrompt:
    def test_decide_once_consumes_perception_text(self) -> None:
        """perception_provider 返回文本 → 出现在 LLM messages[1] [处境] 段。"""
        from sim.agent.driver import ChenmoDriver
        from sim.content.protagonist import build_anchor

        captured: list[list[dict[str, str]]] = []

        class _Llm:
            async def complete(self, profile, messages):
                captured.append(messages)
                from sim.llm.client import LlmCallResult

                return LlmCallResult(
                    request_id="t",
                    content='{"action": "wait", "reason": "且听听看", "confidence": 0.9}',
                    prompt_tokens=1,
                    completion_tokens=1,
                    total_tokens=2,
                    latency_ms=1.0,
                    attempt=1,
                    cache_hit=False,
                )

        provider_ran = []

        def _provider() -> str:
            provider_ran.append(1)
            return "你看见：街上有人走过。\n你闻到：空气里有烟火气。"

        driver = ChenmoDriver(
            anchor=build_anchor(),
            llm=_Llm(),  # type: ignore[arg-type]
            profile_provider=lambda: object(),  # type: ignore[arg-type,return-value]
            perception_provider=_provider,
        )
        from sim.core.world import EntityState, WorldState

        state = WorldState(
            world_seed=42,
            entities={"chenmo": EntityState(entity_id="chenmo", pos=(8, 16))},
        )
        ok = asyncio.run(driver.decide_once(state, tick=100))
        assert ok is True
        assert provider_ran, "perception_provider 必须被调用"
        body = captured[0][1]["content"]
        assert "街上有人走过" in body
        assert "烟火气" in body

    def test_no_provider_backcompat(self) -> None:
        """不传 perception_provider → 既有行为（[处境] 段省略，不炸）。"""
        from sim.agent.driver import ChenmoDriver
        from sim.content.protagonist import build_anchor

        captured: list[list[dict[str, str]]] = []

        class _Llm:
            async def complete(self, profile, messages):
                captured.append(messages)
                from sim.llm.client import LlmCallResult

                return LlmCallResult(
                    request_id="t",
                    content='{"action": "wait", "reason": "歇会儿", "confidence": 0.9}',
                    prompt_tokens=1,
                    completion_tokens=1,
                    total_tokens=2,
                    latency_ms=1.0,
                    attempt=1,
                    cache_hit=False,
                )

        driver = ChenmoDriver(
            anchor=build_anchor(),
            llm=_Llm(),  # type: ignore[arg-type]
            profile_provider=lambda: object(),  # type: ignore[arg-type,return-value]
        )
        from sim.core.world import EntityState, WorldState

        state = WorldState(
            world_seed=42,
            entities={"chenmo": EntityState(entity_id="chenmo", pos=(8, 16))},
        )
        ok = asyncio.run(driver.decide_once(state, tick=100))
        assert ok is True
        assert "处境" not in captured[0][1]["content"]

    def test_main_wires_perception(self) -> None:
        """main.py 静态钉：chenmo 装配点必须传 perception_provider。"""
        from pathlib import Path

        source = (Path(__file__).parents[1] / "api" / "main.py").read_text(encoding="utf-8")
        assert "perception_provider" in source
