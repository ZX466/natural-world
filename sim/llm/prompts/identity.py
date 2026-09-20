"""身份锚 — Agent 的自述 + 人格摘要 + 长期目标（DESIGN §8 [身份锚] 段）。

铁律 4「记忆即身份」的地基：身份锚是 prompt 第一段，前缀缓存以它为
分界（messages[0]）。frozen 模型：锚定后不可变（人格不是可写状态）。
本模型只承载文本，不承载任何数值属性——人格是叙事，不是参数表。
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class IdentityAnchor(BaseModel):
    """一段身份锚。组装进 prompt 时原样嵌入 [身份锚] 段。

    self_narrative：第一人称自述（「我叫陈默，是个跑腿的……」）。
    persona_summary：人格摘要（叙事语言，非 Big-Five 数值）。
    long_term_goal：长期目标（第一人称）。
    """

    model_config = ConfigDict(frozen=True)

    entity_id: str  # 戏外主键（组装 prompt 时绝不出现；仅用于寻址与缓存键）
    self_narrative: str
    persona_summary: str
    long_term_goal: str

    def render(self) -> str:
        """[身份锚] 段文本：纯第一人称，视角锁定（铁律 2）。"""
        return "\n".join((self.self_narrative, self.persona_summary, self.long_term_goal))
