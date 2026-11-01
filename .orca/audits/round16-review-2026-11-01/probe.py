"""主树复核探针（第十六轮）——独立于 codex 自证。

三条硬事实：
  A. 生产形态下 `Observation.subject` 是**中文显示名**，而 `witnesses_of_emerge`
     拿 `rtoken_of(subject)` 去比 ⇒ 永不匹配 ⇒ `witnesses` 恒空。
  B. 因此 `npc.knowledge_learned` 零产生 ⇒ `knowledge` 表恒 0 行。
  C. `told` 路以 `knowledge` 行为源 ⇒ 同根因被堵死。

用法：
    PYTHONPATH=. uv run python .orca/audits/round16-review-2026-11-01/probe.py
"""

from __future__ import annotations

import asyncio
import json
import shutil
import tempfile
from pathlib import Path

from sqlalchemy import func, select

from sim.api import main
from sim.core.persistence.models import Event, Knowledge, Relationship
from sim.perception.frame import Channel, Observation, PerceptionFrame
from sim.perception.senses import rtoken_of
from sim.npc.evidence import witnesses_of_emerge, witnesses_of_entity_emerge

AUDIT = Path(__file__).resolve().parent


def check_subject_format() -> dict[str, object]:
    """A：两种帧形态下 witnesses 装配的差异（纯函数，无 IO）。"""
    ids = ["villager_01", "villager_02"]
    production_frame = {
        rtoken_of("villager_01"): PerceptionFrame(
            observer=rtoken_of("villager_01"),
            tick=9,
            observations=(
                Observation(
                    channel=Channel.VISION,
                    subject="赵铁",  # 生产：display_name_of（senses.py:271）
                    description="赵铁停下了脚步。",
                    strength=0.4,
                ),
            ),
        )
    }
    test_frame = {
        rtoken_of("villager_01"): PerceptionFrame(
            observer=rtoken_of("villager_01"),
            tick=9,
            observations=(
                Observation(
                    channel=Channel.VISION,
                    subject=rtoken_of("villager_02"),  # codex 测试：rtoken
                    description="走来",
                    strength=1.0,
                ),
            ),
        )
    }
    return {
        "production_form": witnesses_of_entity_emerge(
            production_frame, subject="villager_02", entity_ids=ids, tick=10
        ),
        "codex_test_form": witnesses_of_entity_emerge(
            test_frame, subject="villager_02", entity_ids=ids, tick=10
        ),
        "legacy_fn_on_production": witnesses_of_emerge(
            production_frame, subject=rtoken_of("villager_02")
        ),
    }


async def run_live(db_source: Path | None, ticks: int) -> dict[str, object]:
    """B/C：真实 lifespan 推进，观察两张表是否自然产生行。"""
    root = Path(tempfile.mkdtemp(prefix="r16-review-"))
    if db_source is not None:
        db = root / "world.db"
        shutil.copy2(db_source, db)
    else:
        db = root / "fresh.db"
    main.WORLD_DB_PATH = db
    main._offline_wall_time = lambda: 0.0
    main._active_profile_snapshot_provider = lambda: lambda: None

    async with main.lifespan(main.app):
        for name in ("driver", "chenmo_task"):
            task = getattr(main.app.state, name, None)
            if task is not None:
                task.cancel()
        loop = main.app.state.loop
        store = main.app.state.store
        branch = await store.current_branch_id_or_none() or "main"

        async def counts() -> dict[str, int]:
            async with store.session_factory() as session:
                return {
                    "events": int(await session.scalar(select(func.count()).select_from(Event)) or 0),
                    "knowledge": int(
                        await session.scalar(
                            select(func.count())
                            .select_from(Knowledge)
                            .where(Knowledge.branch_id == branch)
                        )
                        or 0
                    ),
                    "relationships": int(
                        await session.scalar(
                            select(func.count())
                            .select_from(Relationship)
                            .where(Relationship.branch_id == branch)
                        )
                        or 0
                    ),
                }

        before = await counts()
        start = loop.state.tick
        while loop.state.tick < start + ticks:
            loop.advance_frame(4.0)
            # 坑：flush_for_anchor 读 loop.pending_events，不要先 drain_events。
            if loop.pending_events:
                await main.app.state.flush_for_anchor()
        after = await counts()

        async with store.session_factory() as session:
            emerges = (
                (await session.execute(select(Event).where(Event.event_type == "npc.hidden_emerge")))
                .scalars()
                .all()
            )
            learned = (
                (
                    await session.execute(
                        select(Event).where(Event.event_type == "npc.knowledge_learned")
                    )
                )
                .scalars()
                .all()
            )

        witnesses_nonempty = sum(
            1 for row in emerges if row.witnesses and row.witnesses != "[]"
        )
        return {
            "db": str(db),
            "db_source": None if db_source is None else str(db_source),
            "start_tick": start,
            "end_tick": loop.state.tick,
            "before": before,
            "after": after,
            "event_delta": after["events"] - before["events"],
            "hidden_emerge": len(emerges),
            "hidden_emerge_with_witnesses": witnesses_nonempty,
            "knowledge_learned_events": len(learned),
        }


async def main_() -> None:
    result: dict[str, object] = {"A_subject_format": check_subject_format()}
    result["B_fresh_db"] = await run_live(None, ticks=600)
    main_db = Path("E:/zxdevelop/project7/world.db")
    if main_db.exists():
        result["C_real_db_copy"] = await run_live(main_db, ticks=600)
    out = AUDIT / "review.json"
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main_())
