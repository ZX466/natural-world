"""Intent — LLM 唯一能输出的东西（DESIGN §6 契约，C06-⑤）。

schema 化（codex 意见 7 同款）：Literal 枚举 action + 显式字段 +
extra="forbid"。LLM 原始 JSON 经 parse_intent 严格校验后才能进闸门；
解析失败 = 结构化拒绝（幻觉隔离铁律 4 的第一道）。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

IntentAction = Literal[
    "move_to",
    "talk_to",
    "take",
    "give",
    "buy",
    "sell",
    "build",
    "demolish",
    "attack",
    "flee",
    "use",
    "wait",
    "investigate",
]


class Intent(BaseModel):
    """结构化意图。reason 是独白唯一来源（第一人称世界内语言）。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    action: IntentAction
    target_id: str | None = None
    target_pos: tuple[int, int] | None = None
    params: dict[str, str] = Field(default_factory=dict)
    reason: str
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


#: confidence 低于此值触发重新规划（DESIGN §6）。
REPLAN_CONFIDENCE_THRESHOLD = 0.5


class IntentParseError(Exception):
    """LLM 输出无法解析为合法 Intent。detail 是结构化拒绝原因（不出戏）。"""

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)


def parse_intent(raw: str) -> Intent:
    """LLM 原始输出 → Intent。任何偏差都结构化拒绝，绝不猜测修正。

    拒绝原因（detail）只描述结构问题，供重规划；不含 LLM 原文
    （原文只进开发日志，永不进戏内通道）。
    """
    import json
    import re

    # 提取 JSON 块：容忍 ```json 围栏（LLM 常见输出形态），其余一律拒绝
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if match is None:
        raise IntentParseError("no_json_object")
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        raise IntentParseError("malformed_json") from None
    if not isinstance(data, dict):
        raise IntentParseError("not_an_object")
    try:
        return Intent.model_validate(data)
    except ValidationError as exc:
        # 只报字段级错误码，不透传模型原文；extra 字段不落名字（防侧信道）
        errors = exc.errors()
        extra = any(err["type"] == "extra_forbidden" for err in errors)
        if extra:
            raise IntentParseError("extra_fields") from None
        fields = sorted({str(err["loc"][0]) for err in errors if err["loc"]})
        raise IntentParseError(f"invalid_fields:{','.join(fields)}") from None
