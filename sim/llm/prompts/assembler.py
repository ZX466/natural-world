"""prompt 装配器 — 每次决策的六段结构（DESIGN §8，TASK-C06-④）。

段序固定（前段可命中供应商前缀缓存）：
  [身份锚] → [记忆] → [处境] → [计划] → [输入] → [要求]

出戏边界防线（在装配层强制，不靠上游自觉）：
- 零元信息扫描：装配产物全文过 banned_words.scan()，命中即装配失败
  （装配产物是 LLM 出口，等同记忆出口的 S1 唯一入口原则）。
- entity_id/seed/tick 等字段只存在于装配输入（结构化对象），渲染函数
  的参数表里没有它们——类型签名即边界。
"""

from __future__ import annotations

from dataclasses import dataclass

import structlog
from pydantic import BaseModel, ConfigDict

from sim.llm.prompts.banned_words import scan
from sim.llm.prompts.identity import IdentityAnchor

logger = structlog.get_logger(__name__)

#: [要求] 段固定文本：Intent JSON 输出契约 + reason 第一人称世界内语言。
_REQUIREMENTS_TEXT = (
    "只输出一个 JSON 对象，字段：action（你要做的事，简短祈使句）、"
    "target（可选，对象或地点，用你看到的说法指代）、reason（你为什么"
    "这么做，用你自己的话，第一人称）。不要输出 JSON 以外的任何文字。"
)


class PromptAssemblyError(Exception):
    """装配产物命中禁词——拒绝出站（底线：残缺比出戏安全）。"""

    def __init__(self, hits: tuple[str, ...]) -> None:
        self.hits = hits
        super().__init__(f"prompt 禁词命中: {hits}")


@dataclass(frozen=True)
class MemorySlice:
    """[记忆] 段原料：已检索的 top-k 记忆文本（M1 阶段由上游检索给定）。"""

    entries: tuple[str, ...] = ()


@dataclass(frozen=True)
class NormSlice:
    """[规矩] 段原料：不成文规矩文本（M3 批次 D1；sim.npc.norms 产出）。

    逐条 = 知识行 fact（写入门已把关的世界内语言）；空集 = 段省略。
    """

    entries: tuple[str, ...] = ()


@dataclass(frozen=True)
class SituationSlice:
    """[处境] 段原料：感知帧叙事文本 + 内感受。"""

    perception_text: str = ""
    interoception_text: str = ""


@dataclass(frozen=True)
class PlanSlice:
    """[计划] 段原料：当前计划 + 上次意图的结果。"""

    current_plan: str = ""
    last_intent_result: str = ""


@dataclass(frozen=True)
class InputSlice:
    """[输入] 段原料：新念头 / 对方的话 / 事件（玩家注入在此，§10）。"""

    thought: str = ""
    dialogue: str = ""
    event: str = ""


class AssembledPrompt(BaseModel):
    """装配产物：messages 列表（messages[0]=身份锚，前缀缓存分界）。"""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    chain_id: str
    messages: tuple[dict[str, str], ...]

    def first_message_fingerprint(self) -> str:
        """messages[0] 指纹：llm.cache_hit 判定输入（C06-① 探针消费）。"""
        import hashlib

        if not self.messages:
            return ""
        blob = self.messages[0].get("content", "")
        return hashlib.sha256(blob.encode()).hexdigest()


def assemble_prompt(
    anchor: IdentityAnchor,
    memory: MemorySlice,
    situation: SituationSlice,
    plan: PlanSlice,
    user_input: InputSlice,
    chain_id: str,
    norms: NormSlice | None = None,
) -> AssembledPrompt:
    """六段装配 → 禁词终扫 → messages。装配失败抛 PromptAssemblyError。

    段序即缓存序：身份锚单独占 messages[0]（同 Agent 恒定 → 前缀缓存
    必命中）；其余五段合并为 messages[1]（每决策变化）。
    norms（M3 批次 D1）：[规矩] 段，[记忆] 之后 [处境] 之前；None/空 = 段省略
    （兼容既有调用形）。
    """
    sections: list[str] = []

    # [记忆]（top-k 已由检索端排序，这里只依序列出）
    if memory.entries:
        memories = "\n".join(f"- {m}" for m in memory.entries)
        sections.append(f"你还记得的事：\n{memories}")

    # [规矩]（M3 批次 D1）：不成文规矩，[记忆] 后 [处境] 前——先规矩后处境，
    # 行为约束在情境解读之前给出。
    if norms is not None and norms.entries:
        norm_lines = "\n".join(f"- {n}" for n in norms.entries)
        sections.append(f"这镇上不成文的规矩：\n{norm_lines}")

    # [处境]：感知帧叙事 + 内感受（内感受永远在最前——身体优先）
    situation_parts: list[str] = []
    if situation.interoception_text:
        situation_parts.append(situation.interoception_text)
    if situation.perception_text:
        situation_parts.append(situation.perception_text)
    if situation_parts:
        sections.append("\n".join(situation_parts))

    # [计划]
    plan_parts: list[str] = []
    if plan.current_plan:
        plan_parts.append(f"你正打算：{plan.current_plan}")
    if plan.last_intent_result:
        plan_parts.append(f"上次的结果：{plan.last_intent_result}")
    if plan_parts:
        sections.append("\n".join(plan_parts))

    # [输入]
    input_parts: list[str] = []
    if user_input.thought:
        input_parts.append(f"你心里冒出一个念头：{user_input.thought}")
    if user_input.dialogue:
        input_parts.append(f"有人对你说：{user_input.dialogue}")
    if user_input.event:
        input_parts.append(user_input.event)
    if input_parts:
        sections.append("\n".join(input_parts))

    sections.append(_REQUIREMENTS_TEXT)

    body = "\n\n".join(sections)
    messages = (
        {"role": "system", "content": anchor.render()},
        {"role": "user", "content": body},
    )

    # 出站终扫（S2 同一词表；装配出口 = LLM 出口，同 S1 唯一入口原则）
    hits: list[str] = []
    for text in (messages[0]["content"], messages[1]["content"]):
        result = scan(text)
        hits.extend(h.word for h in result.hits)
    if hits:
        logger.warning("prompt.banned_hit", chain_id=chain_id, hits=hits)
        raise PromptAssemblyError(tuple(hits))

    return AssembledPrompt(chain_id=chain_id, messages=messages)
