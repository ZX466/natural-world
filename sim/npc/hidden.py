"""自我未知数据标注与信息闸门 — 隐藏创伤属性的安全边界（DESIGN §16，M2-S1）。

规范全文：docs/security/self-unknown.md（安全域维护）。本模块是它的实现：
- 数据标注：HiddenAttribute/HiddenProfile —— NPC 健康档（疾病/旧伤/成瘾/残疾）
  与创伤应激里被标为「隐藏」的属性，携带世界内直陈词面（descriptors）与
  情境触发条件（triggers）；
- 情境触发：evaluate_triggers() —— 当前处境文本命中触发条件 → 属性本 tick 浮现；
- 泄漏扫描：hidden_leak_scan() —— 未触发隐藏属性被直陈即命中，供闸门
  （执行时二次校验）与记忆写入管线（拒写）共用——同一工具，禁两处维护。

直陈 vs 行为暗示（M2-S1 任务书口径）：扫描面 = 属性的世界内直陈词面，
不含行为描述词——走路瘸/回避话题等行为暗示可议，不做闸门拒绝。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict

#: 隐藏属性类别：DESIGN §13 健康四类 + §8 创伤应激。
HiddenCategory = Literal["disease", "old_injury", "addiction", "disability", "trauma"]


class HiddenAttribute(BaseModel):
    """一条隐藏属性标注（健康档隐藏项或创伤应激触发项）。

    id 是稳定戏外主键：不进入任何戏内/prompt 面（同 banned_words 字段纪律）。
    descriptors 是「直陈面」：独白/记忆里直接说出该属性会用到的话，泄漏扫描面。
    triggers 是「情境触发面」：对 Agent 当前处境文本（感知帧叙事+内感受）子串匹配，
    命中任一 → 本 tick 浮现（visible = triggered）。
    """

    model_config = ConfigDict(frozen=True)

    id: str
    category: HiddenCategory
    label: str  # 世界内指称（文档/调试用，本身也是直陈词面之一）
    descriptors: tuple[str, ...]
    triggers: tuple[str, ...]


class HiddenProfile(BaseModel):
    """一个 NPC 的隐藏属性全集（与 opencode 0004 健康档持久化对齐的标注层）。"""

    model_config = ConfigDict(frozen=True)

    npc_id: str
    attributes: tuple[HiddenAttribute, ...] = ()

    def by_id(self, attr_id: str) -> HiddenAttribute | None:
        """按稳定主键取属性（无则 None）。"""
        for attr in self.attributes:
            if attr.id == attr_id:
                return attr
        return None


def evaluate_triggers(profile: HiddenProfile, context_text: str) -> frozenset[str]:
    """情境触发评估：context_text 命中某属性的任一 triggers → 该属性本 tick 浮现。

    纯函数、无状态：触发窗口按 tick 重估（self-unknown.md §2），调用方
    （感知引擎/行为循环，Claude 架构域）每 tick 对 Agent 自身处境文本调用，
    把返回的 triggered 集合传给独白装配、闸门与记忆写入管线。
    """
    triggered: set[str] = set()
    for attr in profile.attributes:
        if any(keyword in context_text for keyword in attr.triggers):
            triggered.add(attr.id)
    return frozenset(triggered)


@dataclass(frozen=True)
class HiddenLeak:
    """一处直陈泄漏命中。span 为 text[start:end] 切片坐标（同 banned_words.Hit）。"""

    attr_id: str
    word: str
    start: int
    end: int


def _descriptor_pattern(word: str) -> re.Pattern[str]:
    """直陈词面编译：ASCII 走词边界（防 leg 误中 legacy），CJK 走转义子串。"""
    if word.isascii():
        return re.compile(rf"(?i)(?<![0-9A-Za-z_]){re.escape(word)}(?![0-9A-Za-z_])")
    return re.compile(re.escape(word))


def hidden_leak_scan(
    text: str, profile: HiddenProfile, triggered: frozenset[str]
) -> tuple[HiddenLeak, ...]:
    """未触发隐藏属性的直陈扫描。

    triggered 中的属性已浮现 → 允许直陈；其余属性被直陈 → 泄漏命中。
    返回按文本出现顺序排列的命中列表；处置（闸门拒绝/记忆拒写）由调用方定。
    """
    hits: list[HiddenLeak] = []
    for attr in profile.attributes:
        if attr.id in triggered:
            continue
        for word in attr.descriptors:
            pattern = _descriptor_pattern(word)
            for match in pattern.finditer(text):
                hits.append(
                    HiddenLeak(
                        attr_id=attr.id,
                        word=word,
                        start=match.start(),
                        end=match.end(),
                    )
                )
    return tuple(sorted(hits, key=lambda hit: (hit.start, hit.end)))
