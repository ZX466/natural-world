"""身份锚从分支档案透传到不可变 profile 和 runtime。"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from sim.core.persistence.database import create_engine, create_session_factory, init_database
from sim.core.persistence.models import NpcProfile
from sim.core.persistence.npc_store import NpcStore
from sim.core.persistence.store import SqlEventStore
from sim.npc.assemble import assemble_runtime
from sim.npc.model import Need, NpcProfileData

_MAIN_ANCHOR = "  我是许娘，守着祖传的茶铺。\n不愿离开老街。  "
_CHILD_ANCHOR = "我是许娘，我已收起茶铺，改做摆渡。\n"


@pytest.fixture
async def identity_events(tmp_path: Path) -> AsyncIterator[SqlEventStore]:
    database_path = (tmp_path / "identity.sqlite3").as_posix()
    engine = create_engine(f"sqlite+aiosqlite:///{database_path}")
    try:
        await init_database(engine)
        yield SqlEventStore(create_session_factory(engine))
    finally:
        await engine.dispose()


async def _seed_branch_anchors(events: SqlEventStore) -> None:
    async with events.session_factory() as session:
        session.add_all(
            [
                NpcProfile(
                    id="npc:same",
                    branch_id="main",
                    name="许娘",
                    identity_anchor=_MAIN_ANCHOR,
                ),
                NpcProfile(
                    id="npc:same",
                    branch_id="child",
                    name="许娘",
                    identity_anchor=_CHILD_ANCHOR,
                ),
            ]
        )
        await session.commit()


def test_legacy_positional_profile_defaults_to_empty_identity_anchor() -> None:
    profile = NpcProfileData(
        "npc:legacy",
        "旧客",
        "human",
        "木匠",
        (40.0, 50.0, 60.0, 70.0, 80.0),
        (0.1, 0.2, -0.3),
        (Need("hunger", 0.4, 1.0),),
        {"木工": 3},
        2,
        "士",
    )

    assert profile.identity_anchor == ""
    assert profile.class_register == "士"
    assert profile.lod == 2


def test_profile_updates_preserve_identity_anchor() -> None:
    original = NpcProfileData("npc:same", "许娘", identity_anchor=_MAIN_ANCHOR)
    needs = (Need("hunger", 0.4, 1.0),)

    promoted = original.with_lod(2)
    changed_needs = original.with_needs(needs)

    assert promoted.identity_anchor == _MAIN_ANCHOR
    assert changed_needs.identity_anchor == _MAIN_ANCHOR
    assert promoted.lod == 2
    assert changed_needs.needs == needs
    assert original.lod == 1
    assert original.needs == ()


@pytest.mark.parametrize("npc_ids", [None, ["npc:same"]])
async def test_materialize_keeps_same_npc_anchors_isolated_by_branch(
    identity_events: SqlEventStore, npc_ids: list[str] | None
) -> None:
    await _seed_branch_anchors(identity_events)

    main_profiles = await NpcStore(identity_events, branch_id="main").materialize(npc_ids)
    child_profiles = await NpcStore(identity_events, branch_id="child").materialize(npc_ids)

    assert set(main_profiles) == {"npc:same"}
    assert set(child_profiles) == {"npc:same"}
    assert main_profiles["npc:same"].identity_anchor == _MAIN_ANCHOR
    assert child_profiles["npc:same"].identity_anchor == _CHILD_ANCHOR


@pytest.mark.parametrize("explicit_empty", [False, True])
async def test_empty_database_anchor_stays_empty(
    identity_events: SqlEventStore, explicit_empty: bool
) -> None:
    row = NpcProfile(id="npc:legacy", branch_id="main", name="旧客")
    if explicit_empty:
        row.identity_anchor = ""
    async with identity_events.session_factory() as session:
        session.add(row)
        await session.commit()

    profiles = await NpcStore(identity_events).materialize()

    assert profiles["npc:legacy"].identity_anchor == ""


@pytest.mark.parametrize(
    ("branch_id", "expected_anchor"), [("main", _MAIN_ANCHOR), ("child", _CHILD_ANCHOR)]
)
async def test_assemble_runtime_exposes_branch_identity_anchor(
    identity_events: SqlEventStore, branch_id: str, expected_anchor: str
) -> None:
    await _seed_branch_anchors(identity_events)
    store = NpcStore(identity_events, branch_id=branch_id)

    runtime, _ = await assemble_runtime(store)

    assert runtime.profiles["npc:same"].identity_anchor == expected_anchor
