"""Review 修复验证：I2 装配面——_drain_loads 分叉成功后必须重置全部账本。

（test_e_fix_ledger_reset.py 钉 reset 方法语义；本钉钉**调用点存在**——
「写了新函数不换调用点=没修」教训的防线。）
"""

from pathlib import Path

_MAIN = Path("sim/api/main.py").read_text(encoding="utf-8")


def test_drain_loads_resets_all_runtime_ledgers():
    lines = _MAIN.splitlines()
    start = next(i for i, ln in enumerate(lines) if "async def _drain_loads" in ln)
    end = next(i for i, ln in enumerate(lines) if "def register_new_branch" in ln)
    block = "\n".join(lines[start:end])
    assert "combat_ledger.reset()" in block, "_drain_loads 未重置 combat_ledger"
    assert "coin_ledger.reset()" in block, "_drain_loads 未重置 coin_ledger"
    assert "chat_ledger.reset()" in block, "_drain_loads 未重置 chat_ledger"
    # 冷却账本（调用方持有的跨拍记忆态）同清
    for ledger in ("monologue_last", "chat_last", "retell_last", "wage_last"):
        assert f"{ledger}.clear()" in block, f"_drain_loads 未清 {ledger}"
