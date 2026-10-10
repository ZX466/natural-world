"""E2：陈默 recall 并入 ledger 记忆（prompt [记忆] 段双源）。"""

from sim.agent.chenmo_memory import merge_ledger_entries


def test_merge_puts_ledger_first_and_caps():
    ledger_texts = ("镇口的老张今天神色不对。",)
    base = ("三天前的雨。", "更早的事。", "再早的事。", "第四条。")
    merged = merge_ledger_entries(base, ledger_texts, top_k=4)
    assert merged[0] == "镇口的老张今天神色不对。"
    assert len(merged) == 4
    assert "第四条。" not in merged  # 基础条目被挤掉一条


def test_merge_empty_ledger_unchanged():
    base = ("a", "b")
    assert merge_ledger_entries(base, (), top_k=3) == ("a", "b")


def test_merge_dedupes_identical_texts():
    base = ("同一条。", "别的。")
    merged = merge_ledger_entries(base, ("同一条。",), top_k=3)
    assert merged == ("同一条。", "别的。")
