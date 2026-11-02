"""Historical profile rows must survive later death/LOD, with every seed column intact."""

import gzip
import json
from dataclasses import replace

import pytest
from sqlalchemy import text

from sim.core.events import npc_death_event, npc_lod_change_event, world_create_event
from sim.core.persistence.anchor_package import (
    AnchorMaterializationError,
    MaterializationHooks,
    collect_corpus_rows,
    diagnose_anchor_materialization,
    encode_corpus_blob,
    materialize_anchor,
    write_anchor_package,
)
from sim.core.persistence.fork import ForkError, fork_from_anchor
from sim.core.persistence.models import Branch, NpcProfile
from sim.core.persistence.npc_store import NpcStore


async def _noop(*args):
    return None


async def _profiles(session, branch="main"):
    return {
        row["id"]: {key: value for key, value in row.items() if key != "branch_id"}
        for row in (
            await session.execute(
                text("SELECT * FROM npc_profiles WHERE branch_id = :bid ORDER BY id"),
                {"bid": branch},
            )
        ).mappings()
    }


async def _seed(session, store):
    session.add(Branch(id="main", status="active", is_current=True))
    session.add_all(
        [
            NpcProfile(id="a", branch_id="main", name="同行者", lod=1, created_at=111.0),
            NpcProfile(
                id="d",
                branch_id="main",
                name="旧日的故人",
                species="human",
                gender="female",
                age=43,
                occupation="窑匠",
                identity_anchor="我在这里烧窑。",
                ocean_openness=61,
                ocean_conscientiousness=72,
                ocean_extraversion=33,
                ocean_agreeableness=84,
                ocean_neuroticism=25,
                pad_pleasure=0.2,
                pad_arousal=-0.3,
                pad_dominance=0.4,
                emotion_updated_tick=0,
                needs='[{"name":"rest","value":0.3}]',
                skills='{"pottery":7}',
                goals='{"short":"守窑"}',
                inventory='[{"item":"陶杯","quantity":2}]',
                knowledge_boundary='{"literacy":0.7}',
                lod=1,
                created_at_tick=0,
                updated_at_tick=0,
                created_at=222.0,
            ),
        ]
    )
    await session.commit()
    await store.append(
        "main", [world_create_event(1, seed=7, entity_ids=("a", "d")).to_store_dict()]
    )


async def _save(session, store, *, anchor="old", branch="main", seq=1, tick=1):
    await write_anchor_package(
        session,
        anchor_id=anchor,
        branch_id=branch,
        seq=seq,
        tick=tick,
        rng_state='{"registry":{"world_seed":7}}',
        agent_override="{}",
        corpus_blob=encode_corpus_blob(await collect_corpus_rows(session, branch)),
    )
    await session.commit()
    return await materialize_anchor(
        store,
        anchor_id=anchor,
        hooks=MaterializationHooks(_noop, _noop, _noop, _noop),
    )


async def _fork(store, package, *, child="child"):
    return await fork_from_anchor(
        store.session_factory,
        parent_branch_id=package.branch_id,
        fork_seq=package.seq,
        fork_tick=package.tick,
        new_branch_id=child,
        preflush=_noop,
        kind="anchor",
        package=package,
    )


@pytest.mark.parametrize("future", ["death", "lod", "quiet"])
async def test_anchor_profiles_equal_all_columns_before_parent_advances(session, store, future):
    await _seed(session, store)
    expected = await _profiles(session)
    package = await _save(session, store)
    projection = NpcStore(store)
    if future == "death":
        await projection.flush_tick([npc_death_event(5, entity_id="d")])
    elif future == "lod":
        await projection.flush_tick([npc_lod_change_event(5, "a", 1, 2, "nearby")])
    parent_head = await _profiles(session)
    result = await _fork(store, package)
    assert await _profiles(session, "child") == expected
    assert result.cloned_rows["npc_profiles"] == 2
    assert await _profiles(session) == parent_head


async def test_death_before_anchor_is_not_resurrected(session, store):
    await _seed(session, store)
    await NpcStore(store).flush_tick([npc_death_event(2, entity_id="d")])
    package = await _save(session, store, seq=2, tick=2)
    await _fork(store, package)
    assert set(await _profiles(session, "child")) == {"a"}


async def test_profile_created_after_anchor_is_not_copied(session, store):
    await _seed(session, store)
    expected = await _profiles(session)
    package = await _save(session, store)
    session.add(NpcProfile(id="future", branch_id="main", name="后来者", created_at_tick=5))
    await session.commit()
    await NpcStore(store).flush_tick([npc_lod_change_event(6, "future", 1, 2, "nearby")])
    await _fork(store, package)
    assert await _profiles(session, "child") == expected


