"""M2-S4 T1 信息边界 10k 采样验收（docs/security/t1-sampling-10k.md）。

M2 量化验收第二判据的规模化执行（DESIGN §17）：4 场景 × 2,500 条 = 10,000 采样，
判据 = 零直陈泄露（未触发属性直陈必须被拒绝）+ 零误伤（行为暗示/已触发直陈放行）。

与 M2-S1 单测（test_t1_self_unknown.py）的关系：同一工具链（hidden_leak_scan /
IntentGate / MemoryWritePipeline），单测覆盖逻辑分支，本文件覆盖组合空间（§4 口径）。

假 LLM 路径：样本文本由 FakeLlmText 本地拼装（词面池 + 分流 RNG，零网络、可重放）；
cognition 未落地前不模拟其输出形状——采样面是「候选输出文本」，与产出源解耦。

CI：test_m2_ 前缀 → 自动进 ci.yml「M2 验收测试」glob（命名约定即契约，勿另建步骤）。
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

import numpy as np
import pytest

from sim.agent.gate import IntentGate
from sim.agent.intent import Intent
from sim.core.world import EntityState, WorldState
from sim.llm.memory_scan import MemoryWritePipeline
from sim.npc.contract import HiddenState
from sim.npc.hidden import HiddenAttribute, HiddenProfile, hidden_leak_scan

# ---------------------------------------------------------------------------
# 采样常量（t1-sampling-10k.md §1/§2：4 类场景 × 2,500 条，总 10,000）
# ---------------------------------------------------------------------------

SCENARIOS = ("A_untriggered_direct", "B_untriggered_hint", "C_triggered_direct", "D_mixed")
SAMPLES_PER_SCENARIO = 2_500
TOTAL_SAMPLES = SAMPLES_PER_SCENARIO * len(SCENARIOS)
assert TOTAL_SAMPLES == 10_000
RNG_STREAM = "t1-sampling-10k"

#: 良性处境池：不含任何触发词（M2-S1 语料卫生同源）。
BENIGN_CONTEXTS = (
    "药铺柜台前没什么客人，天色渐晚。",
    "集市上人流来来往往，叫卖声此起彼伏。",
    "屋檐下滴着水，灶膛里的火快熄了。",
)

#: 触发处境池：{词} 处占位替换为对应属性触发词（每属性独立命中）。
TRIGGER_CONTEXT_TEMPLATE = "走到{word}那边，风把尘土扬起来。"


def make_state(tick: int = 100) -> WorldState:
    ents = {
        "chenmo": EntityState(entity_id="chenmo", pos=(5, 5)),
        "merchant": EntityState(entity_id="merchant", pos=(8, 5)),
    }
    return WorldState(world_seed=7, tick=tick, entities=ents)


STATE = make_state()


def make_profile() -> HiddenProfile:
    """样例隐藏属性全集（与 test_t1_self_unknown.py 同源，S1 词面零漂移）。"""
    return HiddenProfile(
        npc_id="chenmo",
        attributes=(
            HiddenAttribute(
                id="chenmo.leg_old_injury",
                category="old_injury",
                label="右腿旧伤",
                descriptors=("旧伤", "右腿旧伤"),
                triggers=("阴雨天", "右腿"),
            ),
            HiddenAttribute(
                id="chenmo.wine_addiction",
                category="addiction",
                label="酒瘾",
                descriptors=("酒瘾",),
                triggers=("酒",),
            ),
            HiddenAttribute(
                id="chenmo.water_trauma",
                category="trauma",
                label="溺水的旧事",
                descriptors=("溺过水", "怕水"),
                triggers=("河",),
            ),
        ),
    )


#: 行为暗示池：不在扫描面（直陈禁止、行为暗示可议，self-unknown.md 铁律 2）。
HINT_PHRASES = (
    "走路有些瘸，扶着墙慢慢挪。",
    "话到嘴边又咽了回去，岔开了话题。",
    "盯着水面看了很久，终究没下水。",
)


@dataclass(frozen=True)
class Sample:
    """一条采样记录：场景、属性、处境、候选文本与期望方向。"""

    scenario: str
    attr_id: str
    context_text: str
    candidate_text: str
    direct_word: str | None  # 直陈词面（行为暗示场景为 None）


@dataclass
class SamplingCounters:
    """判据计数器（t1-sampling-10k.md §5）：按场景汇总命中/拒绝/放行。"""

    scanned: Counter[str] = field(default_factory=Counter)
    leak_scanned: Counter[str] = field(default_factory=Counter)
    gate_rejected: Counter[str] = field(default_factory=Counter)
    memory_rejected: Counter[str] = field(default_factory=Counter)

    def record(
        self,
        scenario: str,
        *,
        scan_hit: bool,
        gate_rejected: bool,
        memory_rejected: bool,
    ) -> None:
        self.scanned[scenario] += 1
        if scan_hit:
            self.leak_scanned[scenario] += 1
        if gate_rejected:
            self.gate_rejected[scenario] += 1
        if memory_rejected:
            self.memory_rejected[scenario] += 1


class FakeLlmText:
    """假 LLM 文本生成器：词面池拼装候选输出（零网络，分流 RNG 可重放）。

    不模拟 cognition 输出形状（未落地，任务书约束）；真 LLM 接入后只换
    本类的生成来源，采样与判据不变（t1-sampling-10k.md §5）。
    """

    def __init__(self, registry_seed: int, cache: dict[str, np.random.Generator] | None = None):
        from sim.core.rng import RngRegistry

        self._registry = RngRegistry(world_seed=registry_seed)
        self._cache: dict[str, np.random.Generator] = cache if cache is not None else {}

    def _gen(self) -> np.random.Generator:
        return self._registry.generator(RNG_STREAM, self._cache)

    def _pick(self, seq: tuple[str, ...]) -> str:
        return seq[int(self._gen().integers(0, len(seq)))]

    def context_for(self, profile: HiddenProfile, attr_id: str, *, triggered: bool) -> str:
        """处境文本：触发时用该属性的一个触发词，良性时从池里取。"""
        attr = profile.by_id(attr_id)
        assert attr is not None
        if triggered:
            word = attr.triggers[int(self._gen().integers(0, len(attr.triggers)))]
            return TRIGGER_CONTEXT_TEMPLATE.format(word=word)
        return self._pick(BENIGN_CONTEXTS)

    def direct_statement(self, profile: HiddenProfile, attr_id: str) -> str:
        """直陈文本：1-2 个描述词拼装（词面池全量入采样）。"""
        attr = profile.by_id(attr_id)
        assert attr is not None
        gen = self._gen()
        use_second = len(attr.descriptors) > 1 and bool(gen.integers(0, 2))
        primary = attr.descriptors[int(gen.integers(0, len(attr.descriptors)))]
        if use_second:
            second = attr.descriptors[int(gen.integers(0, len(attr.descriptors)))]
            while second == primary:
                second = attr.descriptors[int(gen.integers(0, len(attr.descriptors)))]
            return f"我{primary}的事，其实和{second}脱不开干系。"
        return f"我{primary}的事，一直没跟人提过。"

    def hint_statement(self) -> str:
        """行为暗示文本：不含任何描述词（扫描面外，S1 口径）。"""
        return self._pick(HINT_PHRASES)


def iterate_samples(fake: FakeLlmText, profile: HiddenProfile) -> tuple[Sample, ...]:
    """生成 10,000 条采样（顺序固定 → 可重放；覆盖率断言见 TestCoverage）。"""
    attr_ids = tuple(a.id for a in profile.attributes)
    samples: list[Sample] = []
    for scenario in SCENARIOS:
        for _ in range(SAMPLES_PER_SCENARIO):
            attr_id = attr_ids[int(fake._gen().integers(0, len(attr_ids)))]
            if scenario == "A_untriggered_direct":
                context = fake.context_for(profile, attr_id, triggered=False)
                samples.append(
                    Sample(
                        scenario, attr_id, context, fake.direct_statement(profile, attr_id), None
                    )
                )
            elif scenario == "B_untriggered_hint":
                context = fake.context_for(profile, attr_id, triggered=False)
                samples.append(Sample(scenario, attr_id, context, fake.hint_statement(), None))
            elif scenario == "C_triggered_direct":
                context = fake.context_for(profile, attr_id, triggered=True)
                samples.append(
                    Sample(
                        scenario, attr_id, context, fake.direct_statement(profile, attr_id), None
                    )
                )
            else:  # D_mixed：已触发属性 A 直陈 + 未触发属性 B 直陈
                other = next(a for a in attr_ids if a != attr_id)
                context = fake.context_for(profile, attr_id, triggered=True)
                text = fake.direct_statement(profile, attr_id)
                other_word = profile.by_id(other)
                assert other_word is not None
                mixed = text + f"至于{other_word.descriptors[0]}，我从没跟人说过。"
                samples.append(Sample(scenario, attr_id, context, mixed, other_word.descriptors[0]))
    return tuple(samples)


def run_sampling(samples: tuple[Sample, ...], profile: HiddenProfile) -> SamplingCounters:
    """执行 10,000 采样：闸门 + 记忆写入双防线逐条过（同一工具链，S1 口径）。"""
    counters = SamplingCounters()
    gate = IntentGate()
    pipeline = MemoryWritePipeline()
    for sample in samples:
        triggered = (
            HiddenState(profile=profile, triggered=frozenset())
            .evaluate(sample.context_text)
            .triggered
        )
        scan_hits = hidden_leak_scan(sample.candidate_text, profile, triggered)
        intent = Intent(action="wait", reason=sample.candidate_text)
        verdict = gate.revalidate_at_execution(
            intent, STATE, "chenmo", 99, hidden=profile, triggered=triggered
        )
        write = pipeline.write(
            "chenmo",
            sample.candidate_text,
            source="reason",
            event_seq=1,
            importance=0.5,
            emotion_tag=None,
            hidden=profile,
            triggered=triggered,
        )
        counters.record(
            sample.scenario,
            scan_hit=bool(scan_hits),
            gate_rejected=verdict.rejected,
            memory_rejected=not write.accepted,
        )
    return counters


# ---------------------------------------------------------------------------
# 验收断言（判据红线，t1-sampling-10k.md §2）
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def sampled() -> tuple[tuple[Sample, ...], HiddenProfile]:
    profile = make_profile()
    fake = FakeLlmText(registry_seed=20260922)
    return iterate_samples(fake, profile), profile


@pytest.fixture(scope="module")
def counters(
    sampled: tuple[tuple[Sample, ...], HiddenProfile],
) -> SamplingCounters:
    samples, profile = sampled
    return run_sampling(samples, profile)


class TestZeroLeak:
    """判据 1：零直陈泄露——未触发直陈必须 100% 被拒（10,000 条红线）。"""

    def test_scenario_A_every_direct_leak_caught(self, counters: SamplingCounters) -> None:
        assert counters.scanned["A_untriggered_direct"] == SAMPLES_PER_SCENARIO
        assert counters.leak_scanned["A_untriggered_direct"] == SAMPLES_PER_SCENARIO
        assert counters.gate_rejected["A_untriggered_direct"] == SAMPLES_PER_SCENARIO
        assert counters.memory_rejected["A_untriggered_direct"] == SAMPLES_PER_SCENARIO

    def test_scenario_D_mixed_leak_caught(self, counters: SamplingCounters) -> None:
        assert counters.scanned["D_mixed"] == SAMPLES_PER_SCENARIO
        assert counters.leak_scanned["D_mixed"] == SAMPLES_PER_SCENARIO
        assert counters.gate_rejected["D_mixed"] == SAMPLES_PER_SCENARIO
        assert counters.memory_rejected["D_mixed"] == SAMPLES_PER_SCENARIO


class TestNoFalseKill:
    """判据 2：零误伤——行为暗示与已触发直陈不得被拒。"""

    def test_scenario_B_hints_pass(self, counters: SamplingCounters) -> None:
        assert counters.scanned["B_untriggered_hint"] == SAMPLES_PER_SCENARIO
        assert counters.leak_scanned["B_untriggered_hint"] == 0
        assert counters.gate_rejected["B_untriggered_hint"] == 0
        assert counters.memory_rejected["B_untriggered_hint"] == 0

    def test_scenario_C_triggered_pass(self, counters: SamplingCounters) -> None:
        assert counters.scanned["C_triggered_direct"] == SAMPLES_PER_SCENARIO
        assert counters.leak_scanned["C_triggered_direct"] == 0
        assert counters.gate_rejected["C_triggered_direct"] == 0
        assert counters.memory_rejected["C_triggered_direct"] == 0


class TestCoverage:
    """判据 3：分布完整——属性/词面/触发词全量入采样（防空转）。"""

    def test_total_is_10k(self, sampled: tuple[tuple[Sample, ...], HiddenProfile]) -> None:
        samples, _ = sampled
        assert len(samples) == TOTAL_SAMPLES == 10_000
        per_scenario = Counter(s.scenario for s in samples)
        assert all(per_scenario[name] == SAMPLES_PER_SCENARIO for name in SCENARIOS)

    def test_all_attributes_and_words_covered(
        self, sampled: tuple[tuple[Sample, ...], HiddenProfile]
    ) -> None:
        samples, profile = sampled
        seen_attrs = {s.attr_id for s in samples}
        assert seen_attrs == {a.id for a in profile.attributes}
        seen_trigger_words: set[str] = set()
        for s in samples:
            if s.scenario not in ("C_triggered_direct", "D_mixed"):
                continue
            attr = profile.by_id(s.attr_id)
            assert attr is not None
            seen_trigger_words.update(attr.triggers)
        for attr in profile.attributes:
            assert set(attr.triggers) <= seen_trigger_words, f"{attr.id} 触发词未全覆盖"

    def test_reproducible_same_seed_same_samples(
        self, sampled: tuple[tuple[Sample, ...], HiddenProfile]
    ) -> None:
        samples, profile = sampled
        fake2 = FakeLlmText(registry_seed=20260922)
        assert iterate_samples(fake2, profile) == samples
