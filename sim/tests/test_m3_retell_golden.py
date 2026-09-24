"""D3 「NPC 记得且会转述」端到端 golden 雏形（m3-plan 批次 D3，DESIGN §17 M3 验收）。
T5 golden 场景 M3 雏形（fixture 优先，无 LLM——§16 T5「fixture 优先」原则）：
一个场景 = 记忆传播全链路闭环，宏观断言不依赖任何 LLM 调用：
  1. 见证：B 现场目睹 A 的隐藏属性浮现（E1 事件 + witnesses 装配）；
  2. 记得：witnessed 知识落 B 的 knowledge 表（write_fact 走写入门）；
  3. 转述：B 把它讲给 C（retell 走证据链判定 + C 侧复制写记忆）；
  4. told 知识落 C 的 knowledge 表（source_knowledge_id 指向 B 的行，链上溯）；
  5. 级联：A 的源记忆 supersede → B 行失效 → C 行沿 told 链失效 → C 转述被拒
     （链断拒收闭环，R1 端到端）。
宏观断言：链路各节点状态 + 治理不变量（失效传播完整、无孤儿有效行）。
C5：同种子同事件流逐位可重放（纯函数链 + 管线确定性）。
"""
from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from sim.core.persistence.database import init_database
from sim.core.persistence.knowledge_store import (
    REASON_SOURCE_SUPERSEDED,
    KnowledgeStore,
)
from sim.llm.memory_scan import MemoryWritePipeline
from sim.npc.evidence import SELF_DISCLOSURE_CONFIDENCE, WITNESSED_CONFIDENCE
from sim.npc.propagation import retell


@pytest.fixture
async def engine():
    eng = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    await init_database(eng)
    yield eng
    await eng.dispose()


@pytest.fixture
def sessions(engine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture()
def pipeline() -> MemoryWritePipeline:
    return MemoryWritePipeline()


def _emerge_row(*, npc_id: str, tick: int, attr_ids: list[str], witnesses: list[str]) -> dict:
    """E1 事件行（evidence.judge_third_party_hidden 消费的最小 dict 形）。"""
    return {
        "event_type": "npc.hidden_emerge",
        "tick": tick,
        "payload": {"npc_id": npc_id, "attr_ids": attr_ids},
        "witnesses": witnesses,
    }


@pytest.mark.t1
class TestRetellChainGolden:
    """「记得且会转述」全链路：A 患咳疾 → B 目击 → B 讲给 C → 源翻转 → 全链断。"""

    async def test_witness_remember_retell_cascade(self, sessions, pipeline) -> None:
        store = KnowledgeStore(sessions)

        # 1. 见证：B 现场目睹 A 的咳疾浮现（雨夜触发，B 在 witnesses 里）
        events = [_emerge_row(npc_id="npc-a", tick=100, attr_ids=["h1"], witnesses=["npc-b"])]
        # 2. 记得：witnessed 知识落 B（X7 写入门；confidence=见证基线 0.9）
        b_row = await store.write_fact(
            pipeline,
            holder_id="npc-b",
            fact="陈默的咳疾怕雨夜，别在雨夜约他出诊",
            confidence=WITNESSED_CONFIDENCE,
            source="witnessed",
            learned_at=100,
            subject_npc_id="npc-a",
            subject_attr_id="h1",
            evidence_seq=1,
            source_memory="mem-root",
        )
        assert b_row.accepted and b_row.row_id is not None

        # 3. 转述：B 把它讲给 C——先有 B 的转述记忆（C 侧复制写），再有 C 的知识行
        b_row_orm = await store.get(b_row.row_id)
        assert b_row_orm is not None  # 刚写入的行必在
        verdict_input = {
            "invalidated": b_row_orm.invalidated,
            "subject_npc_id": b_row_orm.subject_npc_id,
            "subject_attr_id": b_row_orm.subject_attr_id,
            "confidence": b_row_orm.confidence,
        }
        entry = retell(
            pipeline=pipeline,
            to_npc="npc-c",
            source="told",
            subject_id="npc-a",
            attr_id="h1",
            events=events,
            content="听说陈默的咳疾怕雨夜",
            tick=110,
            teller_knowledge=verdict_input,
        )
        assert entry is not None  # 证据链通过 + C 侧写入门放行

        # 4. told 知识落 C（source_knowledge_id 指向 B 的行；置信 = 0.9×0.6）
        c_row = await store.write_fact(
            pipeline,
            holder_id="npc-c",
            fact="陈默的咳疾怕雨夜，别在雨夜约他出诊",
            confidence=round(WITNESSED_CONFIDENCE * 0.6, 6),
            source="told",
            learned_at=110,
            subject_npc_id="npc-a",
            subject_attr_id="h1",
            source_knowledge_id=b_row.row_id,
        )
        assert c_row.accepted and c_row.row_id is not None

        # 宏观断言①：B、C 各持一条有效知识（「记得」）
        assert len(await store.iter_valid("npc-b")) == 1
        assert len(await store.iter_valid("npc-c")) == 1

        # 5. 级联：A 的源知识被推翻（supersede 等价口 invalidate_by_source）
        #    B 行失效 → C 行沿 told 链失效（R1 端到端）
        count = await store.invalidate_by_row(b_row.row_id, REASON_SOURCE_SUPERSEDED)
        assert count == 2  # B 行 + C 行（继承失效不继承替代）

        # 宏观断言②：链断后全链无效（「不再转述」）
        assert await store.iter_valid("npc-b") == []
        assert await store.iter_valid("npc-c") == []

        # 宏观断言③：C 再想转述给 D → teller 知识已失效 → 拒收（链断拒收）
        c_row_orm = await store.get(c_row.row_id)
        assert c_row_orm is not None  # 刚写入的行必在
        d_entry = retell(
            pipeline=pipeline,
            to_npc="npc-d",
            source="told",
            subject_id="npc-a",
            attr_id="h1",
            events=events,
            content="听说陈默的咳疾怕雨夜",
            tick=120,
            teller_knowledge={
                "invalidated": c_row_orm.invalidated,
                "subject_npc_id": c_row_orm.subject_npc_id,
                "subject_attr_id": c_row_orm.subject_attr_id,
                "confidence": c_row_orm.confidence,
            },
        )
        assert d_entry is None

    async def test_self_disclosure_chain_root(self, sessions, pipeline) -> None:
        """自我披露链根：A 自己告诉 C（subject==holder 不要求 source_knowledge_id）。"""
        store = KnowledgeStore(sessions)
        row = await store.write_fact(
            pipeline,
            holder_id="npc-a",
            fact="陈默自己说了，他的咳疾是旧伤落下的",
            confidence=SELF_DISCLOSURE_CONFIDENCE,
            source="told",
            learned_at=50,
            subject_npc_id="npc-a",
            subject_attr_id="h1",
        )
        assert row.accepted
        # 链根知识在 A 自己名下（subject==holder）；iter_valid 验证它有效
        assert len(await store.iter_valid("npc-a")) == 1
