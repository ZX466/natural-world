"""交互中村民的异步 L2 决策：叙事输入、安全成品输出，不写世界或持久层。"""

from __future__ import annotations

import asyncio
import math
import os
import re
import time
import unicodedata
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from sim.agent.dialogue import sanitize_provider_line, template_line, validate_provider_line
from sim.llm.prompts.assembler import (
    InputSlice,
    MemorySlice,
    NormSlice,
    PlanSlice,
    SituationSlice,
    assemble_prompt,
)
from sim.llm.prompts.identity import IdentityAnchor
from sim.npc.contract import HiddenState
from sim.npc.speech_register import SpeechContext

if TYPE_CHECKING:
    from sim.llm.client import LlmCallResult, ProfileSnapshot
    from sim.npc.model import NpcProfileData

_Action = Literal["eat", "rest", "work", "wander", "request_chat"]
_ACTIONS = frozenset({"eat", "rest", "work", "wander", "request_chat"})
_NUMBERED_LEVEL = re.compile(
    r"(?i)(?<![a-z])(?:lod|band)(?![a-z])"
    r"|等级|档位|档号"
    r"|[零〇一二两三四五六七八九十百千万]+\s*[级档]"
)
_ROMAN_NUMBER = re.compile(r"(?<![a-z])[ivxlcdm]+(?![a-z])", re.IGNORECASE)
# These are vague everyday phrases, not numerical values or levels.
_EVERYDAY_PHRASES = ("一会儿", "一会", "一下", "一起", "一直", "一阵", "一边")
_OUTPUT_REQUIREMENTS = (
    "只输出一个 JSON 对象，且只能有 action、thought、line 这些字段。"
    "action 只能选 eat（吃东西）、rest（歇息）、work（做活）、"
    "wander（走走）、request_chat（与眼前的人交谈）。"
    "thought 是你此刻的一句简短心声，line 是要当面说的一句简短对白；"
    "这两个字段只写第一人称的日常话，不写标号、数值或称号之外的代号。"
    "不交谈时 line 留空；没有人在面前时不可选 request_chat。"
    "交谈时 line 不可为空，心声或对白须至少写出一句。"
    "不要输出这些字段以外的内容，也不要解释 JSON。"
)


class _LlmCompleter(Protocol):
    async def complete(
        self,
        profile: ProfileSnapshot,
        messages: list[dict[str, str]],
        *,
        max_tokens_override: int | None = None,
    ) -> LlmCallResult: ...


@dataclass(frozen=True)
class L2Decision:
    """只包含经过安全闸的成品；听者寻址只取调用方，不取模型文本。"""

    action: str
    thought: str = ""
    line: str = ""
    listener_id: str | None = None

    def __post_init__(self) -> None:
        if self.action not in _ACTIONS:
            raise ValueError("unsupported NPC L2 action")


@dataclass(frozen=True)
class L2Policy:
    """保守成本默认值；环境输入失败时维持默认值。"""

    min_interval_seconds: float = 60.0
    max_calls_per_minute: int = 4
    timeout_seconds: float = 8.0
    max_tokens: int = 192

    @classmethod
    def from_environment(cls) -> L2Policy:
        defaults = cls()
        interval = _environment_seconds(
            "NPC_L2_MIN_INTERVAL_SECONDS", defaults.min_interval_seconds, allow_zero=True
        )
        timeout = _environment_seconds("NPC_L2_TIMEOUT_SECONDS", defaults.timeout_seconds)
        try:
            limit = int(os.environ.get("NPC_L2_CALLS_PER_MINUTE", ""))
        except ValueError:
            limit = defaults.max_calls_per_minute
        if limit < 0:
            limit = defaults.max_calls_per_minute
        return cls(
            min_interval_seconds=max(5.0, interval),
            max_calls_per_minute=limit,
            timeout_seconds=timeout,
            max_tokens=defaults.max_tokens,
        )


def _environment_seconds(name: str, default: float, *, allow_zero: bool = False) -> float:
    try:
        value = float(os.environ.get(name, ""))
    except ValueError:
        return default
    if not math.isfinite(value) or value < 0 or (value == 0 and not allow_zero):
        return default
    return value


class _ModelDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    action: _Action
    thought: str = Field(default="", max_length=160)
    line: str = Field(default="", max_length=160)


