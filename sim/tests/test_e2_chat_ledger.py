"""E2：进程内关系/记忆账本（禁第二 SQL 驱动——纯 dict）。"""

import pytest

from sim.npc.chat_ledger import ChatLedger


def test_adjust_creates_row_with_positive_delta():
    led = ChatLedger()
    led.adjust("a", "b", kind="chat")
    rows = led.relations_of("a")
    assert rows["b"]["affection"] > 0.0  # a 对 b 好感上升


def test_adjust_clamps_to_unit_range():
    led = ChatLedger()
    for _ in range(200):
        led.adjust("a", "b", kind="chat")
    assert led.relations_of("a")["b"]["affection"] <= 1.0


def test_remember_ring_buffer():
    led = ChatLedger()
    for i in range(25):
        led.remember("a", f"第{i}句话", tick=i)
    mems = led.memories_of("a")
    assert len(mems) == 20  # 上限 20
    assert mems[-1][1] == "第24句话"  # 保留最新


def test_chat_kind_unknown_rejected():
    led = ChatLedger()
    with pytest.raises(ValueError):
        led.adjust("a", "b", kind="nope")


def test_retell_kind_moves_trust():
    led = ChatLedger()
    led.adjust("a", "b", kind="retell")
    assert led.relations_of("a")["b"]["trust"] > 0.0


def test_memories_of_is_copy():
    led = ChatLedger()
    led.remember("a", "x", tick=1)
    snap = led.memories_of("a")
    snap.append((99, "脏数据"))
    assert len(led.memories_of("a")) == 1  # 外部改不动内部缓冲
