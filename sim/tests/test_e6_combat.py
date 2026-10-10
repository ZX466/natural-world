"""E6：战斗最小面——确定性结算 + 死亡事件 + 呼救。"""

from dataclasses import is_dataclass

from sim.agent.combat_exec import (
    HELP_TEMPLATES,
    AttackOutcome,
    CombatLedger,
    help_line,
    needs_critical_entropy,
    settle_attack,
)
from sim.llm.prompts.banned_words import scan


def test_settle_deterministic():
    a = settle_attack("chenmo", "villager_03", tick=777, seed=42)
    b = settle_attack("chenmo", "villager_03", tick=777, seed=42)
    assert a == b  # C5 同输入同输出
    assert a.outcome in ("hit", "miss", "kill")
    assert 0 <= a.damage <= 9


def test_critical_candidate_uses_recorded_entropy():
    tick = next(
        t
        for t in range(1000)
        if needs_critical_entropy("chenmo", "villager_03", tick=t, seed=42)
    )
    critical = settle_attack("chenmo", "villager_03", tick=tick, seed=42, entropy_roll=0.1)
    ordinary = settle_attack("chenmo", "villager_03", tick=tick, seed=42, entropy_roll=0.9)

    assert critical.critical is True
    assert critical.damage >= 6
    assert ordinary.critical is False
    assert ordinary.damage <= 4


def test_kill_when_hp_depleted():
    led = CombatLedger()
    tick = 100
    killed = False
    for i in range(200):  # 上限防御（miss 不会耗血，但 200 轮必出 kill 序列）
        outcome = led.apply_attack("chenmo", "villager_03", tick=tick + i, seed=42)
        if outcome.outcome == "kill":
            killed = True
            break
    assert killed
    assert led.hp_of("villager_03") == 0


def test_miss_does_not_lower_hp():
    led = CombatLedger()
    # 找一个必 miss 的 tick（扫 1000 个 tick,sha256 均匀分布必有 <25% 段）
    for t in range(1000):
        out = settle_attack("chenmo", "villager_09", tick=t, seed=42)
        if out.outcome == "miss":
            hp = led.hp_of("villager_09")
            led.apply_attack("chenmo", "villager_09", tick=t, seed=42)
            assert led.hp_of("villager_09") == hp
            return
    raise AssertionError("1000 tick 内无 miss（概率不可能）")


def test_outcome_frozen():
    assert is_dataclass(AttackOutcome)


def test_help_templates_clean():
    for t in HELP_TEMPLATES:
        assert not scan(t).hits


def test_help_template_format_and_determinism():
    line = help_line("赵铁柱", tick=5)
    assert "赵铁柱" in line
    assert line == help_line("赵铁柱", tick=5)  # C5
