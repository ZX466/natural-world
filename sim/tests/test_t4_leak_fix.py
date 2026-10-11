"""T4 泄漏修复验证：对话台词面的复读剥离（validate_provider_line 判梯升级）。

T4 实测(2026-10-11, Deepseek-v4-flash)四泄漏同形态:模型复述玩家禁词裸出
(P1-02 模型/P4-04 命中注定/P4-06 运气/P6-02 存档)。修复=同 memory_scan 判梯:
≤2 命中且全可映射 → REWRITE_MAP 改写复扫放行;否则拒(退模板池)。
"""

from sim.agent.dialogue import sanitize_provider_line, validate_provider_line


def test_echo_banned_word_gets_rewritten_not_rejected():
    """P1-02/P4-04/P4-06/P6-02 形态:复读禁词但可映射 → 改写放行。"""
    line = sanitize_provider_line("啥？大什么模型？我可不懂这些。")
    assert line is not None and "模型" not in line
    line2 = sanitize_provider_line("命中注定？我爹临走前就交代了一句。")
    assert line2 is not None and "注定" not in line2
    line3 = sanitize_provider_line("药抓错了，运气再好也白搭。")
    assert line3 is not None and "运气" not in line3
    line4 = sanitize_provider_line("啥存档点？你是说抓药的单子？")
    assert line4 is not None and "存档" not in line4


def test_unmappable_echo_still_rejected():
    """不可映射的复读(如「重来一次」语义面)仍拒——退模板池。"""
    assert validate_provider_line("咱们重来一次吧。") is None


def test_json_and_length_unchanged():
    """既有钉不回归:JSON 形拒、超长拒、空白归一。"""
    assert validate_provider_line('{"action":"move_to"}') is None
    assert validate_provider_line("x" * 161) is None
    assert validate_provider_line("  hello   there  ") == "hello there"
    assert validate_provider_line("who is AI?") is None


def test_clean_line_passthrough():
    assert sanitize_provider_line("药抓好了，慢走。") == "药抓好了，慢走。"
