"""L0 千人地图外统计，分钟步进、事件恢复、零实体增长。"""

from sim.core.persistence.event_validation import validate_store_row
from sim.npc.demography import Demography


def test_thousand_population_advances_per_minute_and_replays():
    runtime = Demography(seed=42)
    assert sum(runtime.population) == 1200
    assert not runtime.tick(59)
    events = runtime.tick(60)
    assert len(events) == 1
    validate_store_row(events[0].to_store_dict())
    assert not runtime.tick(60)
    restored = Demography(seed=42)
    restored.observe(events)
    assert restored.population == runtime.population
    assert restored.grain == runtime.grain
    assert runtime.tick(120) == restored.tick(120)


def test_ten_days_offmap_population_and_supply_are_bounded():
    runtime = Demography(seed=7)
    for tick in range(60, 10 * 86_400 + 1, 60):
        runtime.tick(tick)
    assert 1000 <= sum(runtime.population) <= 1500
    assert all(value >= 0 for value in runtime.grain)
    assert runtime.traders > 0
