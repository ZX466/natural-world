"""批次 D8（「标记」→「人」——感知叙事接真名）钉子。

问题：感知叙事给模型的是 rtoken 替身（rt-1a2b...），模型复述作 target_id
必被闸门拒（「这么多标记」实录）。修：assemble 增 display_name_of 可选映射
（entity_id → 戏内名；名字是戏内事实可出站，rtoken 才是替身），label 优先
真名，缺省回退 rtoken（既有行为零回归）。
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.t1


class TestDisplayNameNarration:
    @staticmethod
    def _engine():
        from sim.api.main import _fallback_map
        from sim.perception.senses import PerceptionEngine

        return PerceptionEngine(_fallback_map())

    @staticmethod
    def _state():
        from sim.core.world import EntityState, WorldState

        return WorldState(
            world_seed=42,
            entities={
                "chenmo": EntityState(entity_id="chenmo", pos=(5, 5)),
                "villager_01": EntityState(entity_id="villager_01", pos=(6, 5)),
            },
        )

    def test_narration_uses_display_name(self) -> None:
        """display_name_of 提供 → 观测文本用真名（「赵铁柱」非 rt-…）。"""
        engine = self._engine()
        frame = engine.assemble(
            self._state(),
            "chenmo",
            display_name_of={"villager_01": "赵铁柱", "chenmo": "陈默"},
        )
        texts = [ob.description for ob in frame.observations]
        assert any("赵铁柱" in t for t in texts), f"真名未进叙事: {texts}"
        assert not any("rt-" in t for t in texts)

    def test_no_mapping_falls_back_to_rtoken(self) -> None:
        """缺省 None → rtoken 替身（既有行为，零回归）。"""
        engine = self._engine()
        frame = engine.assemble(self._state(), "chenmo")
        texts = [ob.description for ob in frame.observations]
        assert any("rt-" in t for t in texts)

    def test_main_wires_display_names(self) -> None:
        """main.py 静态钉：感知挂载必须传 display_name_of。"""
        from pathlib import Path

        source = (Path(__file__).parents[1] / "api" / "main.py").read_text(encoding="utf-8")
        assert "display_name_of" in source
