"""Review 修复验证：C2 combat_provider 装配 + C3 retell_last 装配。

钉生产装配面（main.py lifespan 构造形）——修复前两处断线在测试里不可见。
用反射检查装配形而非起真 lifespan（lifespan 依赖 DB/世界初始化，单测不起）。
"""


from pathlib import Path

_MAIN = Path("sim/api/main.py").read_text(encoding="utf-8")


def test_driver_construction_passes_combat_provider():
    """C2：main.py 的 ChenmoDriver 构造必须注入 combat_provider。"""
    # 定位 lifespan 内的 ChenmoDriver(...) 调用块
    match = None
    for line in _MAIN.splitlines():
        if "ChenmoDriver(" in line:
            match = line
            break
    # 构造调用跨多行——抓 build_runtime_provider 之后 3 行内的 combat_provider
    assert match is not None, "main.py 无 ChenmoDriver 构造"
    lines = _MAIN.splitlines()
    start = next(i for i, ln in enumerate(lines) if "ChenmoDriver(" in ln)
    block = "\n".join(lines[start : start + 10])
    assert "combat_provider" in block, (
        "ChenmoDriver 构造缺 combat_provider——attack 生产不可达（review C2）"
    )
    assert "combat_ledger" in block or "CombatLedger" in _MAIN, (
        "main.py 无 CombatLedger 实例"
    )


def test_npc_events_for_tick_call_passes_retell_last():
    """C3：生产调用点必须传 retell_last（学舌通路）。"""
    lines = _MAIN.splitlines()
    start = next(
        i for i, ln in enumerate(lines) if "npc_events_for_tick(" in ln
    )
    block = "\n".join(lines[start : start + 14])
    assert "retell_last" in block, (
        "npc_events_for_tick 生产调用缺 retell_last——retell 死路（review C3）"
    )


def test_combat_ledger_instantiated_in_lifespan():
    """C2 配套：lifespan 里有 CombatLedger() 实例化并挂 app.state。"""
    assert "CombatLedger()" in _MAIN, "main.py 未实例化 CombatLedger"
    assert "app.state.combat_ledger" in _MAIN, "combat_ledger 未挂 app.state"
