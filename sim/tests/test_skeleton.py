"""骨架冒烟测试（T1 级，无 LLM）：确认 DESIGN.md §5 的目录结构可导入。

本文件属「依赖/配置」域的骨架交付（cline TASK-001），只验证包结构可用；
六类不变量（T1）与回放确定性（T2）测试归 Claude（架构/测试域）在 M0 实现期补齐。
"""

import importlib

import pytest

SUBPACKAGES = [
    "sim",
    "sim.core",
    "sim.world",
    "sim.perception",
    "sim.perception.profiles",
    "sim.npc",
    "sim.agent",
    "sim.combat",
    "sim.llm",
    "sim.api",
    "sim.tests",
]


@pytest.mark.t1
@pytest.mark.parametrize("name", SUBPACKAGES)
def test_package_importable(name: str) -> None:
    """§5 的每个子包都必须可导入（骨架未被误删/改名）。"""
    assert importlib.import_module(name) is not None
