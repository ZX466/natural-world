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


def strip_stage_direction(text: str) -> str:
    """剥离期望响应列的括注（（不解释X类断言参考）——响应正文不含括注。"""
    i = text.find("（")
    return text[:i] if i != -1 else text


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
