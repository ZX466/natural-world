"""感知帧 — Agent 在某一 tick 收到的完整感官流（DESIGN §7/§8 [处境] 段原料）。

信息边界 C2 的产出物：世界状态进来，叙事化感知出去。
铁律一（动机永不输出）：Observation 只有行为描述字段，没有数值关系字段——
类型系统层面就不可能把 trust/affection 装进感知帧。
铁律二（零元信息）：帧内不含 tick/seed/entity_id 等出戏字段；
对外标识一律 rtoken（与 WS 网关同一派生函数，全项目一个真相源）。
"""

from __future__ import annotations

import enum
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from sim.agent.language import LanguageProfile


class Channel(enum.StrEnum):
    """M1 通道：视/听/触/内感受；M2 增嗅觉。"""

    VISION = "vision"
    HEARING = "hearing"
    TOUCH = "touch"
    INTEROCEPTION = "interoception"
    SMELL = "smell"


class Observation(BaseModel):
    """一条感知观测。strength 只用于排序/门控，装配叙事时不出现在文本里。"""

    model_config = ConfigDict(frozen=True)

    channel: Channel
    subject: str  # rtoken（行为主体，戏外唯一标识；绝不 entity_id）
    description: str  # 世界内语言（已叙事化）
    strength: float  # 显著性 0..1（不进 prompt 文本，仅供装配排序）


class PerceptionFrame(BaseModel):
    """一个 Agent 一帧的感知。observations 已按 (channel, -strength, subject) 排序。"""

    model_config = ConfigDict(frozen=True)

    observer: str  # rtoken
    tick: int  # 戏外坐标（进 debug 层与测试断言；装配 prompt 时由叙事层消费，不出戏）
    observations: tuple[Observation, ...] = ()
    light: float = 1.0  # 本帧光照修正系数（debug/测试用，不进 prompt）

    def narrated(
        self,
        language: LanguageProfile | None = None,
        channel_kinds: dict[str, str] | None = None,
    ) -> str:
        """[处境] 段感知文本：纯第一人称世界内语言，零元信息。

        内感受与触觉直接出，视听按通道分组，嗅觉殿后。空帧 → 「四周很安静。」
        language（sim.agent.language.LanguageProfile）传入时，视听文本在分组
        输出前按角色语言档降质（M2 §5.2；channel_kinds = subject → "written"/"speech"，
        视觉缺省 "written"、听觉缺省 "speech"）。降质只动叙事层文本——
        self.observations 原始数据保持完整（M3 知识传播前提）。
        缺省无 language → 与 M1 叙事逐字节一致（零回归）。
        """
        if not self.observations:
            return "四周很安静。"
        lines: list[str] = []
        by_channel: dict[Channel, list[Observation]] = {}
        for ob in self.observations:
            by_channel.setdefault(ob.channel, []).append(ob)
        if (intero := by_channel.get(Channel.INTEROCEPTION)) is not None:
            lines.extend(ob.description for ob in intero)
        if (touch := by_channel.get(Channel.TOUCH)) is not None:
            lines.extend(ob.description for ob in touch)
        kinds = channel_kinds or {}
        for ch in (Channel.VISION, Channel.HEARING):
            obs = by_channel.get(ch)
            if not obs:
                continue
            texts = [ob.description for ob in obs]
            if language is not None:
                from sim.agent.language import degrade_observation_text

                default_kind = "written" if ch is Channel.VISION else "speech"
                texts = [
                    degrade_observation_text(t, kinds.get(ob.subject, default_kind), language)
                    for ob, t in zip(obs, texts, strict=True)
                ]
            if ch is Channel.VISION:
                lines.append("你看到：" + "；".join(texts) + "。")
            else:
                lines.append("你听到：" + "；".join(texts) + "。")
        if (smell := by_channel.get(Channel.SMELL)) is not None:
            lines.append("你闻到：" + "；".join(ob.description for ob in smell) + "。")
        return "\n".join(lines)

    def to_debug_dict(self) -> dict[str, Any]:
        """戏外调试视图（跑通链路/测试断言用；绝不经此直连 prompt）。"""
        return self.model_dump()
