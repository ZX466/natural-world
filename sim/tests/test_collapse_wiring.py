"""DA-07 收口：坍塌致伤必须接进生产维护钩子（不只是存在一个没人调的函数）。

用反射检查装配形而非起真 lifespan（lifespan 依赖 DB/世界初始化），
与 ``test_e_fix_production_wiring.py`` 同口径。
"""

from pathlib import Path

_MAIN = Path("sim/api/main.py").read_text(encoding="utf-8")


def test_maintenance_hook_uses_injury_wiring():
    """维护钩子必须产「坍塌 + 致伤」同批事件，而不是裸 ``maintenance.tick``。"""
    lines = _MAIN.splitlines()
    start = next((i for i, line in enumerate(lines) if "def _maintenance_tick_hook" in line), None)
    assert start is not None, "main.py 没有维护钩子"
    block = "\n".join(lines[start : start + 12])
    assert "tick_with_injuries" in block, "维护钩子没接坍塌致伤——结构塌了不伤人（DA-07 缺口）"


def test_maintenance_hook_passes_combat_ledger():
    """致伤需要 hp 账本；账本必须早于钩子创建并挂 app.state。"""
    hook_at = _MAIN.index("def _maintenance_tick_hook")
    ledger_at = _MAIN.index("combat_ledger = CombatLedger()")
    assert ledger_at < hook_at, "combat_ledger 晚于维护钩子定义——钩子会读不到"
    assert "app.state.combat_ledger = combat_ledger" in _MAIN
