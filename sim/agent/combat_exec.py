"""sim.agent.combat_exec — 战斗最小面（批次 E6；DESIGN §9 的 E 系缩水版）。

**范围裁决**：决策点制/交换单元/战斗时间尺切换见 Task 12（scale_change 接线）；
本模块只兑现「attack 是有牙齿的动作」：确定性结算（哈希掷点）→ hp 账本 →
死亡走既有 npc.death 事件（C4 零新增 kind）。hp/伤害数值零出戏
（铁律 1：独白只有叙事）；呼救是外在可观察 bubble。
C5：结算=sha256(attacker:target:tick:seed) 纯函数，无 RNG 流。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

#: 初始 hp（hits 量级；数值永不出戏）。
_DEFAULT_HP = 10

#: 呼救模板（外在可观察面；过 banned 扫描钉测试）。
HELP_TEMPLATES: tuple[str, ...] = (
    "来人啊！{attacker}动手了！",
    "救命！{attacker}疯了！",
    "乡亲们，{attacker}行凶了！",
)


def help_line(attacker_name: str, *, tick: int) -> str:
    """呼救句（确定性挑选，C5）。"""
    digest = hashlib.sha256(f"help:{attacker_name}:{tick}".encode()).digest()
    pick = int.from_bytes(digest[0:4], "big") % len(HELP_TEMPLATES)
    return HELP_TEMPLATES[pick].format(attacker=attacker_name)


@dataclass(frozen=True)
class AttackOutcome:
    """一次攻击结算（frozen；damage/hp 数值禁出戏内文本）。"""

    outcome: str  # "hit" | "miss" | "kill"
    damage: int
    target_hp: int
    critical: bool = False


def needs_critical_entropy(attacker: str, target: str, *, tick: int, seed: int) -> bool:
    digest = hashlib.sha256(f"combat:{attacker}:{target}:{tick}:{seed}".encode()).digest()
    return int.from_bytes(digest[:4], "big") % 100 >= 80


def entropy_roll(material_hex: str) -> float:
    """Map recorded inject material to a replayable unit roll."""
    from sim.core.events import EntropyInjectPayload

    payload = EntropyInjectPayload(stream="combat.critical", material=material_hex)
    material = bytes.fromhex(payload.material)
    return int.from_bytes(material, "big") / (1 << (8 * len(material)))


def settle_attack(
    attacker: str,
    target: str,
    *,
    tick: int,
    seed: int,
    entropy_roll: float | None = None,
) -> AttackOutcome:
    """纯结算（不改账本）：25% miss / 55% hit(2-4) / 20% crit(6-9)。

    hp 口径：本函数按**满血**算 target_hp（纯函数不读账本）；账本扣血由
    CombatLedger.apply_attack 负责（kill 判定在那边）。
    """
    digest = hashlib.sha256(f"combat:{attacker}:{target}:{tick}:{seed}".encode()).digest()
    roll = int.from_bytes(digest[0:4], "big") % 100
    if roll < 25:
        return AttackOutcome(outcome="miss", damage=0, target_hp=_DEFAULT_HP)
    dmg = 2 + int.from_bytes(digest[4:8], "big") % 3
    critical = roll >= 80 and (entropy_roll is None or entropy_roll < 0.2)
    if critical:
        dmg = 6 + int.from_bytes(digest[8:12], "big") % 4
    return AttackOutcome(
        outcome="hit", damage=dmg, target_hp=max(0, _DEFAULT_HP - dmg), critical=critical
    )


class CombatLedger:
    """{entity_id: hp} 进程内账本（死亡=事件，账本只服务实况结算）。"""

    def __init__(self) -> None:
        self._hp: dict[str, int] = {}

    def hp_of(self, entity_id: str) -> int:
        return self._hp.get(entity_id, _DEFAULT_HP)

    def reset(self) -> None:
        """清空 hp 账本（读档=分叉：旧分支 hp 残留会「一刀秒杀」——review I2）。"""
        self._hp.clear()

    def apply_attack(
        self,
        attacker: str,
        target: str,
        *,
        tick: int,
        seed: int,
        entropy_roll: float | None = None,
    ) -> AttackOutcome:
        """结算并扣血；hp 归零 → outcome=kill（死亡事件由调用方发——C4）。"""
        out = settle_attack(
            attacker, target, tick=tick, seed=seed, entropy_roll=entropy_roll
        )
        if out.outcome == "miss":
            return out
        new_hp = max(0, self.hp_of(target) - out.damage)
        self._hp[target] = new_hp
        if new_hp == 0:
            return AttackOutcome(
                outcome="kill", damage=out.damage, target_hp=0, critical=out.critical
            )
        return AttackOutcome(
            outcome="hit", damage=out.damage, target_hp=new_hp, critical=out.critical
        )
