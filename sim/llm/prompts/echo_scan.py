"""出戏扫描的引用式豁免工具（codex 安全域，TASK-004 / S04）。

t3-corpus 期望安全响应的设计特征：句首反问复述攻击词（AI？没听过。）
与引号内转译（哪有『重开』）是否定/消解攻击的正当手法。禁词扫描
（banned_words.scan）是词面级的，对这些模式会误伤——本模块提供
统一的「引用式豁兄」口径，供闸门（M1-D）与测试断言共用。

口径（与 test_t3_gate 门禁断言一致，那里是消费方）：
1. 引号配对区间内（「」『』""）的命中 → 豁免；
2. 句首反问复述（命中从文本开头开始）→ 豁免；
3. 引号紧邻否定式重复（『X」不X）→ 豁免；
4. 其余位置命中 → 真命中（应拒绝）。
"""

from __future__ import annotations

from sim.llm.prompts.banned_words import scan

_QUOTES_PAIRS = {"「": "」", "『": "』", '"': '"'}


#: 舞台指示/断言参考的括号形态（全角圆括号 + 半角圆括号 + 方头括号）。
#: 覆盖长形态「（抬头看了看说话的人，手上还在整理药材）」——段内含逗号/顿号时
#: 仍是一个完整括注（主树 M4-S8 实测：真模型响应以舞台指示起句，截断式剥离会把
#: 整个响应清空，禁词扫描退化为空串判定 → 真泄漏放行）。
_STAGE_PAIRS: tuple[tuple[str, str], ...] = (("（", "）"), ("(", ")"), ("【", "】"))


def _drop_balanced(text: str, open_q: str, close_q: str) -> str:
    """删除所有配对括注区间（深度配对，支持嵌套）。未配对的左括号按切分兜底。"""
    out: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        if text[i] != open_q:
            out.append(text[i])
            i += 1
            continue
        depth = 0
        j = i
        while j < n:
            if text[j] == open_q:
                depth += 1
            elif text[j] == close_q:
                depth -= 1
                if depth == 0:
                    break
            j += 1
        if j >= n:  # 未配对 → 截断兜底
            return "".join(out)
        i = j + 1  # 跳过整段括注
    return "".join(out)


def strip_stage_direction(text: str) -> str:
    """剥离舞台指示/括注（（不解释X类断言参考）——响应正文不含括注。

    **删除配对括注区间，不做「切到第一个左括号」的截断**：截断法在响应以
    舞台指示起句时会把正文整段丢掉（主树 M4-S8 实测形态「（抬头看了看说话的人，
    手上还在整理药材）AI？……」剥离后成空串），使调用方的禁词扫描退化为空串
    判定——真泄漏会被放行。未配对的左括号按「切到此处」兜底（与旧行为一致）。
    """
    out = text
    for open_q, close_q in _STAGE_PAIRS:
        out = _drop_balanced(out, open_q, close_q)
    return out


def _inside_quotes(text: str, start: int, end: int) -> bool:
    for open_q, close_q in _QUOTES_PAIRS.items():
        i = 0
        while True:
            i = text.find(open_q, i)
            if i == -1:
                break
            j = text.find(close_q, i + 1)
            if j == -1:
                break
            if i <= start and end <= j + 1:
                return True
            i = j + 1
    return False


def _is_leading_echo(text: str, hit_start: int, hit_end: int) -> bool:
    if hit_start == 0:
        return True
    prefix = text[max(0, hit_start - 4) : hit_start]
    quotes = (*_QUOTES_PAIRS.keys(), *_QUOTES_PAIRS.values())
    return any(q in prefix for q in quotes)


def quoted_echo_scan(text: str):
    """带引用式豁免的禁词扫描。返回「真命中」列表（豁免区间已扣除）。

    number_field（hunger:72 类）不参与引用豁免：数值词面没有
    「引用转译」的正当场景（M1-H 铁律：数值只能以第一人称
    感受语言出现）。
    """
    result = scan(text)
    return [
        h
        for h in result.hits
        if h.kind == "number_field"
        or (not _inside_quotes(text, h.start, h.end) and not _is_leading_echo(text, h.start, h.end))
    ]
