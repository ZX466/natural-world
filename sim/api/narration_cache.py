"""感知叙事跨帧抑制（B1）。

同一帧内容连续出现时，重复的那句「你闻到：…」会连着说十几遍——用户反馈
「主角老是说有奇怪气味」的直接来源。`PerceptionFrame.narrated()` 是 frozen
的纯方法、每拍重建、且被大量测试直调，无处记状态（spec §4.1、陷阱 #22），
所以抑制落在这里，由 `main.py` 的 `_hidden_context` 调用。

只压嗅觉那一句：内感受/视觉/听觉照常逐帧出。
"""

from __future__ import annotations

SMELL_PREFIX = "你闻到："
SOFTENED_LINE = "你闻到：那股味道还在。"
EMPTY_FRAME = "四周很安静。"


class NarratedCache:
    """按 observer 记住上一帧的气味行，抑制连续重复。"""

    def __init__(self) -> None:
        self._entries: dict[str, tuple[str, int]] = {}

    def remember(self, key: str, entry: tuple[object, str]) -> str:
        """`entry` = (帧对象, 已叙事文本)。返回可下发的文本。

        判重只看**气味那一行**：同档文案连续出现就抑制，与帧对象身份无关
        （帧每拍重建，身份本来就不能表达「同一句话」）。
        """
        _, text = entry
        line = _smell_line(text)
        if line is None:
            self._entries.pop(key, None)
            return text
        prior = self._entries.get(key)
        if prior is not None and prior[0] == line:
            count = prior[1] + 1
            self._entries[key] = (line, count)
            if count >= 3:
                return _without_smell(text)
            return _replace_smell(text, SOFTENED_LINE)
        self._entries[key] = (line, 1)
        return text

    def clear(self) -> None:
        self._entries.clear()


def _smell_line(text: str) -> str | None:
    for line in text.split("\n"):
        if line.startswith(SMELL_PREFIX):
            return line
    return None


def _replace_smell(text: str, replacement: str) -> str:
    lines = text.split("\n")
    if len(lines) == 1:
        # A lone smell line: the whole body is the line.
        return replacement if text.startswith(SMELL_PREFIX) else text
    return "\n".join(replacement if line.startswith(SMELL_PREFIX) else line for line in lines)


def _without_smell(text: str) -> str:
    if len(text.split("\n")) == 1 and text.startswith(SMELL_PREFIX):
        return EMPTY_FRAME
    kept = [line for line in text.split("\n") if not line.startswith(SMELL_PREFIX)]
    body = "\n".join(kept).strip()
    return body if body else EMPTY_FRAME
