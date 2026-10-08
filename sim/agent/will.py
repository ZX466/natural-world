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

import hashlib
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


#: 各档独白模板池（全部**自我怀疑**词面——§10「我干嘛要干这个」族；
#: 禁「谁在指使/被操纵」族（出戏）。D10 扩池：每档 ≥4 条，按 (band, npc_name)
#: 确定性哈希选取（C5 同输入同输出）——D2 实证单模板 × 50 人 = 全镇合唱
#: 同一句（「心之声凌乱」根因之一）。扩面时词面纪律随 T4 band 词表钉走。
_TEMPLATES: dict[int, tuple[str, ...]] = {
    1: (
        "这事我有点犯嘀咕——我平时可不这么办事。",
        "心里有点打鼓，这么干到底对不对？",
        "不大情愿……可事到眼前，迟疑也是白迟疑。",
        "说不出的不自在，今天这活儿我有点犹豫。",
        # D18 扩池（4→12）：50 人同屏时 4 句必复读（截图定罪），语域不变
        "手上的活儿照做，心里总有点不大情愿。",
        "唉，磨磨蹭蹭的，心里直犯嘀咕。",
        "做是做，心里那道坎还没过去，说不出的不自在。",
        "这差事推又推不掉，做又不大情愿。",
        "手脚慢了半拍，心里直犹豫。",
        "说不上来哪儿不对，就是犯嘀咕。",
        "咬咬牙也就做了，心里还是有点打鼓。",
        "干着干着就犹豫，这活儿不合我心。",
    ),
    2: (
        "说不上来为什么，就是不痛快。先磨蹭一会儿吧，我干嘛非要现在干这个。",
        "这活儿讨价还价也没人听，磨蹭一会儿是一会儿。",
        "越想越不痛快——凭什么是我来干这个？",
        "不痛快。缓口气再动，我干嘛非要这么急。",
        # D18 扩池
        "凭什么赶这么急，我的活儿我心里有数。",
        "这事儿办得不痛快，歇会儿再说。",
        "急什么，磨蹭到太阳落山前做完就成。",
        "心里不痛快，手上就慢了。",
        "这安排不痛快，可日子还得过。",
        "拖着吧，不痛快的活儿干不好。",
        "让我缓缓，这口气咽不下，不痛快。",
        "凭什么，干活的是我，拿主意的又不是我。",
    ),
    3: (
        "这活儿我实在打怵。……先去别处转一圈，缓过来再说。",
        "不想干，真不想干。先走开透透气。",
        "打怵得很，腿都沉了——先去别处绕绕，缓过来再说。",
        "这事儿我先撂下。不缓过来我怕自己干砸。",
        # D18 扩池
        "先去别处走走，撂下这摊子缓过来再说。",
        "不想干，真不想干，换个地方缓缓。",
        "打怵得很，腿已经先往别处走了。",
        "先去溜达一圈，缓过来再跟这活儿较劲。",
        "这会儿真打怵，先去别处避开一会儿。",
        "不想干就走开走开，眼不见心不烦。",
        "先去透口气，缓过来再说，这活儿跑不了。",
        "缓不过来就先撤，先去别处回头再说。",
    ),
}


def willingness_expression(
    verdict: WillingnessVerdict, *, npc_name: str
) -> WillingnessExpression | None:
    """verdict → 戏内表现（band 0 无表现=None；独白不嵌 NPC 名=第一人称铁律）。

    D10：模板从池中按 (band, npc_name) 确定性哈希选取——不同 npc 说法岔开
    （同输入恒同输出，C5）；`npc_name` 兼作选取键（仍不进文本）。
    """
    if verdict.band <= 0:
        return None
    pool = _TEMPLATES[verdict.band]
    idx = _pick_index(npc_name, len(pool))
    template = pool[idx]
    return WillingnessExpression(
        band=verdict.band,
        monologue=template,
        defers=verdict.band >= 3,
    )


def _pick_index(npc_name: str, pool_size: int) -> int:
    """(npc_name) → 池内下标（sha256 截断取模；确定性，无 RNG 状态流）。"""
    digest = hashlib.sha256(npc_name.encode("utf-8")).digest()
    return int.from_bytes(digest[0:4], "big") % pool_size


