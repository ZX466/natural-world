"""E3：最小经济——coin.grant 事件 + CoinLedger 余额 + 价目表。"""


from sim.core.events import EventKind, coin_grant_event
from sim.core.persistence.event_validation import PAYLOAD_MODELS, validate_store_row
from sim.core.world import TickContext, WorldState, build_default_bus
from sim.world.economy import GOODS, CoinLedger, buy_price


def test_coin_grant_event_and_registry():
    ev = coin_grant_event(tick=5, owner_id="chenmo", delta=-12, note="buy:herb")
    assert ev.event_type is EventKind.COIN_GRANT
    assert ev.actor_id == "chenmo"
    validate_store_row(ev.to_store_dict())
    assert PAYLOAD_MODELS[EventKind.COIN_GRANT].model_validate(
        {"owner_id": "chenmo", "delta": -12, "note": "buy:herb"}
    )


def test_coin_grant_fold_noop_hash_stable():
    bus = build_default_bus()
    state = WorldState(world_seed=42)
    ev = coin_grant_event(tick=0, owner_id="chenmo", delta=5, note="sell:herb")
    before = state.state_hash()
    assert bus.apply(state, ev, TickContext()).state.state_hash() == before


def test_ledger_applies_and_rejects_negative():
    led = CoinLedger()
    led.apply_grant("chenmo", 100, tick=1)
    assert led.balance_of("chenmo") == 100
    assert led.apply_grant("chenmo", -200, tick=2) is False  # 余额不够：拒绝
    assert led.balance_of("chenmo") == 100
    assert led.apply_grant("chenmo", -30, tick=3) is True
    assert led.balance_of("chenmo") == 70


def test_goods_catalog_and_price_bounds():
    ids = [g.id for g in GOODS]
    assert ids == ["herb", "salve", "meal"]
    for good in GOODS:
        price = buy_price(good.id, tick=12345, seed=42)
        assert int(good.price * 0.8) <= price <= int(good.price * 1.2) + 1
        assert buy_price(good.id, tick=12345, seed=42) == price  # C5 同输入同输出


def test_buy_intent_produces_grant_and_monologue():
    """陈默 buy 执行面：余额够 → coin.grant(负) + thought 独白。"""
    from sim.agent.driver import ChenmoDriver
    from sim.content.protagonist import build_anchor
    from sim.core.clock import GameClock
    from sim.core.tick import TickLoop
    from sim.core.world import EntityState, build_default_bus
    from sim.world.economy import CoinLedger

    class _NullLlm:
        pass

    state = WorldState(
        world_seed=42, entities={"chenmo": EntityState(entity_id="chenmo", pos=(30, 46))}
    )
    loop = TickLoop(clock=GameClock(speed=1.0), bus=build_default_bus(), state=state)
    led = CoinLedger()
    led.apply_grant("chenmo", 100, tick=0)
    driver = ChenmoDriver(
        anchor=build_anchor(),
        llm=_NullLlm(),
        profile_provider=lambda: None,
        economy_provider=lambda: (led, 42),
    )
    from sim.agent.intent import Intent

    driver._pending.append(
        Intent(action="buy", target_id="herb", reason="铺子里草药见了底", confidence=0.9)
    )
    executed = driver.execute_pending(loop, pathfinder=None)
    assert executed == 1
    events = loop.drain_events()
    grants = [e for e in events if e.event_type.value == "coin.grant"]
    assert len(grants) == 1
    assert grants[0].payload["delta"] < 0  # 买=出账
    assert led.balance_of("chenmo") < 100
    monos = [e for e in events if e.event_type.value == "npc.monologue"]
    assert len(monos) >= 1  # 结果独白在场（另有一条 intent.reason 独白，D 批既有面）
    assert any("草药" in str(m.payload["content"]) for m in monos)  # 结果句含货名


def test_buy_insufficient_funds_no_grant():
    """余额不够：零 grant（账本拒）+ 独白仍是「买不起」（fail-soft 叙事）。"""
    from sim.agent.driver import ChenmoDriver
    from sim.content.protagonist import build_anchor
    from sim.core.clock import GameClock
    from sim.core.tick import TickLoop
    from sim.core.world import EntityState, build_default_bus
    from sim.world.economy import CoinLedger

    class _NullLlm:
        pass

    state = WorldState(
        world_seed=42, entities={"chenmo": EntityState(entity_id="chenmo", pos=(30, 46))}
    )
    loop = TickLoop(clock=GameClock(speed=1.0), bus=build_default_bus(), state=state)
    led = CoinLedger()  # 余额 0
    driver = ChenmoDriver(
        anchor=build_anchor(),
        llm=_NullLlm(),
        profile_provider=lambda: None,
        economy_provider=lambda: (led, 42),
    )
    from sim.agent.intent import Intent

    driver._pending.append(
        Intent(action="buy", target_id="salve", reason="想备一帖药膏", confidence=0.9)
    )
    driver.execute_pending(loop, pathfinder=None)
    events = loop.drain_events()
    assert not [e for e in events if e.event_type.value == "coin.grant"]
    assert [e for e in events if e.event_type.value == "npc.monologue"]
