"""B1 叙事层：同档气味文案不连续重复（spec §4.1 的抑制口径）。"""

from __future__ import annotations

from sim.api.narration_cache import NarratedCache

SMELLY = "你闻到：空气里飘着一股明显的味道。"


def _frame(text: str = SMELLY) -> tuple[object, str]:
    return (object(), text)


def test_second_identical_line_is_softened() -> None:
    cache = NarratedCache()
    first = cache.remember("chenmo", _frame())
    second = cache.remember("chenmo", _frame())
    assert "明显的味道" in first
    assert "还在" in second, "第二次应换成省略式，而不是原句"


def test_third_and_later_are_dropped() -> None:
    cache = NarratedCache()
    for _ in range(2):
        cache.remember("chenmo", _frame())
    third = cache.remember("chenmo", _frame())
    assert third == "四周很安静。", "第三次起整句不出现，回落到空帧文案"


def test_a_different_line_resets_the_counter() -> None:
    cache = NarratedCache()
    cache.remember("chenmo", _frame())
    cache.remember("chenmo", _frame())
    assert "还在" not in cache.remember("chenmo", _frame("你闻到：隐约有一丝陌生的气味。"))


def test_a_different_observer_keeps_its_own_counter() -> None:
    cache = NarratedCache()
    cache.remember("chenmo", _frame())
    cache.remember("chenmo", _frame())
    # 换一个人：不该继承陈默的重复计数
    assert "还在" not in cache.remember("auntie", _frame())


def test_clear_resets_everything() -> None:
    cache = NarratedCache()
    cache.remember("chenmo", _frame())
    cache.remember("chenmo", _frame())
    cache.clear()
    assert "还在" not in cache.remember("chenmo", _frame())
