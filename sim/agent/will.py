"""sim.agent.will — 意愿系统（M4-B2，DESIGN §10；m4-plan 批次 B 行为链 Claude 域）。

**意愿冲突度** = w₁性格违背 + w₂风险 + w₃需求冲突 + w₄处境不合（§10 公式，权重和=1）。
四档表现（§10 表）：0.0-0.3 自然接受 / 0.3-0.6 轻微迟疑独白微词 / 0.6-0.8 明显抱怨
拖延讨价还价 / 0.8-1.0 强烈抵触先做别的事再绕回来。

**但最终都执行**——本管线只产 `WillingnessVerdict`（表现强度），不回写效用分数、
不拦截动作：决策结果由 utility.py 决定，意愿系统只决定「执行时的姿态」。
（类型层保证：`willingness_conflict` 不接受也不返回 UtilityDecision。）

纪律（§10/§19）：
- 抱怨必须是**自我怀疑**（「我干嘛要干这个」），绝不能是被操纵感（「谁在指使
  我」）——后者即出戏；模板词面全部第一人称自嘲/迟疑（test_m4_willingness 钉死）；
- 冲突度数值/w1-w4 权重/档位号是元信息，**永不进任何戏内文本**（X 系构造隔离）；
- 纯函数、frozen 值对象（immutability 规约）；模板选取确定性（C5）。

不做：念头注入（批次 A 另件）、看板渲染（前端域）、LOD0 统计档（无独白面）。
"""
from __future__ import annotations

from dataclasses import dataclass

#: §10 四档切分阈值（band 0/1/2/3 的上界，最后一档到 1.0）
WILLINGNESS_BANDS: tuple[float, float, float] = (0.3, 0.6, 0.8)

#: §10 权重 w₁-w₄（性格违背/风险/需求冲突/处境不合；和=1.0）。
#: M4 初版均分——权重调参是 M5 行为回填的事，先给中性基线（§15 监控先行）。
WEIGHT_PERSONALITY = 0.25
WEIGHT_RISK = 0.25
WEIGHT_NEEDS = 0.25
WEIGHT_SITUATION = 0.25


@dataclass(frozen=True)
class WillingnessVerdict:
    """冲突度合成结果（frozen；score∈[0,1]，band∈{0,1,2,3}）。"""

    score: float
    band: int


@dataclass(frozen=True)
class WillingnessExpression:
    """四档表现的戏内产物（frozen）。

    monologue=独白微词（band≥1 必有）；defers=先做别的再绕回来（仅 band 3）；
    band 是戏内表现档（供装配层选模板，**不进文本**）。
    """

    band: int
    monologue: str = ""
    defers: bool = False


def _band_of(score: float) -> int:
    for band, upper in enumerate(WILLINGNESS_BANDS):
        if score < upper:
            return band
    return 3


def willingness_conflict(
    personality_violation: float,
    risk: float,
    needs_conflict: float,
    situation_mismatch: float,
) -> WillingnessVerdict:
    """w₁-w₄ 线性合成 → 冲突度 verdict（各维夹到 [0,1]；C5 纯函数）。

    参数语义（§10）：
    - personality_violation：动作与 OCEAN 人格的违背程度（0..1）；
    - risk：动作的感知风险（战斗/高危叙述出现强度，0..1）；
    - needs_conflict：动作与当前最紧迫需求的冲突（0..1）；
    - situation_mismatch：处境不合（时间/地点/天气与动作的错配，0..1）。
    """
    w1 = min(1.0, max(0.0, personality_violation))
    w2 = min(1.0, max(0.0, risk))
    w3 = min(1.0, max(0.0, needs_conflict))
    w4 = min(1.0, max(0.0, situation_mismatch))
    score = (
        WEIGHT_PERSONALITY * w1
        + WEIGHT_RISK * w2
        + WEIGHT_NEEDS * w3
        + WEIGHT_SITUATION * w4
    )
    return WillingnessVerdict(score=score, band=_band_of(score))


#: 各档独白模板（全部**自我怀疑**词面——§10「我干嘛要干这个」族；
#: 禁「谁在指使/被操纵」族（出戏）。多模板按 band 轮换时用 (band, 分数微差)
#: 决定，保证 C5；M4 初版每档 1 条，扩模板走 T4 词面复核）。
_TEMPLATES: dict[int, str] = {
    1: "这事我有点犯嘀咕——我平时可不这么办事。",
    2: "说不上来为什么，就是不痛快。先磨蹭一会儿吧，我干嘛非要现在干这个。",
    3: "这活儿我实在打怵。……先去别处转一圈，缓过来再说。",
}


def willingness_expression(
    verdict: WillingnessVerdict, *, npc_name: str
) -> WillingnessExpression | None:
    """verdict → 戏内表现（band 0 无表现=None；独白不嵌 NPC 名=第一人称铁律）。

    `npc_name` 当前只用于未来第二人称调试层（M4 不消费）；签名收它是因为
    装配层调用点已持有，避免 M5 加参破调用。
    """
    _ = npc_name  # 见 docstring：预留，不进文本
    if verdict.band <= 0:
        return None
    template = _TEMPLATES[verdict.band]
    return WillingnessExpression(
        band=verdict.band,
        monologue=template,
        defers=verdict.band >= 3,
    )
