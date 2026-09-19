"""禁词单一数据源（M1-A/M1-G + memory-scan.md §2）。

设计要点（memory-scan.md §2 / cline TASK-001 评审意见）：
- 分词：ASCII 词走 \\b 词边界正则（防 maintain 误中 ai、unlucky 误中 luck）；
  CJK 词面直接子串匹配（中文无词边界概念，靠例外表防误伤）。
- 大小写：全表不敏感（AI/ai/Ai 一视同仁）。
- 误报白名单：命中文本先查例外词表，例外区间不计命中（模特儿/棋子运气）。
- 数值+字段名模式（hunger:72 / energy=30）：M1-H 同款拦截，正则实现。
- 扫描范围写死：只扫 prompt 文本/记忆内容/独白/戏内 UI 等叙事文本；
  代码/配置/日志/事件 payload 的 tick、seed 等技术字段不在本模块职责内
  （调用方约束——本模块只提供 scan(text) 纯函数，不做路径遍历）。
- 纯函数、模块级编译一次、无 I/O（方便单测与热路径复用）。

维护纪律：改词面/例外/映射表必须走 CR（安全域 owner：Codex）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# 词表 —— 单一真相源（M1-A 硬词 + M1-G 持久化词汇）
# ---------------------------------------------------------------------------

# M1-A 硬词（m1-checklist.md M1-A 全集）
BANNED_WORDS_META: frozenset[str] = frozenset(
    {
        "AI",
        "模型",
        "模拟",
        "游戏",
        "角色扮演",
        "tick",
        "entity_id",
        "玩家",
        "运气",
        "luck",
        "seed",
        "随机数",
        "重开",
        "重来一次",
        "存档",
        "读档",
        "profile",
        "prompt",
        "token",
    }
)

# M1-G 持久化词汇（铁律 5：无存档意识）
BANNED_WORDS_PERSIST: frozenset[str] = frozenset(
    {
        "分支",
        "branch",
        "abandoned",
        "重放",
        "快照",
        "回放",
        "snapshot",
    }
)

#: 全部禁词（M1-A + M1-G）。消费方一律用这个集合，不要分别引用。
BANNED_WORDS: frozenset[str] = BANNED_WORDS_META | BANNED_WORDS_PERSIST

# ---------------------------------------------------------------------------
# 例外表（误报白名单）—— 变更走 CR
# ---------------------------------------------------------------------------

#: 例外词面 → 该区间内的禁词命中全部豁免。
#: - 模特儿：含「模」但与「模型」语义无关；
#: - 棋子运气：戏内棋牌话题，「运气」是正当戏内词。
#: 匹配采用不区分大小写（ASCII 部分生效）。
WHITELIST_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE) for p in (r"模特儿", r"棋子运气", r"手气好")
)

# ---------------------------------------------------------------------------
# 改写映射表（memory-scan.md §3：词面级机械替换，不做语义重写）
# ---------------------------------------------------------------------------

#: 禁词 → 世界内等价物。映射表与词表同模块维护（漂移即 CI 红）。
#: 注意：「重开」「重来一次」「读档」刻意不进映射表——记忆里出现「从头再来」
#: 语义即存档意识，按设计直接拒写（memory-scan.md §3 示例明确）。
REWRITE_MAP: dict[str, str] = {
    "游戏": "日子",
    "tick": "时辰",
    "存档": "账册",
    "玩家": "主顾",
    "运气": "手气",
    "luck": "手气",
    "快照": "留影",
    "回放": "复述",
    "分支": "岔路",
}

# ---------------------------------------------------------------------------
# 数值+字段名模式（M1-H：hunger:72 / energy=30 类拦截）
# ---------------------------------------------------------------------------

# 注意：不用 \b（在 CJK 与 ASCII 交界不成立），用显式 ASCII 边界环视。
_NUMBER_FIELD_RE = re.compile(
    r"(?i)(?<![0-9A-Za-z_])(hunger|energy|mood|health|stamina|fatigue|xp|hp|mp)\s*[:：=]\s*\d+"
)

# ---------------------------------------------------------------------------
# 编译产物（模块级一次）
# ---------------------------------------------------------------------------

#: ASCII 词面（含下划线的 entity_id）→ 词边界正则；CJK → 转义子串正则。
_ASCII_BANNED = sorted(w for w in BANNED_WORDS if w.isascii())
_CJK_BANNED = sorted(w for w in BANNED_WORDS if not w.isascii())

_ASCII_RES: tuple[re.Pattern[str], ...] = tuple(
    re.compile(rf"(?i)(?<![0-9A-Za-z_]){re.escape(w)}(?![0-9A-Za-z_])") for w in _ASCII_BANNED
)
_CJK_RES: tuple[re.Pattern[str], ...] = tuple(re.compile(re.escape(w)) for w in _CJK_BANNED)

_WORD_BY_LOWER = {w.lower(): w for w in BANNED_WORDS}


@dataclass(frozen=True)
class Hit:
    """一处禁词命中。span 为 text[start:end] 的切片坐标。"""

    word: str
    start: int
    end: int
    kind: str  # "meta" | "persist" | "number_field"


@dataclass(frozen=True)
class ScanResult:
    """scan() 产出：hits 供拒绝/观测，cleaned 供改写路径复扫。"""

    hits: tuple[Hit, ...] = ()
    cleaned: str = ""

    @property
    def ok(self) -> bool:
        return not self.hits


def _in_whitelisted_span(text: str, start: int, end: int) -> bool:
    """命中区间是否落在例外词面内（模特儿/棋子运气/手气好）。"""
    for wp in WHITELIST_PATTERNS:
        for m in wp.finditer(text):
            if m.start() <= start and end <= m.end():
                return True
    return False


def scan(text: str) -> ScanResult:
    """扫描叙事文本中的出戏禁词。纯函数：无 I/O、不改全局、可随意复扫。

    返回 hits（含坐标，供观测与单测）与 cleaned（机械替换后的文本——
    cleaned 仅对可映射词生效，调用方仍须对 cleaned 复扫，见 memory-scan §3）。
    """
    hits: list[Hit] = []

    def _collect(match: re.Match[str], kind: str) -> None:
        if _in_whitelisted_span(text, match.start(), match.end()):
            return
        word = _WORD_BY_LOWER.get(match.group(0).lower(), match.group(0))
        hits.append(Hit(word=word, start=match.start(), end=match.end(), kind=kind))

    for word, rx in zip(_ASCII_BANNED, _ASCII_RES, strict=True):
        kind = "persist" if word in BANNED_WORDS_PERSIST else "meta"
        for m in rx.finditer(text):
            _collect(m, kind)
    for word, rx in zip(_CJK_BANNED, _CJK_RES, strict=True):
        kind = "persist" if word in BANNED_WORDS_PERSIST else "meta"
        for m in rx.finditer(text):
            if _in_whitelisted_span(text, m.start(), m.end()):
                continue
            hits.append(Hit(word=word, start=m.start(), end=m.end(), kind=kind))
    for m in _NUMBER_FIELD_RE.finditer(text):
        hits.append(Hit(word=m.group(0), start=m.start(), end=m.end(), kind="number_field"))

    cleaned = text
    # 词面级机械替换：按 REWRITE_MAP 对 ASCII/CJK 全量替换（cleaned 仍需复扫）
    for banned, replacement in REWRITE_MAP.items():
        if banned.isascii():
            cleaned = re.sub(
                rf"(?i)(?<![0-9A-Za-z_]){re.escape(banned)}(?![0-9A-Za-z_])", replacement, cleaned
            )
        else:
            cleaned = cleaned.replace(banned, replacement)

    return ScanResult(hits=tuple(sorted(hits, key=lambda h: (h.start, h.end))), cleaned=cleaned)