class NpcL2Service:
    """最多一个在途调用；计费预留发生在第一次 await 之前，失败不退预算。"""

    def __init__(
        self,
        *,
        llm: _LlmCompleter,
        profile_provider: Callable[[], ProfileSnapshot | None],
        policy: L2Policy | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._llm = llm
        self._profile_provider = profile_provider
        self._policy = policy if policy is not None else L2Policy.from_environment()
        self._clock = clock
        self._call_starts: deque[float] = deque()
        self._last_started: dict[str, float] = {}
        self._busy = False

    async def decide_once(
        self,
        profile: NpcProfileData,
        *,
        perception: str,
        tick: int,
        listener_id: str | None = None,
        listener_name: str = "眼前的人",
        memory_entries: tuple[str, ...] = (),
        norms_entries: tuple[str, ...] = (),
        hidden: HiddenState | None = None,
        forbidden_ids: tuple[str, ...] = (),
    ) -> L2Decision | None:
        """一次 L2 尝试；无资格、无配置、忙或成本闸拒绝时保持 L1。"""
        if (
            self._busy
            or profile.species != "human"
            or profile.lod != 2
            or not profile.identity_anchor.strip()
            or self._policy.max_calls_per_minute <= 0
        ):
            return None
        now = self._clock()
        while self._call_starts and self._call_starts[0] <= now - 60.0:
            self._call_starts.popleft()
        last = self._last_started.get(profile.npc_id)
        if len(self._call_starts) >= self._policy.max_calls_per_minute or (
            last is not None and now - last < self._policy.min_interval_seconds
        ):
            return None
        try:
            active_profile = self._profile_provider()
            if active_profile is None or not all(
                value.strip()
                for value in (
                    active_profile.profile_name,
                    active_profile.base_url,
                    active_profile.model,
                    active_profile.api_key_plain,
                )
            ):
                return None
        except Exception:
            return None  # 解密或配置故障不泄漏详情，也不消耗模型预算。

        hidden_state = hidden if hidden is not None else HiddenState.empty()
        blocked = tuple(
            unicodedata.normalize("NFKC", entity_id).casefold()
            for entity_id in (profile.npc_id, listener_id or "", *forbidden_ids)
            if entity_id
        )
        speech_context = SpeechContext(profile.class_register, in_circle=False)

        def safe_text(text: str) -> str | None:
            if not text.strip():
                return ""
            candidate = sanitize_provider_line(text)
            if candidate is None:
                return None
            candidate = validate_provider_line(candidate)
            if candidate is None or hidden_state.check_reason(candidate):
                return None
            normalized = unicodedata.normalize("NFKC", candidate).casefold()
            numeric_text = candidate
            for phrase in _EVERYDAY_PHRASES:
                numeric_text = numeric_text.replace(phrase, "")
            if (
                any(char.isnumeric() for char in numeric_text)
                or _ROMAN_NUMBER.search(normalized)
                or _NUMBERED_LEVEL.search(normalized)
                or any(entity_id in normalized for entity_id in blocked)
            ):
                return None
            return candidate

        def fallback() -> L2Decision | None:
            if not listener_id:
                return None
            name = safe_text(listener_name) or "眼前的人"
            line = safe_text(
                template_line(profile.npc_id, name, tick, speech_context=speech_context)
            )
            if not line:
                return None
            return L2Decision("request_chat", line=line, listener_id=listener_id)

        try:
            listener_text = (
                f"{safe_text(listener_name) or '眼前的人'}正在面前，可以与其交谈。"
                if listener_id
                else "眼下没有人在面前，只能自己做事或想一想。"
            )
            prompt = assemble_prompt(
                anchor=IdentityAnchor(
                    entity_id=profile.npc_id,
                    self_narrative=profile.identity_anchor,
                    persona_summary="",
                    long_term_goal="",
                ),
                memory=MemorySlice(
                    entries=tuple(
                        text for text in memory_entries if not hidden_state.check_reason(text)
                    )
                ),
                norms=NormSlice(entries=norms_entries),
                situation=SituationSlice(perception_text=perception),
                plan=PlanSlice(),
                user_input=InputSlice(event=listener_text),
                chain_id=f"npc-l2-{tick}",
                speech_context=speech_context,
                output_requirements=_OUTPUT_REQUIREMENTS,
            )
        except Exception:
            return fallback()

        self._call_starts.append(now)
        self._last_started[profile.npc_id] = now
        self._busy = True
        try:
            result = await asyncio.wait_for(
                self._llm.complete(
                    active_profile,
                    list(prompt.messages),
                    max_tokens_override=self._policy.max_tokens,
                ),
                timeout=self._policy.timeout_seconds,
            )
            output = _ModelDecision.model_validate_json(result.content)
            thought = safe_text(output.thought)
            line = safe_text(output.line)
            if thought is None or line is None:
                return fallback()
            if not listener_id:
                line = ""
            if output.action == "request_chat" and (not listener_id or not line):
                return fallback()
            if not thought and not line:
                return fallback()
            return L2Decision(
                output.action,
                thought=thought,
                line=line,
                listener_id=listener_id if line else None,
            )
        except Exception:
            return fallback()  # 不记录模型原文或异常详情；取消属于 BaseException，继续向上抛。
        finally:
            self._busy = False