# ---------------------------------------------------------------------------
# D14 真实意愿合成（替换「全队共享 band=1 占位」——D9 遗留正主）
# ---------------------------------------------------------------------------

#: 需求冲突阈值：紧迫度超过它却没在做对应补救动作 → 冲突。
#: 与 needs.py DEFAULT_DECAYS 的 threshold 同源口径（0.7/0.7/0.8）。
_NEED_THRESHOLD: dict[str, float] = {"hunger": 0.7, "energy": 0.7, "social": 0.8}

#: 需求 → 其补救动作（needs.py remedy_action 同源）。
_NEED_REMEDY: dict[str, str] = {
    "hunger": "eat",
    "energy": "rest",
    "social": "request_chat",
}

#: 动作 → 性格违背的 (ocean 维下标, "高才冲突"/"低才冲突") 描述。
#: OCEAN 序 = openness/conscientiousness/extraversion/agreeableness/neuroticism。
#: 社交列（request_chat）违背 extraversion；劳作列（work）违背 conscientiousness。
_ACTION_PERSONALITY: dict[str, tuple[int, bool]] = {
    "request_chat": (2, False),  # 内向（低 E）被拉去聊天 → 冲突
    "work": (1, True),  # 低 C（懒散）被派活 → 冲突
}


def _phase_of_tick(tick: int) -> str:
    """tick → day phase（calendar.phase_of_day 同源；此处独立小表防循环导入）。"""
    hour = (tick // 3600) % 24
    if 5 <= hour < 7:
        return "dawn"
    if 7 <= hour < 17:
        return "day"
    if 17 <= hour < 19:
        return "dusk"
    return "night"


def synthesize_verdict(profile: object, action: str, *, tick: int) -> WillingnessVerdict:
    """逐人真实意愿合成（纯函数，C5）：性格违背 + 需求冲突 + 处境不合。

    **主档语义**（D14，替代 §10 加权和的实况供数版）：加权和在
    sum(w)=1、band1 界 0.3 的体系下单维贡献 ≤0.25——「E=5 被拉去聊天」
    这种现实强冲突数学上永远沉在 band0，与「单维强冲突即迟疑」的现实
    语义矛盾。改为：band = 最强单维的主档（0.3/0.6/0.8 界同 §10），
    多维中档叠加升一档（封 3）。frozen verdict 形状不变；「最终都执行」
    不变（verdict 不改动作）。
    """
    needs = getattr(profile, "needs", ())
    ocean = getattr(profile, "ocean", (50.0, 50.0, 50.0, 50.0, 50.0))

    # 三个冲突维各自归一到 [0,1]（0.3/0.6/0.8 界复用 WILLINGNESS_BANDS）
    dims: list[float] = []

    # 1. 性格违背：低 E 被拉去聊天 / 低 C 被派活（中性 50 起算，极端 1.0）
    spec = _ACTION_PERSONALITY.get(action)
    if spec is not None:
        idx, _conflicts_when_low = spec
        score = float(ocean[idx]) if idx < len(ocean) else 50.0
        dims.append(max(0.0, (50.0 - score) / 50.0))

    # 2. 需求冲突：越阈值的需求没被当前动作补救（超出量归一）
    for n in needs:
        threshold = _NEED_THRESHOLD.get(n.name)
        if threshold is None:
            continue
        if float(n.value) >= threshold and action != _NEED_REMEDY.get(n.name):
            dims.append((float(n.value) - threshold) / (1.0 - threshold))

    # 3. 处境不合：深夜干活 / 白天补觉（作息错配）
    phase = _phase_of_tick(tick)
    if phase == "night" and action == "work":
        dims.append(0.8)
    elif phase == "day" and action == "rest":
        dims.append(0.6)

    if not dims:
        return WillingnessVerdict(score=0.0, band=0)

    # 主档 = 最强单维；中档（≥0.3）维度 ≥2 个 → 升一档（叠加升级，封 3）
    strongest = max(dims)
    band = _band_of(strongest)
    if band < 3 and sum(1 for d in dims if d >= WILLINGNESS_BANDS[0]) >= 2:
        band += 1
    return WillingnessVerdict(score=strongest, band=band)
