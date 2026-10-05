"""sim.npc.speech_register — 语言阶层语域派生（M6 内容面；DESIGN §13 语言阶层）。

**职责边界（最小面）**：
- 语域 = **运行态纯函数派生**（opencode A3 判定：**无事件源状态禁落可重放表**
  ——本模块**不落列、不发事件、不占 0015**：语域是「权力/亲疏的派生读数」，
  任何 tick 可由输入重算 ⇒ 事件/落列都只是第二真相源，撞 schema §19.3）；
- **三档语域**（粗/日常/文雅——DESIGN §13「语言阶层」；M2 的
  `LanguageProfile.class_register` 是**角色静态档**，本模块派生的是**当下
  对话语域**=静态档 × 权力/亲疏修正）；
- **S4 三边界硬约束**（安规判定）：①**不读 power 档**——语域修正只接
  「可达性布尔」（对方是否在我可对话的社交圈，布尔不泄漏连续量级）；
  ②**不出机器档号**——输出只有语域词（粗/日常/文雅），零数值零索引；
  ③**只经既有意愿域输入**（人格/亲疏——不新开权力参数口）；
- 消费方 = prompt 装配（语域词进对话风格段——**禁挂 messages[0]**，P4 红线：
  破坏前缀缓存 ⇒ 增量被 LLM 侧放大成假账；识字率是判据不是数值，同 M2 红线）。

C5：同输入必同语域（无隐藏随机/时钟）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

#: 三档语域（可叙事词；零数值——S4 边界②：输出只有这几个词）。
REGISTER_ROUGH: Final[str] = "粗"
REGISTER_PLAIN: Final[str] = "日常"
REGISTER_REFINED: Final[str] = "文雅"

#: 语域档全集（校验用）。
REGISTERS: Final[frozenset[str]] = frozenset({REGISTER_ROUGH, REGISTER_PLAIN, REGISTER_REFINED})


class SpeechRegisterError(ValueError):
    """语域派生输入非法（未知静态档/亲疏越界）。"""


@dataclass(frozen=True)
class SpeechContext:
    """一次对话的语域输入（frozen；**零权力数值**——S4 边界①）。

    `class_register`：角色静态档（M2 `LanguageProfile.class_register` 同源，
    如「平民/士绅/行内」）；`in_circle`：对方是否在我可对话的社交圈
    （**布尔**——可达性，不是连续亲疏值）。
    """

    class_register: str
    in_circle: bool = True

    def __post_init__(self) -> None:
        if not self.class_register:
            raise SpeechRegisterError("class_register 不得为空")
        if not isinstance(self.in_circle, bool):
            raise SpeechRegisterError(f"in_circle 必须是布尔: {self.in_circle!r}")


def speech_register(ctx: SpeechContext) -> str:
    """当下对话语域（**纯函数**；三档；S4 三边界兑现）。

    规则（占位直段；调参 M6 定标轮回填）：
    - 圈内人 ⇒ 按静态档：士绅/行内=文雅，平民=日常（亲近则收起架子）；
    - 圈外人 ⇒ 平民档对外一律「粗」（陌生人的戒备），士绅对外仍「日常」
      （不失态但不亲近）；
    - **零权力输入**：本函数签名不收 power/authority 任何形态（S4 边界①
      在签名层面兑现——想传都传不进）。
    """
    if ctx.in_circle:
        return REGISTER_REFINED if ctx.class_register in ("士绅", "行内") else REGISTER_PLAIN
    return REGISTER_PLAIN if ctx.class_register in ("士绅", "行内") else REGISTER_ROUGH
