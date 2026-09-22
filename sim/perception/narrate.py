"""感知叙事化 — 世界状态 → 世界内语言（DESIGN §7「感官流的转换规则」）。

铁律落地点：
- 数值永不出（hp:30 → 「左肋疼得厉害」，绝不「生命值 30」）
- 动机永不出（trust:-20 → 「他看我的眼神不太对」——行为描述，零关系数值）
- 时间零元信息（tick → 「天色暗下来了」，由叙事端从 tick 派生，不出现数字）

模板函数全部纯函数、中文世界内语言。M1 覆盖 §7 表格的五类转换 +
移动/战斗/位置类观测；更细腻的变化 M2 非理性框架时再扩。
"""

from __future__ import annotations

from sim.core.calendar import DayPhase, phase_of_day
from sim.perception.frame import Channel, Observation


def narrate_hp(fraction: float) -> str:
    """hp 比例 → 身体感受（铁律 7：必须有身体）。fraction ∈ [0,1]。"""
    if fraction >= 0.9:
        return "身子骨还算硬朗。"
    if fraction >= 0.6:
        return "身上有些地方隐隐作痛。"
    if fraction >= 0.3:
        return "伤处疼得厉害，喘气都得收着点。"
    if fraction > 0.0:
        return "眼前阵阵发黑，每一口气都像从水里捞上来的。"
    return "身子已经不听使唤了。"


def narrate_hunger(fraction: float) -> str:
    """饥饿 0..1（1=极饿）→ 内感受。"""
    if fraction >= 0.8:
        return "肚子空得有点发慌，眼前有点发飘。"
    if fraction >= 0.5:
        return "肚子咕咕叫，该寻摸点吃的了。"
    if fraction >= 0.2:
        return "有点饿了。"
    return "肚子里还挺踏实。"


def narrate_time(tick: int) -> str:
    """tick → 天色感受（时间零元信息：绝不出现数字）。"""
    phase = phase_of_day(tick)
    if phase is DayPhase.DAWN:
        return "天刚蒙蒙亮。"
    if phase is DayPhase.DAY:
        return "日头正好。"
    if phase is DayPhase.DUSK:
        return "天色暗下来了。"
    return "夜深了，四下里黑漆漆的。"


def narrate_motion(rtoken_label: str) -> str:
    """看见某人移动 → 行为描述。只有行为，没有动机（社会未知）。"""
    return f"{rtoken_label}正朝这边走。"


def narrate_move_end(rtoken_label: str) -> str:
    """看见某人停下。"""
    return f"{rtoken_label}停下了脚步。"


def narrate_sound(kind: str, rtoken_label: str | None) -> str:
    """听觉观测 → 声音描述。穿墙/远距时自然带出闷响感由强度决定（装配端）。"""
    subjects = f"，像是{rtoken_label}" if rtoken_label else ""
    kinds = {
        "footstep": "传来一阵脚步声",
        "door": "有扇门开了又关",
        "combat": "那边传来打斗的响动",
        "shout": "有人喊了一嗓子",
    }
    return kinds.get(kind, "有些动静") + subjects + "。"


def narrate_presence(rtoken_label: str) -> str:
    """视觉静态存在（看见一个人站在那）。"""
    return f"{rtoken_label}就在不远处。"


def narrate_smell(concentration: float) -> str:
    """嗅觉浓度（场采样值，内部量）→ 气味描述。零数值零系统词（铁律 1）。

    分档只按浓淡，不带来源方向（风向叙事 M3 起；现批次浓度→文案占位映射）。
    """
    if concentration >= 2.0:
        return "一股浓重的气味直冲鼻子。"
    if concentration >= 0.5:
        return "空气里飘着一股明显的味道。"
    if concentration >= 0.1:
        return "空气里飘着一股说不清的味道。"
    return "隐约有一丝陌生的气味。"


def make_observation(
    channel: Channel, subject: str, description: str, strength: float
) -> Observation:
    """观测构造统一入口（保持 frame.Observation 的 frozen 语义）。"""
    return Observation(channel=channel, subject=subject, description=description, strength=strength)
