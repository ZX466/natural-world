"""M5-S2b T1 钉子 — 跨分支证据链断言面（R-E2/E3/E5/E6；m5-fork-evidence-preplan.md §2/§3）

RED 先行（codex 安全域 M5-S2b）：四条钉子锁的是 S2 预研实证过的**现状正确行为**——
「恰好对」的实现没有断言 = 未受保护状态，任何放宽（跨分支事件合并查询、浮现状态
持久化、iter_valid 口径变更）必须先让这里的钉子显式红，再走 CR。

- **R-E2**（祖父指针保留）：再分叉合法（父可已 abandoned，fork.py:278），fork 的
  CASE 只改写 NULL 指针 → 孙分支的 `evidence_branch_id` 必须仍是**祖父**；
  改写成父 = 伪造「证据在父分支」，与事实不符。
- **R-E3**（消费 fail-closed）：子分支 witnessed 知识的证据住在非本分支（事件不克隆）
  → `judge_third_party_hidden` **必须 deny**。现状恰好 fail-closed（judge 只读
  本分支事件流，实测 `witnessed_no_matching_emerge`）；钉死防未来跨分支事件
  合并查询静默放宽（全仓 grep：evidence_branch_id 当前零读侧消费）。
- **R-E5**（可见集/可证集分离）：`iter_valid` 可见集 = 当前分支克隆行（含证据
  指针指向父分支的行）；可证集 = R-E3 的 deny。两半各自 fail-closed，分开钉。
- **R-E6**（浮现状态禁持久化）：`evaluate_triggers` 按 tick 纯函数重算，触发消退
  → 回归隐藏（self-unknown §1.3）。生产代码不得出现「已浮现」持久化载体
  （surfaced 表/列）；**若未来为性能/叙事引入持久化，必须带 branch_id 且按分支
  隔离**——否则父分支浮现会渗给子分支（S1 §3 最初担心的洞，构造上封死）。

复用 D3-b/D3-c fixtures 体例（`test_m5_fork_clone.py` / `test_t1_m5_history_preserved.py`）：
内存 SQLite + `init_database` + 真实 `SqlEventStore.append`（事件走生产校验，不合成）。
本文件不改生产语义、不扩 BANNED_WORDS（m5-fork-evidence-preplan.md §7 变更纪律）。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from sim.core.persistence.database import init_database
from sim.core.persistence.fork import fork_from_anchor
from sim.core.persistence.knowledge_store import KnowledgeStore
from sim.core.persistence.models import Event, Knowledge
from sim.core.persistence.store import SqlEventStore
from sim.npc.evidence import judge_third_party_hidden

REPO_ROOT = Path(__file__).resolve().parents[2]

GRAND = "branch-grand"
PARENT = "branch-parent"
CHILD = "branch-child"


def _lod_event(tick: int) -> dict:
    """一条过生产校验的合法事件（推进分支头部用；NPC_HIDDEN_EMERGE 见 _emerge_event）。"""
    return {
        "tick": tick,
        "event_type": "npc.lod_change",
        "actor_id": "worker-a",
        "target_id": None,
        "parent_seq": None,
        "payload": {"npc_id": "worker-a", "from_lod": 1, "to_lod": 2, "reason": "enter_range"},
        "witnesses": [],
        "entropy_ref": None,
    }


def _emerge_event(tick: int, *, subject: str, attr: str, witness: str) -> dict:
    """npc.hidden_emerge（R5 证据链根，EventKind 白名单内；witnesses 承 0005 口径）。"""
    return {
        "tick": tick,
        "event_type": "npc.hidden_emerge",
        "actor_id": subject,
        "target_id": None,
        "parent_seq": None,
        "payload": {"npc_id": subject, "attr_ids": [attr]},
        "witnesses": [witness],
        "entropy_ref": None,
    }


async def _noop_preflush() -> None:
    return None


@pytest.fixture
async def engine():
    eng = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    await init_database(eng)
    yield eng
    await eng.dispose()


@pytest.fixture
def store(engine):
    sf = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return SqlEventStore(sf)


@pytest.fixture
def session_factory(engine):
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


# ---------------------------------------------------------------------------
# R-E2：祖父证据指针在再分叉时保留（CASE 只碰 NULL）
# ---------------------------------------------------------------------------
class TestGrandparentEvidencePointerPreserved:
    async def test_grandparent_pointer_survives_refork(
        self, store: SqlEventStore, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        """R-E2：三段链 祖→父→子，孙行 evidence_branch_id 必须仍是**祖父**。

        fork.py 的 CASE（`WHEN evidence_branch_id IS NULL THEN :pid`）只改写
        「证据在本分支」的行；指向祖父的行原样保留。改写成父 = 伪造证据位置。
        （M5-S2b 实测：现实现恰好对——本钉把它从「恰好」变成「受保护」。）
        """
        async with session_factory() as session:
            await store.append(GRAND, [_emerge_event(1, subject="npc-b", attr="x", witness="w")])
            session.add(
                Knowledge(
                    holder_id="w",
                    fact="npc-b 有旧伤",
                    confidence=0.9,
                    source="witnessed",
                    learned_at=1,
                    branch_id=GRAND,
                    evidence_seq=1,
                    subject_npc_id="npc-b",
                    subject_attr_id="x",
                )
            )
            await session.commit()

        # 祖→父（父分支随后再推进一格，供再分叉）
        await fork_from_anchor(
            session_factory,
            parent_branch_id=GRAND,
            fork_seq=1,
            fork_tick=1,
            new_branch_id=PARENT,
            preflush=_noop_preflush,
        )
        async with session_factory() as session:
            await store.append(PARENT, [_lod_event(2)])
        # 父→子（再分叉：父分支头部）
        await fork_from_anchor(
            session_factory,
            parent_branch_id=PARENT,
            fork_seq=1,
            fork_tick=2,
            new_branch_id=CHILD,
            preflush=_noop_preflush,
        )

        async with session_factory() as session:
            child_row = (
                await session.execute(select(Knowledge).where(Knowledge.branch_id == CHILD))
            ).scalar_one()
            assert child_row.evidence_branch_id == GRAND, (
                f"祖父证据指针被改写成 {child_row.evidence_branch_id!r}（应为 {GRAND!r}）——"
                "伪造「证据在父分支」，违反 0008-d 语义"
            )
            assert child_row.evidence_seq == 1

            parent_row = (
                await session.execute(select(Knowledge).where(Knowledge.branch_id == PARENT))
            ).scalar_one()
            assert parent_row.evidence_branch_id == GRAND, (
                "父分支行指针在 fork 后被改动（克隆只写子分支，父行不可变）"
            )


# ---------------------------------------------------------------------------
# R-E3 + R-E5：可见集（iter_valid）与可证集（judge）分离，各自 fail-closed
# ---------------------------------------------------------------------------
class TestVisibilityVsVerifiabilitySeparated:
    async def test_child_iter_valid_sees_cloned_row_but_judge_denies(
        self, store: SqlEventStore, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        """R-E5（可见）+ R-E3（可证）：子分支「看得到」克隆行，但证据**不可在本分支解析**。

        - 可见集：`iter_valid` 返回克隆 witnessed 行（只按 branch_id+invalidated 过滤）；
        - 可证集：`judge_third_party_hidden` 只读本分支事件流，证据事件住在父分支
          （事件不克隆）→ `witnessed_no_matching_emerge` deny（fail-closed）。

        两半分开钉：未来任何「跨分支事件合并查询」或「iter_valid 口径变更」都必须
        先让本钉显式红，再走 CR（m5-fork-evidence-preplan.md §2 R-E3/E5）。
        """
        async with session_factory() as session:
            await store.append(PARENT, [_emerge_event(1, subject="npc-b", attr="x", witness="w")])
            session.add(
                Knowledge(
                    holder_id="w",
                    fact="npc-b 有旧伤",
                    confidence=0.9,
                    source="witnessed",
                    learned_at=1,
                    branch_id=PARENT,
                    evidence_seq=1,
                    subject_npc_id="npc-b",
                    subject_attr_id="x",
                )
            )
            await session.commit()

        await fork_from_anchor(
            session_factory,
            parent_branch_id=PARENT,
            fork_seq=1,
            fork_tick=1,
            new_branch_id=CHILD,
            preflush=_noop_preflush,
        )

        # R-E5：可见集 = 当前分支克隆行
        ks_child = KnowledgeStore(session_factory, branch_id=CHILD)
        child_rows = await ks_child.iter_valid("w")
        assert len(child_rows) == 1, "克隆 witnessed 行应出现在子分支可见集"
        assert child_rows[0].evidence_branch_id == PARENT

        ks_parent = KnowledgeStore(session_factory, branch_id=PARENT)
        parent_rows = await ks_parent.iter_valid("w")
        assert len(parent_rows) == 1, "父分支行仍在（克隆非搬移，§19/C6）"

        # R-E5 白盒侧：跨分支 id 视作不存在（R4 口径在分叉后仍成立）
        cross = await ks_child.get(parent_rows[0].id)
        assert cross is None, "子分支 store 读到了父分支行 id（跨分支可见性破口）"

        # R-E3：可证集——子分支事件流为空（证据事件不克隆）→ deny
        async with session_factory() as session:
            child_events = (
                (await session.execute(select(Event).where(Event.branch_id == CHILD)))
                .scalars()
                .all()
            )
        events = [
            {
                "event_type": e.event_type,
                "tick": e.tick,
                "payload": e.payload,
                "witnesses": e.witnesses,
            }
            for e in child_events
        ]
        verdict = judge_third_party_hidden(
            source="witnessed",
            holder_id="w",
            subject_id="npc-b",
            attr_id="x",
            events=events,
            observed_tick=1,
        )
        assert not verdict.admitted, "子分支凭父分支证据 admitted（跨分支证据链污染）"
        assert verdict.reason == "witnessed_no_matching_emerge", verdict.reason


# ---------------------------------------------------------------------------
# R-E6：浮现状态禁持久化（白盒纪律钉；若未来落表必须带 branch_id）
# ---------------------------------------------------------------------------
class TestSurfacedStateNotPersisted:
    def test_no_persistent_surfaced_state_without_branch_id(self) -> None:
        """R-E6：生产代码零「浮现持久化」载体；落表则必须含 branch_id（按分支隔离）。

        现状（M5-S2b 实测）：零命中——浮现窗口按 tick 纯函数重算（self-unknown §1.3），
        无 surfaced 表/列。本钉扫**构造载体**（类名/列名/表名），不扫注释：
        注释里的「已浮现」是文档不是状态（gate.py / impulse_gate.py / hidden.py
        命中的均为 docstring，非载体——本钉因此用结构化正则而非关键词裸匹配）。

        未来若为性能/叙事引入持久化：必须带 `branch_id` 且按分支隔离（本钉的
        第二分支），否则父分支浮现渗给子分支（m5-security-preplan §3）。
        """
        pattern = re.compile(
            r"class\s+\w*(Surfaced|Emerged)\w*"
            r"|surfaced\w*\s*[:=]"
            r'|__tablename__\s*=\s*"[^"]*surfaced[^"]*"',
            re.IGNORECASE,
        )
        column_pattern = re.compile(r"(surfaced\w*|is_surfaced)\s*[:=]\s*Mapped", re.IGNORECASE)

        carriers: list[str] = []
        for f in (REPO_ROOT / "sim").rglob("*.py"):
            if "test" in f.name:
                continue
            text = f.read_text(encoding="utf-8")
            for rx in (pattern, column_pattern):
                for m in rx.finditer(text):
                    line_no = text[: m.start()].count("\n") + 1
                    carriers.append(f"{f.relative_to(REPO_ROOT)}:{line_no}: {m.group(0)}")

        assert not carriers, (
            "发现「浮现状态持久化」载体（违反 R-E6）：\n"
            + "\n".join(carriers)
            + "\n若为有意引入：载体必须带 branch_id 列并按分支隔离，"
            "且本钉须随 CR 同步更新（m5-fork-evidence-preplan.md §2 R-E6）"
        )

    def test_evaluation_is_pure_function(self) -> None:
        """R-E6 白盒侧证：同 profile 两次求值互不残留（无模块级可变状态累积）。"""
        from sim.npc.hidden import HiddenAttribute, HiddenProfile, evaluate_triggers

        profile = HiddenProfile(
            npc_id="npc-b",
            attributes=(
                HiddenAttribute(
                    id="x",
                    category="old_injury",
                    label="旧伤",
                    descriptors=("旧伤",),
                    triggers=("雨天腿疼",),
                ),
            ),
        )
        first = evaluate_triggers(profile, "晴天")
        assert first == frozenset(), "未触发时应为空集"
        second = evaluate_triggers(profile, "雨天腿疼")
        assert second == frozenset({"x"}), "触发时应浮现"
        third = evaluate_triggers(profile, "晴天")
        assert third == frozenset(), (
            "第二次未触发求值仍残留上次的浮现状态（evaluate_triggers 引入了状态）"
        )
