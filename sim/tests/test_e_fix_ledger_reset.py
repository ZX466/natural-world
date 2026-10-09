"""Review 修复验证：I2 分叉账本泄漏——三账本必须有 reset 且语义正确。

修复前：读档=分叉后 CombatLedger/CoinLedger/ChatLedger 残留旧分支状态
（旧分支打到 hp=2 的人在新分支满血在场——一刀秒杀）。
"""

from sim.agent.combat_exec import CombatLedger
from sim.npc.chat_ledger import ChatLedger
from sim.world.economy import CoinLedger


def test_combat_ledger_reset_restores_full_hp():
    led = CombatLedger()
    led.apply_attack("chenmo", "villager_03", tick=1, seed=42)
    assert led.hp_of("villager_03") < 10  # 有伤
    led.reset()
    assert led.hp_of("villager_03") == 10  # 新分支：满血


def test_coin_ledger_reset_clears_balances():
    led = CoinLedger()
    led.apply_grant("chenmo", 100, tick=1)
    led.reset()
    assert led.balance_of("chenmo") == 0


def test_chat_ledger_reset_clears_both():
    led = ChatLedger()
    led.adjust("a", "b", kind="chat")
    led.remember("a", "旧分支的话", tick=1)
    led.reset()
    assert len(led) == 0
    assert led.memories_of("a") == []
