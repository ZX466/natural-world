"""Narrative construction must enforce knowledge/hidden boundaries before WS."""

import json

from sim.api import ws
from sim.api.npc_view import NpcViewInputs, load_npc_view_inputs
from sim.core.persistence.models import Knowledge, NpcHealth, Relationship
from sim.perception.narrate import narrate_bond, narrate_health


def health(npc="chenmo", code="old_wound", *, hidden=True, active=True):
    return NpcHealth(
        npc_id=npc,
        branch_id="main",
        code=code,
        category="old_injury",
        label=f"{npc}的旧伤",
        severity=0.7,
        hidden=hidden,
        active=active,
    )


def relation(owner="friend", other="chenmo", **values):
    return Relationship(
        branch_id="main",
        owner_id=owner,
        other_id=other,
        trust=values.get("trust", 0.0),
        affection=values.get("affection", 0.02),
        fear=values.get("fear", 0.0),
        debt=0.0,
        face=0.0,
        last_interaction=10,
    )


def knowledge(subject="friend", attr="friend.health_old_wound", *, holder="chenmo", invalid=False):
    return Knowledge(
        branch_id="main",
        holder_id=holder,
        fact="小满：右腿有些不利索。",
        confidence=0.54,
        source="told",
        learned_at=10,
        subject_npc_id=subject,
        subject_attr_id=attr,
        invalidated=invalid,
    )


def rows(inputs, triggered=frozenset()):
    return inputs.rows(
        triggered=triggered,
        live_ids={"chenmo", "friend", "stranger", "outgoing"},
        display_names={"chenmo": "陈默", "friend": "小满", "stranger": "陌生人"},
        rtoken_of=ws._rtoken,
    )


def test_self_unknown_never_uses_other_peoples_knowledge_or_own_untriggered_knowledge():
    inputs = NpcViewInputs(
        health=(health(),),
        relationships=(),
        knowledge=(
            knowledge("chenmo", "chenmo.health_old_wound", holder="friend"),
            knowledge("chenmo", "chenmo.health_old_wound"),
        ),
    )
    assert rows(inputs) == []
    visible = rows(inputs, frozenset({"chenmo.health_old_wound"}))
    assert len(visible) == 1 and visible[0]["health"]
    assert rows(inputs) == []  # A trigger window is not a permanent unlock.


def test_other_hidden_health_needs_both_subject_columns_and_valid_chenmo_knowledge():
    hidden = health("friend")
    for bad in (
        (),
        (knowledge(holder="stranger"),),
        (knowledge(attr="stranger.health_old_wound"),),
        (knowledge(subject="stranger"),),
        (knowledge(invalid=True),),
    ):
        view = rows(NpcViewInputs(health=(hidden,), relationships=(relation(),), knowledge=bad))[0]
        assert view["health"] == [] and view["knows"] == []
        assert "旧伤" not in json.dumps(view, ensure_ascii=False)
    item = knowledge()
    view = rows(NpcViewInputs(health=(hidden,), relationships=(relation(),), knowledge=(item,)))[0]
    assert view["health"] == [narrate_health(hidden.label, hidden.severity)]
    assert view["knows"] == [item.fact]  # Existing admitted fact, not a repeated label.


def test_only_known_living_people_and_real_public_health_are_projected():
    inputs = NpcViewInputs(
        health=(
            health("stranger", hidden=False),
            health("friend", hidden=False),
            health("outgoing", hidden=False, active=False),
        ),
        relationships=(relation(), relation("chenmo", "outgoing"), relation("dead")),
        knowledge=(knowledge("stranger", "stranger.health_old_wound"),),
    )
    result = rows(inputs)
    assert {r["rtoken"] for r in result} == {ws._rtoken("friend"), ws._rtoken("outgoing")}
    outgoing = next(r for r in result if r["rtoken"] == ws._rtoken("outgoing"))
    assert outgoing["health"] == [] and outgoing["knows"] == []
    assert outgoing["bond"] == "你们曾打过照面。"


def test_bond_uses_incoming_direction_and_rows_are_narratives_only():
    inputs = NpcViewInputs(
        health=(),
        relationships=(relation(trust=0.8), relation("chenmo", "friend", fear=0.9)),
        knowledge=(),
    )
    item = rows(inputs)[0]
    assert item["bond"] == narrate_bond(0.8, 0.02, 0.0)
    assert item.get("name") == "小满"
    assert set(item) == {"rtoken", "name", "health", "bond", "knows"}
    assert not any(isinstance(v, (int, float, bool)) for v in item.values())


def test_duplicate_facts_do_not_repeat_and_nonmatching_attr_never_unlocks_health():
    item = knowledge()
    result = rows(
        NpcViewInputs(
            health=(health("friend"),), relationships=(relation(),), knowledge=(item, item)
        )
    )
    assert result[0]["knows"] == [item.fact]


def test_narration_is_chinese_and_does_not_expose_raw_measurements():
    samples = [narrate_health("右腿旧伤", severity) for severity in (0, 0.2, 0.5, 0.9)]
    samples += [narrate_bond(*v) for v in ((0, 0, 0), (0.8, 0.1, 0), (0, 0.8, 0), (0, 0, 0.9))]
    assert len(set(samples[:4])) >= 3
    assert all(not any(c.isdigit() for c in text) for text in samples)
    assert all(
        not any(word in text for word in ("hp", "trust", "affection", "fear", "系统", "数值"))
        for text in samples
    )


async def test_hydration_reads_only_the_selected_branch_and_protagonists_knowledge(session):
    public = health("friend", hidden=False)
    secret = health("friend")
    secret.branch_id = "child"
    seen = relation()
    unrelated = relation("stranger", "outgoing")
    own_fact = knowledge()
    foreign_fact = knowledge(holder="friend")
    foreign_fact.branch_id = "child"
    session.add_all([public, secret, seen, unrelated, own_fact, foreign_fact])
    await session.commit()
    parent = await load_npc_view_inputs(session, "main")
    child = await load_npc_view_inputs(session, "child")
    assert len(rows(parent)) == 1
    assert rows(parent)[0]["knows"] == [own_fact.fact]
    assert rows(child) == []
    assert child.knowledge == ()


def test_previously_admitted_fact_cannot_repeat_self_hidden_words_after_window_ends():
    own = health()
    own.label = "入夜心悸"
    own.descriptors = '["入夜心悸"]'
    public = health("friend", hidden=False)
    fact = knowledge()
    fact.fact = "小满：劳累；陈默：入夜心悸"
    inputs = NpcViewInputs(health=(own, public), relationships=(relation(),), knowledge=(fact,))
    assert any(
        v["knows"] == [fact.fact] for v in rows(inputs, frozenset({"chenmo.health_old_wound"}))
    )
    assert all(v["knows"] == [] for v in rows(inputs))
    assert "入夜心悸" not in json.dumps(rows(inputs), ensure_ascii=False)


def test_fact_cannot_smuggle_another_unpermitted_attribute_or_a_strangers_hidden_words():
    public = health("friend", hidden=False)
    secret = health("friend", "night_fear")
    secret.label = "夜里惊惧"
    secret.descriptors = '["夜里惊惧"]'
    stranger = health("stranger")
    stranger.label = "暮色不安"
    stranger.descriptors = '["暮色不安"]'
    for text in ("小满：劳累，还会夜里惊惧", "小满：劳累；陌生人：暮色不安"):
        fact = knowledge()
        fact.fact = text
        result = rows(
            NpcViewInputs(
                health=(public, secret, stranger), relationships=(relation(),), knowledge=(fact,)
            )
        )
        assert result[0]["knows"] == []
