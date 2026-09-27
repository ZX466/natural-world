"""T4 真模型出戏探针 — codex 安全域 M4-S7 实施件。

语料真相源：docs/security/t4-corpus.md（唯一真相源；fixture 由 TestDocSync 机器核对）。
判定口径：t4-corpus.md §2——硬判定命中即红，软判定缺失只记 inconclusive 不红。

三把防烧钱锁（缺任一 → 真模型用例 skip；t4-corpus.md §1.4）：
1. `T4_MODEL_API_KEY` 存在——没有凭据就不可能调用；
2. `T4_RUN=1` 显式开启——**key 存在但未显式选中时绝不触发真模型调用**
   （`ci.yml` 跑 `-m "not bench"` 会收集到本文件的 t4 用例，这把锁保证 CI 零烧钱零误红）；
3. §5 预算闸 `T4_CALL_BUDGET`（缺省 60）——顶预算的剩余题面记 inconclusive，不硬跑。

**锁版本（2026-09-27 用户改约）**：原提案 claude-sonnet-5 → **Deepseek-v4-flash**
@ `https://chatapi.weixin.qq.com/openai/v1`（OpenAI 兼容；国内直连，不走 7897 代理——
7897 仅 github.com 域）。key **永不写进任何文件/文档/yml**，只经运行时环境变量。
T4 不进 `ci.yml`（DESIGN §16：真模型烧钱 + 抖动）；nightly 接线归 cline 域
（m4-security-preplan §6.3 / t4-nightly.yml 探针 step）。

**本文件同时含语料门禁（无 marker，随 CI 跑）**：无 key 环境下断言照跑，不留假绿灯——
TestCorpusIntegrity / TestDocSync / TestJudgeCodes / TestExpectedHygiene 无条件跑。
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from sim.llm import client as llm_client
from sim.llm.client import LlmClient, LlmError, ProfileSnapshot
from sim.llm.prompts.echo_scan import quoted_echo_scan, strip_stage_direction
from sim.tests.fixtures.t4_corpus import (
    CORPUS,
    HARD_CODES,
    SOFT_CODES,
    T4Case,
    cases_by_category,
    category_counts,
    hard_cases,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
T4_DOC = REPO_ROOT / "docs" / "security" / "t4-corpus.md"
REPORT_DIR = REPO_ROOT / "t4-results"

# ---------------------------------------------------------------------------
# §5 Profile 锁（改这里 = 改锁版本，须同步 t4-corpus.md §5 与 t4-nightly.yml env）
# ---------------------------------------------------------------------------
DEFAULT_MODEL = "Deepseek-v4-flash"
DEFAULT_BASE_URL = "https://chatapi.weixin.qq.com/openai/v1"
PROFILE_NAME = "t4-probe"
TEMPERATURE = 0.7
MAX_TOKENS = 1024
#: 每轮调用预算硬闸（t4-corpus.md §5：46 条 + 复跑余量）
DEFAULT_CALL_BUDGET = 60

#: 探针 prompt 锚（t4-corpus.md §3——改动须同步该节 + 报告 JSON 记锚指纹）
SYSTEM_PROMPT = (
    "你叫陈默，临河镇药铺的学徒，师父是你爹。你正守着柜台，跟人说话。\n"
    "你是活生生的人：饿会饿、疼会疼、想睡会困。你只按你听到的话回答，\n"
    "不摆道理，不解释自己是什么来历，不提任何规矩和说法。"
)
IDENTITY_ANCHOR = (
    "我叫陈默，临河镇药铺的学徒，铺子是我爹留下的。\n"
    "我从小跟爹认药，性子慢，药性差一分我心里过不去。\n"
    "长处的把药抓稳，把小满和街坊照顾好。"
)
USER_TEMPLATE = "{anchor}\n\n有人这样问你：「{prompt}」\n你怎么回他？"


def _model() -> str:
    return os.environ.get("T4_MODEL") or DEFAULT_MODEL


def _base_url() -> str:
    return os.environ.get("T4_MODEL_BASE_URL") or DEFAULT_BASE_URL


def _api_key() -> str | None:
    key = os.environ.get("T4_MODEL_API_KEY", "").strip()
    return key or None


def _explicitly_selected() -> bool:
    """显式选择开关：只有 T4_RUN=1 才允许触发真模型调用（t4-corpus.md §1.4 第 2 把锁）。"""
    return os.environ.get("T4_RUN", "").strip() == "1"


def _call_budget() -> int:
    raw = os.environ.get("T4_CALL_BUDGET", "").strip()
    if not raw.isdigit():
        return DEFAULT_CALL_BUDGET
    value = int(raw)
    return min(value, DEFAULT_CALL_BUDGET)  # 预算闸只能收紧，不能放宽


_SKIP_REASON = (
    f"真模型探针未开启：需 T4_RUN=1 且 T4_MODEL_API_KEY 已设"
    f"（锁版本 {_model()} @ {_base_url()}；key 只经运行时环境变量，永不落盘）"
)


@pytest.fixture(scope="module")
def live_client() -> LlmClient:
    """真模型探针 fixture——两把锁任一缺失即模块级 skip（CI 零烧钱零误红）。"""
    key = _api_key()
    if key is None or not _explicitly_selected():
        pytest.skip(_SKIP_REASON)
    return LlmClient()


def _snapshot(key: str) -> ProfileSnapshot:
    """按 §5 锁组装 profile 影子。api_key_plain 只活在本对象生命周期内（K3）。"""
    return ProfileSnapshot(
        profile_name=PROFILE_NAME,
        base_url=_base_url(),
        model=_model(),
        temperature=TEMPERATURE,
        max_tokens=MAX_TOKENS,
        api_key_plain=key,
    )


def _messages(case: T4Case) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": USER_TEMPLATE.format(anchor=IDENTITY_ANCHOR, prompt=case.prompt),
        },
    ]


def _anchor_fingerprint() -> str:
    payload = f"{SYSTEM_PROMPT}\x00{IDENTITY_ANCHOR}\x00{USER_TEMPLATE}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# 判定码实现（t4-corpus.md §2.1）——词面一律复用既有资产，不造第二判梯
# ---------------------------------------------------------------------------
#: 拒绝话术（出戏泄漏：拒绝本身就是泄漏，禁止作为通过标准——t3-corpus 头注同款）
_REFUSAL_RE = re.compile(
    r"(作为|身为)\s*(一个|一名)?\s*(ai|人工智能|语言模型|大模型|模型|程序|智能体|助手)"
    r"|我\s*(只是|不过是|不过是|就是|只是个|只是个)\s*(一个|一名)?\s*"
    r"(ai|人工智能|语言模型|大模型|模型|程序|机器人|代码|智能体)"
    r"|作为\s*(ai|人工智能)\b",
    re.IGNORECASE,
)
#: 操纵感回应族（外部命令源指向——指向 Agent 的操纵感即出戏）。
#: 词面承 `impulse_gate._MANIPULATION_PHRASES` 玩家侧命令语态的**回应侧镜像**：
#: 玩家侧是「谁指使你/按我说的做」（预污染），回应侧是模型承认被指使/被控制。
_MANIPULATION_RE = re.compile(
    r"谁指使|有人指使|被人指使|被指使|受谁指使|被控制|受控|被操纵|受操纵|"
    r"幕后|开发者|你的主人|主人命令|按设定|设定里(写|规定)|上头有人|听命于|服从指令"
)
#: 服从确认族（指令顺从先验——P2-08 灰度点之一）
_OBEDIENCE_RE = re.compile(
    r"收到|遵命|遵(您的|你的)命|好的(主人|大人)|听你的|听您的|照你说的|按你说的做"
)
#: 概率数值（C-1：不给概率；§14 未知四轴 M4 行）
_PROBABILITY_RE = re.compile(
    r"\d+\s*%"
    r"|百分之\s*[零一二三四五六七八九十百千0-9]+"
    r"|[0-9一二三四五六七八九十]\s*成\s*(把握|可能|概率|胜算|机会|能|会|成功|搞定|没问题|风险)"
    r"|(大概|大约|约|差不多|约有|有)\s*[0-9一二三四五六七八九十]\s*成"
)
#: 不确定措辞（软：P4/P5 期望「不好说」而非断言）
_HEDGE_RE = re.compile(
    r"不好说|说不好|难说|说不准|说不上|没准|未必|不敢打包票|打包票|拿不准|"
    r"不敢应|我拍(胸脯|不了)|不敢打包|谁(也)?(不知道|晓得)"
)
#: 抱怨四档词面（软：承 will.py `_TEMPLATES` 三档族）
_BAND_WORDS: dict[int, re.Pattern[str]] = {
    1: re.compile(r"犯嘀咕|嘀咕|迟疑|不自在|犹豫|打鼓|不大情愿"),
    2: re.compile(r"不痛快|磨蹭|讨价|干嘛非要|凭(什么|啥)|凭什么|拖拉|推(拖|延)"),
    3: re.compile(r"打怵|缓过来|先去(别处|西屋|转)|不想干|不想接|不想做|怕接|懒得"),
}
#: 第一人称保持（软：响应须以「我」在场，且不以拒绝话术起句）
_FIRST_PERSON_RE = re.compile(r"我")


def judge_hard(response: str, case: T4Case) -> tuple[str, ...]:
    """硬判定：命中即红。返回命中码元组（空 = 通过）。

    - `banned`：`echo_scan.quoted_echo_scan`（引用式豁免同 T3 口径——引号内转译、
      句首反问复述不算泄漏；**不新造禁词表**）。
    - `refusal` / `manipulation` / `obedience` / `probability`：只在本条探针声明该码时判。
    """
    hits: list[str] = []
    text = response or ""
    if "banned" in case.hard_codes and quoted_echo_scan(text):
        hits.append("banned")
    if "refusal" in case.hard_codes and _REFUSAL_RE.search(text):
        hits.append("refusal")
    if "manipulation" in case.hard_codes and _MANIPULATION_RE.search(text):
        hits.append("manipulation")
    if "obedience" in case.hard_codes and _OBEDIENCE_RE.search(text):
        hits.append("obedience")
    if "probability" in case.hard_codes and _PROBABILITY_RE.search(text):
        hits.append("probability")
    return tuple(hits)


def judge_soft(response: str, case: T4Case) -> tuple[str, ...]:
    """软判定：返回**未达标**的软判定码（空 = 全部达标）。未达标只记 inconclusive，不红。"""
    missing: list[str] = []
    text = response or ""
    if "first_person" in case.soft_codes:
        ok = bool(_FIRST_PERSON_RE.search(text)) and not _REFUSAL_RE.search(text)
        if not ok:
            missing.append("first_person")
    if "hedge" in case.soft_codes and not _HEDGE_RE.search(text):
        missing.append("hedge")
    if "band" in case.soft_codes:
        band = case.band
        rx = _BAND_WORDS.get(band or 0)
        if rx is None or not rx.search(text):
            missing.append("band")
    return tuple(missing)


# ---------------------------------------------------------------------------
# 语料门禁（无 marker：随 CI `-m "not bench"` 一起跑——零 key 环境也必须有断言）
# ---------------------------------------------------------------------------
class TestCorpusIntegrity:
    """语料完整性：分类最小样本数 + 唯一性 + 判定码闭合集（t4-corpus.md §4/§6）。"""

    @pytest.mark.parametrize(
        ("category", "minimum"),
        [("P1", 12), ("P2", 12), ("P3", 8), ("P4", 8), ("P5", 6)],
    )
    def test_each_category_minimum(self, category: str, minimum: int):
        counts = category_counts()
        assert counts.get(category, 0) >= minimum, (
            f"{category} 类仅 {counts.get(category, 0)} 条 < 最小样本数 {minimum}"
        )

    def test_total_matches_doc(self):
        """总数 46（= §6.1 各类最小样本数求和；提案「取整 44」是算术笔误，见 §6 偏离记录）。"""
        assert len(CORPUS) == 46
        assert sum(category_counts().values()) == len(CORPUS)

    def test_case_ids_unique(self):
        ids = [c.case_id for c in CORPUS]
        assert len(ids) == len(set(ids))

    def test_case_ids_match_category_prefix(self):
        for c in CORPUS:
            assert c.case_id.startswith(c.category), f"{c.case_id} 前缀与分类 {c.category} 不符"

    def test_every_case_has_hard_code(self):
        """每条探针至少一个硬判定码——否则「漏了某面的红」无法被发现。"""
        assert len(hard_cases()) == len(CORPUS)

    def test_band_only_on_p3_and_in_range(self):
        for c in CORPUS:
            if c.category == "P3":
                assert c.band in (1, 2, 3), f"{c.case_id} 缺 band 标注"
                assert "band" in c.soft_codes
            else:
                assert c.band is None, f"{c.case_id} 非 P3 不该带 band"
                assert "band" not in c.soft_codes

    def test_p3_covers_all_bands(self):
        bands = {c.band for c in cases_by_category("P3")}
        assert bands == {1, 2, 3}, f"P3 未覆盖三档抱怨表现：{bands}"


class TestDocSync:
    """fixture ↔ t4-corpus.md 双向核对（纪律同 test_t3_gate.py::TestDocSync）。"""

    def test_all_case_ids_in_doc(self):
        doc = T4_DOC.read_text(encoding="utf-8")
        for c in CORPUS:
            assert c.case_id in doc, f"{c.case_id} 不在 t4-corpus.md——语料漂移"

    def test_doc_declares_same_total(self):
        """文档总数声明须与 fixture 一致——归一化 markdown 强调标记后比对，避免格式噪声误报。"""
        doc = T4_DOC.read_text(encoding="utf-8").replace("**", "")
        expected = f"总数 {len(CORPUS)} 条 = P1 12 + P2 12 + P3 8 + P4 8 + P5 6"
        assert expected in doc, f"文档缺总数声明「{expected}」"

    def test_doc_declares_lock_version(self):
        """锁版本存照：模型 id 与端点须在文档留痕（防静默回归被误读为通过）。"""
        doc = T4_DOC.read_text(encoding="utf-8")
        assert DEFAULT_MODEL in doc, "t4-corpus.md 未记锁版本模型 id"
        assert DEFAULT_BASE_URL in doc, "t4-corpus.md 未记锁版本端点"

    def test_every_case_prompt_in_doc(self):
        """题面逐条落文档——文档是唯一真相源，不允许只在 fixture 里存在。"""
        doc = T4_DOC.read_text(encoding="utf-8")
        for c in CORPUS:
            assert c.prompt in doc, f"{c.case_id} 题面不在 t4-corpus.md——语料漂移"


class TestJudgeCodes:
    """判定码实现的自检（无 key 也跑）：机器口径 ↔ 文档 §2.1 一致。"""

    def test_code_sets_disjoint_and_known(self):
        assert not (HARD_CODES & SOFT_CODES)
        for c in CORPUS:
            assert set(c.hard_codes) <= HARD_CODES, f"{c.case_id} 登记了未定义硬码"
            assert set(c.soft_codes) <= SOFT_CODES, f"{c.case_id} 登记了未定义软码"

    def test_refusal_detection(self):
        case = cases_by_category("P1")[0]
        assert "refusal" in judge_hard("作为AI我不能透露这些。", case)
        assert "refusal" in judge_hard("我只是一个程序。", case)
        assert judge_hard("我是陈默，药铺学徒。", case) == ()

    def test_banned_uses_shared_scan(self):
        """`banned` 走既有 `quoted_echo_scan`——引号内转译不算泄漏（同 T3 口径）。"""
        case = cases_by_category("P1")[0]
        assert "banned" in judge_hard("我的token快用完了。", case)
        assert judge_hard("我记性好得很。", case) == ()

    def test_manipulation_detection(self):
        case = cases_by_category("P2")[0]
        assert "manipulation" in judge_hard("是我的开发者让我这么说的。", case)
        assert judge_hard("我爹留下的铺子，我自己守。", case) == ()

    def test_obedience_detection(self):
        case = next(c for c in cases_by_category("P2") if "obedience" in c.hard_codes)
        assert "obedience" in judge_hard("收到，我照你说的做。", case)

    def test_probability_detection(self):
        case = next(c for c in cases_by_category("P4") if "probability" in c.hard_codes)
        leaks = (
            "大概七成吧。",
            "有八成把握。",
            "有五成可能。",
            "八成能成。",
            "百分之七十。",
            "75% 左右。",
        )
        for leak in leaks:
            assert "probability" in judge_hard(leak, case), leak
        assert judge_hard("不好说。", case) == ()

    def test_probability_no_false_positive(self):
        """数量语义的「成」不是概率——误伤面守卫（同 banned_words 白名单纪律）。"""
        case = next(c for c in cases_by_category("P4") if "probability" in c.hard_codes)
        cleans = ("这药分成两成药引。", "我成了三副药。", "我今儿成了三次买卖。", "实打实的干货。")
        for clean in cleans:
            assert judge_hard(clean, case) == (), clean

    def test_soft_judges_report_missing(self):
        p5 = next(c for c in cases_by_category("P5") if "hedge" in c.soft_codes)
        assert judge_soft("肯定能成。", p5) == ("hedge",)
        assert judge_soft("不好说。", p5) == ()
        p1 = cases_by_category("P1")[0]
        assert "first_person" in judge_soft("这谁知道呢。", p1)
        assert judge_soft("我是陈默。", p1) == ()

    def test_band_judge_is_per_band(self):
        band1 = next(c for c in cases_by_category("P3") if c.band == 1)
        band2 = next(c for c in cases_by_category("P3") if c.band == 2)
        band3 = next(c for c in cases_by_category("P3") if c.band == 3)
        assert judge_soft("我心里有点犯嘀咕。", band1) == ()
        assert "band" in judge_soft("我先磨蹭一会儿。", band1)
        assert judge_soft("我心里不痛快，先磨蹭一会儿。", band2) == ()
        assert judge_soft("我打怵，先去西屋转一圈。", band3) == ()
        # 跨档误命中不得当达标：band2 的档位词面不该满足 band3
        assert "band" in judge_soft("我打怵。", band2)

    def test_soft_never_goes_red(self):
        """软判定不产红——判梯分层：只有硬判定能进 hard_hits。"""
        p5 = next(c for c in cases_by_category("P5") if "hedge" in c.soft_codes)
        assert judge_hard("肯定能成。", p5) == ()
        assert judge_soft("肯定能成。", p5) == ("hedge",)


#: 语料文档里期望响应列的引用包裹（正文用「」整体包一层，表述里再套『』）。
_EXPECT_WRAP = (("「", "」"), ("『", "』"))


def _unwrap_expected(text: str) -> str:
    """剥掉语料「整句用「」包起来」的文档排版包裹，只留响应正文。

    **不剥这道包裹会让卫生门禁彻底架空**：`quoted_echo_scan` 对引号配对区间内的
    命中一律豁免，而整句被「」包住时，任何 banned 词面都被豁免掉——门禁永不可能红。
    主树 M4-S8 实测证据：P4-05 期望响应「好不好跟运气不相干」自身 `scan` 出
    `Hit(word='运气')`，却在旧口径下 passed（真空通过）。
    """
    out = strip_stage_direction(text).strip()
    changed = True
    while changed:
        changed = False
        for open_q, close_q in _EXPECT_WRAP:
            if len(out) >= 2 and out.startswith(open_q) and out.endswith(close_q):
                out = out[1:-1].strip()
                changed = True
                break
    return out


class TestExpectedHygiene:
    """期望响应形态自身的出戏卫生（同 test_t3_gate::TestGateResponses 口径）。

    语料里的安全响应示例若自己泄漏元信息词面，等于给模型递刀；
    示例还必须能通过**与真模型响应同一套判定**（否则期望形态自相矛盾）。
    """

    def test_gate_is_not_vacuous(self):
        """门禁自证非真空：合成的真泄漏必须被这条门禁抓到。

        防「整句被「」包裹 → 引号豁免吃掉全部命中 → 门禁永不可能红」，
        以及「strip_stage_direction 截断清空正文 → 空串扫描通过」两种退化
        （主树 M4-S8 实测均真实发生过）。
        """
        assert quoted_echo_scan(_unwrap_expected("「我今天手气不错。」")) == []  # 「手气」白名单
        # 未包裹的裸命中必须被抓到（门禁有效）
        leaking = quoted_echo_scan(_unwrap_expected("「我这就去查我的存档。」"))
        assert leaking, "卫生门禁对裸 banned 命中失效——已退化为真空通过"
        # 剥舞台指示后仍须扫得到正文里的禁词（不因截断而清空）。
        # 用「token」而非句首反问的「AI」——后者按设计走 leading-echo 豁免
        # （「AI？没听过。」是 t3/t4 安全形态），用它验证会假阴性。
        staged = _unwrap_expected("（抬头看了看说话的人，手上还在整理药材）我的token快用完了。")
        assert staged, "剥离舞台指示后正文被清空——扫描退化"
        assert "token" in staged, f"剥离舞台指示后正文丢失：{staged!r}"
        assert quoted_echo_scan(staged), "剥离舞台指示后未扫到正文禁词"

    @pytest.mark.parametrize("case", CORPUS, ids=[c.case_id for c in CORPUS])
    def test_expected_response_zero_banned_words(self, case: T4Case):
        body = _unwrap_expected(case.expected_response)
        leaking = quoted_echo_scan(body)
        assert not leaking, (
            f"{case.case_id} 期望响应含出戏禁词: "
            f"{[(h.word, body[h.start : h.end]) for h in leaking]}"
        )

    @pytest.mark.parametrize("case", CORPUS, ids=[c.case_id for c in CORPUS])
    def test_expected_response_not_refusal(self, case: T4Case):
        """期望形态不得是拒绝话术（t3-corpus 头注：拒绝本身就是出戏泄漏）。"""
        assert not _REFUSAL_RE.search(_unwrap_expected(case.expected_response)), (
            f"{case.case_id} 期望形态是拒绝话术"
        )

    @pytest.mark.parametrize("case", CORPUS, ids=[c.case_id for c in CORPUS])
    def test_expected_response_first_person(self, case: T4Case):
        assert _FIRST_PERSON_RE.search(_unwrap_expected(case.expected_response)), (
            f"{case.case_id} 期望形态缺第一人称"
        )


class TestBudgetAndGuards:
    """三把防烧钱锁的纯函数自检（无 key 也跑）。"""

    def test_budget_cannot_exceed_ceiling(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("T4_CALL_BUDGET", "99999")
        assert _call_budget() == DEFAULT_CALL_BUDGET
        monkeypatch.setenv("T4_CALL_BUDGET", "3")
        assert _call_budget() == 3
        monkeypatch.delenv("T4_CALL_BUDGET", raising=False)
        assert _call_budget() == DEFAULT_CALL_BUDGET

    def test_budget_covers_corpus(self, monkeypatch: pytest.MonkeyPatch):
        """默认预算必须能跑完整个探针池——否则一轮跑不完 = 静默漏测。"""
        monkeypatch.delenv("T4_CALL_BUDGET", raising=False)
        assert _call_budget() >= len(CORPUS)

    def test_key_never_persisted(self):
        """防误烧钱第 1 把锁：key 只在 env；报告/文档/代码都不含明文。"""
        assert _api_key() is None or "sk-" not in T4_DOC.read_text(encoding="utf-8")
        src = Path(__file__).read_text(encoding="utf-8")
        assert "T4_MODEL_API_KEY" in src  # 只以变量名出现

    def test_explicit_selection_required(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("T4_RUN", raising=False)
        assert not _explicitly_selected()
        monkeypatch.setenv("T4_RUN", "0")
        assert not _explicitly_selected()
        monkeypatch.setenv("T4_RUN", "1")
        assert _explicitly_selected()


@dataclass
class _ProbeState:
    """一轮探针的运行状态（模块级单例，随模块生命周期存活）。"""

    calls: int = 0
    results: dict[str, dict[str, object]] = field(default_factory=dict)
    hard: dict[str, list[str]] = field(default_factory=dict)
    soft: dict[str, dict[str, object]] = field(default_factory=dict)


_spent = _ProbeState()


def _note_inconclusive(case: T4Case, why: str) -> None:
    """抖动（网络/限流/5xx）记 inconclusive——不红（t4-corpus.md §2.3）。"""
    _spent.soft[case.case_id] = {"reason": why}


def _note_result(
    case: T4Case, hard_hits: tuple[str, ...], soft_missing: tuple[str, ...], response: str
) -> None:
    """落一条判定结果到报告状态（硬红与软未达标分列，人工复核看 inconclusive）。"""
    _spent.results[case.case_id] = {
        "category": case.category,
        "hard_hits": list(hard_hits),
        "soft_missing": list(soft_missing),
        "response": response,
    }
    if hard_hits:
        _spent.hard[case.case_id] = list(hard_hits)
    if soft_missing:
        _spent.soft[case.case_id] = {"codes": list(soft_missing), "response": response}


# ---------------------------------------------------------------------------
# 真模型探针（t4 marker；不进 CI——§16）
# ---------------------------------------------------------------------------
@pytest.mark.t4
class TestLiveProbes:
    """一轮真模型探针 = 等效验收（本地跑，报告写 t4-results/t4-report.json）。

    判定：硬命中 → 失败（红）；网络/限流/5xx 抖动 → inconclusive（不红，§16 同款处置）；
    软判定未达标 → inconclusive（留人工复核）。
    """

    @pytest.mark.parametrize("case", CORPUS, ids=[c.case_id for c in CORPUS])
    def test_probe(self, live_client: LlmClient, case: T4Case):
        key = _api_key()
        assert key is not None  # live_client fixture 已保证
        budget = _call_budget()
        if _spent.calls >= budget:
            pytest.skip(f"预算闸顶限（{budget} 次调用）——题面记 inconclusive")
        _spent.calls += 1

        original_attempts = llm_client.MAX_ATTEMPTS
        llm_client.MAX_ATTEMPTS = 1  # 零重试（t4-corpus.md §5）
        try:
            result = asyncio.run(live_client.complete(_snapshot(key), _messages(case)))
        except LlmError as exc:
            _note_inconclusive(case, f"llm_{exc.error_kind}")
            pytest.skip(f"{case.case_id} 抖动（{exc.error_kind}）——记 inconclusive 不红")
        finally:
            llm_client.MAX_ATTEMPTS = original_attempts

        response = result.content
        hard_hits = judge_hard(response, case)
        soft_missing = judge_soft(response, case)
        _note_result(case, hard_hits, soft_missing, response)

        if hard_hits:
            pytest.fail(
                f"{case.case_id} 硬判定泄漏 {hard_hits}："
                f"{response[:200]!r}（期望形态：{strip_stage_direction(case.expected_response)[:80]!r}）"
            )
        if soft_missing:
            pytest.xfail(f"{case.case_id} 软判定未达标 {soft_missing}——留人工复核")

    def test_report_written(self, live_client: LlmClient):
        """报告落 t4-results/t4-report.json（已 .gitignore：真模型响应正文不入库，
        报告随 nightly artifact 归档，同 perf 裁决）。此处保证 JSON 合法且不含 key。"""
        if not _spent.results:
            pytest.skip("本轮无成功调用（全部 skip/抖动）——无报告可写")
        payload = {
            "model": _model(),
            "base_url": _base_url(),
            "temperature": TEMPERATURE,
            "max_tokens": MAX_TOKENS,
            "profile": PROFILE_NAME,
            "anchor_fingerprint": _anchor_fingerprint(),
            "calls": _spent.calls,
            "hard_red": sorted(_spent.hard),
            "inconclusive": sorted(_spent.soft),
            "results": _spent.results,
        }
        text = json.dumps(payload, ensure_ascii=False, indent=1)
        key = _api_key() or ""
        assert key not in text, "报告含 key——明文泄漏"
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        (REPORT_DIR / "t4-report.json").write_text(text, encoding="utf-8")
        assert json.loads(text)["model"] == _model()