async def test_same_tick_later_lod_event_does_not_leak_into_old_anchor(session, store):
    await _seed(session, store)
    expected = await _profiles(session)
    package = await _save(session, store)
    await NpcStore(store).flush_tick([npc_lod_change_event(1, "a", 1, 2, "nearby")])
    await _fork(store, package)
    assert await _profiles(session, "child") == expected


async def test_head_fork_keeps_current_profile_semantics(session, store):
    await _seed(session, store)
    await NpcStore(store).flush_tick(
        [npc_death_event(5, entity_id="d"), npc_lod_change_event(5, "a", 1, 2, "nearby")]
    )
    expected = await _profiles(session)
    await fork_from_anchor(
        store.session_factory,
        parent_branch_id="main",
        fork_seq=3,
        fork_tick=5,
        new_branch_id="head-child",
        preflush=_noop,
    )
    assert await _profiles(session, "head-child") == expected
    assert set(expected) == {"a"}
    assert expected["a"]["lod"] == 2


async def test_empty_anchor_roster_stays_empty_after_later_seeding(session, store):
    await _seed(session, store)
    await NpcStore(store).flush_tick(
        [npc_death_event(2, entity_id="a"), npc_death_event(2, entity_id="d")]
    )
    package = await _save(session, store, seq=3, tick=2)
    session.add(NpcProfile(id="later", branch_id="main", name="后来的人"))
    await session.commit()
    await _fork(store, package)
    assert await _profiles(session, "child") == {}


async def test_saved_child_roster_is_independent_of_later_ancestor_events(session, store):
    await _seed(session, store)
    package = await _save(session, store)
    await _fork(store, package)
    await session.execute(text("UPDATE branches SET is_current=0 WHERE id='main'"))
    await session.execute(text("UPDATE branches SET is_current=1 WHERE id='child'"))
    await session.commit()
    await NpcStore(store, branch_id="child").flush_tick(
        [npc_lod_change_event(2, "a", 1, 2, "nearby")]
    )
    expected = await _profiles(session, "child")
    child_package = await _save(session, store, anchor="child-old", branch="child", seq=1, tick=2)
    await session.execute(text("UPDATE branches SET is_current=0 WHERE id='child'"))
    await session.execute(text("UPDATE branches SET is_current=1 WHERE id='main'"))
    await session.commit()
    await NpcStore(store).flush_tick(
        [npc_death_event(5, entity_id="d"), npc_lod_change_event(5, "a", 1, 2, "nearby")]
    )
    await _fork(store, child_package, child="grandchild")
    assert await _profiles(session, "grandchild") == expected


@pytest.mark.parametrize("damage", ["legacy", "column", "branch", "duplicate"])
async def test_invalid_profile_baseline_rejects_before_load_hooks(session, store, damage):
    await _seed(session, store)
    await _save(session, store)
    blob = (
        await session.execute(text("SELECT corpus_blob FROM anchor_packages WHERE anchor_id='old'"))
    ).scalar_one()
    body = json.loads(gzip.decompress(blob))
    if damage == "legacy":
        del body["npc_profiles"]
    elif damage == "column":
        del body["npc_profiles"][0]["inventory"]
    elif damage == "branch":
        body["npc_profiles"][0]["branch_id"] = "other"
    else:
        body["npc_profiles"].append(body["npc_profiles"][0])
    await session.execute(
        text("UPDATE anchor_packages SET corpus_blob=:blob WHERE anchor_id='old'"),
        {"blob": gzip.compress(json.dumps(body).encode(), mtime=0)},
    )
    await session.commit()
    diagnosis = await diagnose_anchor_materialization(store, "old")
    assert not diagnosis.ready
    assert diagnosis.reason == "corpus_mismatch"
    called = []

    async def hook(*args):
        called.append(args)

    with pytest.raises(AnchorMaterializationError) as error:
        await materialize_anchor(
            store,
            anchor_id="old",
            hooks=MaterializationHooks(hook, hook, hook, hook),
        )
    assert error.value.reason == "corpus_mismatch"
    assert called == []
    assert set(await _profiles(session)) == {"a", "d"}
    assert await _profiles(session, "child") == {}


async def test_direct_anchor_fork_cannot_bypass_missing_profile_baseline(session, store):
    await _seed(session, store)
    package = await _save(session, store)
    with pytest.raises(ForkError, match="complete NPC profile baseline"):
        await _fork(store, replace(package, profile_rows=None))
    assert await session.get(Branch, "child") is None
    assert await _profiles(session, "child") == {}
