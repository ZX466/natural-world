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
def test_comment_stripping_prevents_false_positive():
    """注释里举例的 JSON 不算发射面。

    实测踩过：ws.py:195 注释写 `{"type":"hello","token":...}`，未剥注释时
    工具把 hello 当成「服务端发送但客户端不消费」的真缺口报出来。
    """
    tool = _load_tool()
    sample = 'x = {"type": "full_snapshot"}\n# 举例 {"type": "hello"}\n'
    stripped = tool._strip_comments(sample)
    assert '"full_snapshot"' in stripped
    assert '"hello"' not in stripped


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
def test_ghost_package_rule_actually_fires():
    """幽灵包规则必须真的会报——用构造目录验证，不依赖当前仓库状态。

    原钉依赖「sim/combat 仍是空壳」这一时点事实；2026-10-20 单 B 把该包
    docstring 改成现状后自然失效。改为直接喂构造包，规则永远有覆盖。
    """
    tool = _load_tool()
    tmp_pkg = _REPO / "sim" / "__ghost_probe__"
    tmp_pkg.mkdir(exist_ok=True)
    try:
        # 必须复刻被检出的真实形态：bullet 清单 `- 模块名  描述`
        (tmp_pkg / "__init__.py").write_text(
            '"""命名空间。\n\n模块划分：\n- exchange   交换单元\n- posture    姿态\n"""\n',
            encoding="utf-8",
        )
        problems = tool.check_ghost_packages()
        assert any("__ghost_probe__" in p for p in problems), (
            "空壳包声称子模块却未被报出——幽灵包规则失效"
        )
    finally:
        for f in tmp_pkg.iterdir():
            f.unlink()
        tmp_pkg.rmdir()


@pytest.mark.t1
def test_ghost_package_rule_ignores_honest_docstring():
    """如实描述现状的空壳包（不点名子模块）不得误报。"""
    tool = _load_tool()
    tmp_pkg = _REPO / "sim" / "__honest_probe__"
    tmp_pkg.mkdir(exist_ok=True)
    try:
        (tmp_pkg / "__init__.py").write_text(
            '"""战斗域命名空间；本包尚无子模块。"""\n', encoding="utf-8"
        )
        problems = tool.check_ghost_packages()
        assert not any("__honest_probe__" in p for p in problems)
    finally:
        for f in tmp_pkg.iterdir():
            f.unlink()
        tmp_pkg.rmdir()
