"""sim.agent.dialogue — 台词生成（批次 E1：对话的最小内容面）。

模板池按 (speaker, listener, tick) 哈希挑一句（C5 确定性，无 RNG 流）；
LLM 台词走 ChenmoDriver 构造注入的同步 provider（E1 不启用）。
台词是**外在可观察面**（对方听见了）→ 走 npc.chat 事件；不进独白面板。
出戏纪律：模板池词面全部过 banned_words.scan（测试钉）；拒绝操纵感语态。
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable

from sim.llm.prompts.banned_words import REWRITE_MAP, scan
from sim.npc.speech_register import SpeechContext, speech_register

#: 模板池（第一人称世界内台词；{listener} 为称呼占位）。
_CHAT_TEMPLATES: tuple[str, ...] = (
    "{listener}，忙着呢？",
    "{listener}，今天镇上有什么新鲜事？",
    "{listener}，回头来我铺子里坐坐。",
    "{listener}，这天看着要变，早些回去吧。",
    "{listener}，改天一起喝一杯。",
)


_REGISTER_TEMPLATES = {
    "粗": ("喂，{listener}，有事快说。", "{listener}，忙着呢，回头再说。"),
    "文雅": ("{listener}，您近来可好？", "{listener}，您得空不妨来坐坐。"),
    "日常": _CHAT_TEMPLATES,
}


def template_line(
    speaker: str, listener_name: str, tick: int, *, speech_context: SpeechContext | None = None
) -> str:
    """模板兜底：sha256(speaker:listener:tick) 挑句（C5 同输入同输出）。"""
    digest = hashlib.sha256(f"chat:{speaker}:{listener_name}:{tick}".encode()).digest()
    pool = (
        _REGISTER_TEMPLATES[speech_register(speech_context)] if speech_context else _CHAT_TEMPLATES
    )
    pick = int.from_bytes(digest[0:4], "big") % len(pool)
    return pool[pick].format(listener=listener_name)


def validate_provider_line(line: str) -> str | None:
    """Accept only short, single-line world speech; reject unsafe model output."""
    candidate = " ".join(line.strip().split())
    if not candidate or len(candidate) > 160 or scan(candidate).hits:
        return None
    try:
        json.loads(candidate)
    except json.JSONDecodeError:
        pass
    else:
        return None
    return candidate


def sanitize_provider_line(line: str) -> str | None:
    """复读剥离判梯（T4 泄漏修复,2026-10-11 实测四泄漏同形态）——同 memory_scan
    decide 判梯:命中 ≤2 且全部在 REWRITE_MAP → 机械改写后复扫放行;其余拒
    （调用方退模板池）。改写产物仍过 validate_provider_line 全部既有钉
    （长度/JSON/复扫）——不绕任何门。"""
    candidate = " ".join(line.strip().split())
    if not candidate or len(candidate) > 160:
        return None
    result = scan(candidate)
    if not result.hits:
        return _reject_json_or_pass(candidate)
    if len(result.hits) <= 2 and all(h.word in REWRITE_MAP for h in result.hits):
        cleaned = result.cleaned
        return validate_provider_line(cleaned)  # 改写产物复走全钉（含复扫）
    return None


def _reject_json_or_pass(candidate: str) -> str | None:
    try:
        json.loads(candidate)
    except json.JSONDecodeError:
        pass
    else:
        return None
    return candidate


DialogueProvider = Callable[[str, str, int], str | None]
