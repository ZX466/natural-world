"""实现程度复检脚本的自测（T1）——防「检查器本身漂移成假绿」。

背景：`tools/check_implementation_status.py` 是 2026-10-20 建立的只读取证工具，
用于回答「游戏实现到什么程度」。**检查器若自己写错（比如把入站消息当出站
幽灵）就会给出误导性报告**，所以它的解析逻辑必须有钉子。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]


def _load_tool():
    path = _REPO / "tools" / "check_implementation_status.py"
    spec = importlib.util.spec_from_file_location("_impl_status_tool", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["_impl_status_tool"] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.t1
def test_type_of_map_covers_known_frames():
    """_TYPE_OF 解析必须拿到关键帧——解析失败会让三面核对隐形失效。"""
    tool = _load_tool()
    mapping = tool._type_of_map()
    assert mapping["TimescaleMessage"] == "timescale"
    assert mapping["CombatEventMessage"] == "combat_event"
    assert mapping["FullSnapshotMessage"] == "full_snapshot"


@pytest.mark.t1
def test_inbound_names_excludes_outbound_frames():
    """C→S 名单只含客户端上行帧；把出站帧混进来会让幽灵检测漏报。"""
    tool = _load_tool()
    inbound = tool._inbound_names()
    assert "move_request" in inbound
    assert "player_impulse" in inbound
    assert "full_snapshot" not in inbound
    assert "timescale" not in inbound


@pytest.mark.t1
def test_perception_is_reported_as_exempt_not_gap():
    """perception 是设计预留（ws-protocol.md 明示），必须标豁免而非真缺口。"""
    tool = _load_tool()
    problems = tool.check_ws_frames()
    perception_lines = [p for p in problems if "'perception'" in p or "perception（" in p]
    # perception 在协议文档豁免时应当出现在报告里且带「豁免」字样
    if perception_lines:
        assert any("豁免" in line for line in perception_lines)


@pytest.mark.t1
def test_protocol_version_badge_matches_code():
    """README 徽章与代码版本必须一致（历史上漂移过一次）。"""
    tool = _load_tool()
    assert tool.check_protocol_version() == []


@pytest.mark.t1
def test_combat_is_flagged_as_ghost_package_while_empty():
    """sim/combat 空壳包若仍声称四个子模块，必须被报出来。

    这是回归钉：将来真把 exchange/posture/resolve/timescale 建起来，
    或者把 docstring 改成现状，本用例会自然失效——届时改断言即可。
    """
    tool = _load_tool()
    problems = tool.check_ghost_packages()
    combat_lines = [p for p in problems if "sim/combat/" in p]
    combat_dir = _REPO / "sim" / "combat"
    has_real_modules = any(
        p.suffix == ".py" and p.name != "__init__.py" for p in combat_dir.iterdir()
    )
    if not has_real_modules:
        assert combat_lines, "空壳 sim/combat 必须被幽灵包检查报出"
