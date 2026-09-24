"""M3 批次 B-B3：关系图激活（m3-plan 批次 B 架构细化；DESIGN §7 有向不对称）。

TDD RED 先行。契约（m3-plan §3 B-B3，M3 最小集防过度设计）：
- RelationshipStore：relationships 表 CRUD（SQL，照 memory_store 惯例——纯 SQL、
  upsert 单行、无缓存层、branch_id 隔离）；双向两行（A→B、B→A 各一行）；
- society.apply_interaction(...)：演化规则 M3 最小集——
  1. 转述互动：retell 成功 → to_npc 对 from_npc 的 trust +δ（δ 常量起步）；
  2. 目击隐藏属性：witnessed 判定成立 → fear +δ（trauma 关联）；
  3. 日常互动：对话类动作 → affection 小幅漂移 + last_interaction 刷新；
- 边界：不做关系推理（M2 架构稿 §3 延续）；关系面不出感知帧（社会未知轴）；
  不碰 L1 效用链（批次 D 才接）。
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from sim.core.persistence.models import Relationship
from sim.core.persistence.relationship_store import RelationshipView


def _must(view: RelationshipView | None) -> RelationshipView:
    """测试收窄：get() 断言非 None 后取值（存在性即断言）。"""
    assert view is not None
    return view


@pytest.fixture
def conn(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    """Alembic 建全表（test_memory_store 同款流程）。"""
    import os
    import subprocess
    import sys

    db = str(tmp_path / "society.db")
    env = {**os.environ, "WORLD_DB_URL": f"sqlite+aiosqlite:///{db}"}
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=str(Path(__file__).resolve().parents[2]),
        env=env,
        check=True,
        capture_output=True,
    )
    c = sqlite3.connect(db)
    c.row_factory = sqlite3.Row
    yield c
    c.close()


class TestRelationshipStore:
    def test_ensure_row_creates_pair(self, conn: sqlite3.Connection) -> None:
        """ensure_row：首次互动建双向两行（默认值 0）。"""
        from sim.core.persistence.relationship_store import RelationshipStore

        store = RelationshipStore(conn, branch_id="main", current_tick=100)
        store.ensure_row("a", "b")
        rows = conn.execute(
            "SELECT * FROM relationships WHERE branch_id='main' ORDER BY owner_id"
        ).fetchall()
        assert len(rows) == 2
        by_owner = {r["owner_id"]: r for r in rows}
        assert by_owner["a"]["other_id"] == "b"
        assert by_owner["b"]["other_id"] == "a"
        assert by_owner["a"]["trust"] == 0.0

    def test_adjust_trust_clamped(self, conn: sqlite3.Connection) -> None:
        """adjust：trust 加 δ 且 clamp [0,1]（不越界）。"""
        from sim.core.persistence.relationship_store import RelationshipStore

        store = RelationshipStore(conn, branch_id="main", current_tick=100)
        store.ensure_row("a", "b")
        store.adjust("a", "b", trust=+0.3)
        assert _must(store.get("a", "b")).trust == pytest.approx(0.3)
        store.adjust("a", "b", trust=+0.9)  # 1.2 → clamp 1.0
        assert _must(store.get("a", "b")).trust == pytest.approx(1.0)
        store.adjust("a", "b", trust=-2.0)  # -1.0 → clamp 0.0
        assert _must(store.get("a", "b")).trust == pytest.approx(0.0)

    def test_adjust_refreshes_last_interaction(self, conn: sqlite3.Connection) -> None:
        from sim.core.persistence.relationship_store import RelationshipStore

        store = RelationshipStore(conn, branch_id="main", current_tick=100)
        store.ensure_row("a", "b")
        store2 = RelationshipStore(conn, branch_id="main", current_tick=500)
        store2.adjust("a", "b", affection=+0.1)
        assert _must(store2.get("a", "b")).last_interaction == 500

    def test_branch_isolation(self, conn: sqlite3.Connection) -> None:
        from sim.core.persistence.relationship_store import RelationshipStore

        RelationshipStore(conn, branch_id="main", current_tick=1).ensure_row("a", "b")
        store_alt = RelationshipStore(conn, branch_id="alt", current_tick=1)
        assert store_alt.get("a", "b") is None  # 分支隔离：alt 不可见 main 的行


class TestApplyInteraction:
    def _store(self, conn: sqlite3.Connection):
        from sim.core.persistence.relationship_store import RelationshipStore

        return RelationshipStore(conn, branch_id="main", current_tick=100)

    def test_retell_success_raises_trust(self, conn: sqlite3.Connection) -> None:
        """规则 1：转述成功 → to_npc 对 from_npc trust +δ（有向：只有 b→a 方向）。"""
        from sim.npc.society import RETELL_TRUST_DELTA, apply_interaction

        store = self._store(conn)
        apply_interaction(store, kind="retell", from_npc="a", to_npc="b")
        after = _must(store.get("b", "a"))
        assert after.trust == pytest.approx(RETELL_TRUST_DELTA)
        # 有向不对称：a→b 方向不动
        assert _must(store.get("a", "b")).trust == pytest.approx(0.0)

    def test_witness_hidden_raises_fear(self, conn: sqlite3.Connection) -> None:
        """规则 2：目击他人隐藏属性 → fear +δ（trauma 关联）。"""
        from sim.npc.society import WITNESS_FEAR_DELTA, apply_interaction

        store = self._store(conn)
        apply_interaction(store, kind="witness_hidden", from_npc="chenmo", to_npc="b")
        assert _must(store.get("b", "chenmo")).fear == pytest.approx(WITNESS_FEAR_DELTA)

    def test_daily_chat_drifts_affection(self, conn: sqlite3.Connection) -> None:
        """规则 3：日常对话 → affection 小幅漂移 + last_interaction 刷新。"""
        from sim.npc.society import CHAT_AFFECTION_DELTA, apply_interaction

        store = self._store(conn)
        apply_interaction(store, kind="chat", from_npc="a", to_npc="b")
        rel = _must(store.get("b", "a"))
        assert rel.affection == pytest.approx(CHAT_AFFECTION_DELTA)
        assert rel.last_interaction == 100

    def test_unknown_kind_rejected(self, conn: sqlite3.Connection) -> None:
        from sim.npc.society import apply_interaction

        store = self._store(conn)
        with pytest.raises(ValueError):
            apply_interaction(store, kind="gossip", from_npc="a", to_npc="b")  # type: ignore[arg-type]

    def test_no_inference_no_perception_leak(self, conn: sqlite3.Connection) -> None:
        """边界锁定：Relationship 模型无「推理值」字段；store 不提供跨人批量读
        （R6 社会面：关系面只按 owner 读自己的一行）。"""
        assert not hasattr(Relationship, "inferred")

        store = self._store(conn)
        store.ensure_row("a", "b")
        # get 只按 (owner, other) 取单行——不存在 list_all/跨人查询接口
        assert not hasattr(store, "list_all")
