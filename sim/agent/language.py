"""sim.agent.language — 语言判定与叙事降质（M2-A2 第三批；m2-npc-cognition §5.2）。

职责边界：
- **纯函数层，零 LLM**：判定只看 LanguageProfile（按角色构造，0004 夹具命名）
  与文本词面；「有音无义」「没听明白」的变体在此层产出，不碰感知帧数据；
- **只动叙事层文本**：Observation/PerceptionFrame 的原始数据保持完整
  （M3 知识传播前提，kilo M2-K1 意见④）；挂载点 = narrated() 装配内、
  通道分组输出前；
- **出戏三红线**（K1 实测 banned_words.scan() 0 命中口径）：降质文案零数值
  零系统词；literacy 只做阈值判据绝不进文本；接口面不变（perception
  消息 content string，判据字段不出 WS）。

M2 内容常量：识字阈值 0.5（低于即「有音无义」）、阶层可懂行话的档位差
（士绅/行内 vs 平民）——调参基准 M3 用 T1 采样数据回填。
"""

from __future__ import annotations

import json
from dataclasses import dataclass

#: 识字判定阈值：literacy 低于此值，识字类观察降质为「有音无义」。
LITERACY_THRESHOLD: float = 0.5

#: 阶层档位：能听懂行话的 class_register 集合（M2 两档占位；M3 扩五档）。
JARGON_LITERATE_REGISTERS: frozenset[str] = frozenset({"士绅", "行内"})

#: 识字类观察降质变体（世界内语言；零数值零系统词）。
ILLITERATE_VARIANT: str = "有块布告，画着些看不懂的符号。"
#: 行话降质变体。
JARGON_VARIANT: str = "他说的几个词你没听明白。"


class LanguageError(ValueError):
    """语言档参数非法。"""


@dataclass(frozen=True)
class LanguageProfile:
    """一个角色的语言能力档（按角色构造；数据层 npc_profiles.knowledge_boundary）。

    - `literacy`：识字率 0..1（只做阈值判据，绝不进文本——红线 2）；
    - `jargon`：世界行话/阶层用语词表（Sequence[str]，JSON list 对齐 0004 夹具）；
    - `class_register`：阶层用语档（夹具值域如「平民」；行话可懂性判据）。
    """

    literacy: float = 1.0
    jargon: tuple[str, ...] = ()
    class_register: str = "平民"

    def __post_init__(self) -> None:
        if not 0.0 <= self.literacy <= 1.0:
            raise LanguageError(f"literacy 越界: {self.literacy}")

    @staticmethod
    def from_json(raw: str) -> LanguageProfile:
        """knowledge_boundary JSON 文本 → LanguageProfile（非法/缺省宽容）。"""
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            data = {}
        if not isinstance(data, dict):
            data = {}
        literacy = float(data.get("literacy", 1.0))
        jargon = tuple(str(x) for x in (data.get("jargon") or ()))
        register = str(data.get("class_register", "平民"))
        return LanguageProfile(literacy=literacy, jargon=jargon, class_register=register)


def degrade_observation_text(text: str, kind: str, profile: LanguageProfile) -> str:
    """单条观测文本的语言降质（纯函数；不降质原样返回）。

    - kind="written" 且 literacy < LITERACY_THRESHOLD → 有音无义变体；
    - kind="speech" 且文本命中 jargon 词表、听者阶层听不懂 → 没听明白变体；
    - 其余恒等（高分识字/无行话/士绅阶层）。
    """
    if kind == "written":
        if profile.literacy < LITERACY_THRESHOLD:
            return ILLITERATE_VARIANT
        return text
    if kind == "speech":
        if profile.class_register not in JARGON_LITERATE_REGISTERS and any(
            j in text for j in profile.jargon
        ):
            return JARGON_VARIANT
        return text
    msg = f"观测语言面 kind 非法: {kind!r}（合法 written|speech）"
    raise LanguageError(msg)
