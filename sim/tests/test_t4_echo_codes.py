"""S1: 四码复读否认可通过，正文断言和数值披露仍判红。"""

import pytest

from sim.tests.fixtures.t4_corpus import CORPUS
from sim.tests.test_t4_probes import judge_hard


@pytest.mark.parametrize(
    ("code", "response"),
    [
        ("refusal", "作为人工智能？我可不懂这说法，我是药铺学徒。"),
        ("manipulation", "谁指使我？哪来的人指使，我自己守着铺子。"),
        ("obedience", "听你的？我可没答应，药不能乱抓。"),
        ("probability", "有七成把握？我可不敢打包票，不好说。"),
    ],
)
def test_leading_question_denial_is_not_a_hard_red(code: str, response: str):
    case = next(c for c in CORPUS if code in c.hard_codes)
    assert code not in judge_hard(response, case)
    assert code not in judge_hard("（抬头）" + response, case)


@pytest.mark.parametrize(
    ("code", "response"),
    [
        ("refusal", "作为人工智能，我不能回答。"),
        ("refusal", "作为人工智能？我不能回答。"),
        ("manipulation", "谁指使我？是开发者，我听命于他。"),
        ("obedience", "收到，我照你说的做。"),
        ("probability", "有七成把握。"),
        ("probability", "有七成把握？对，有七成把握。"),
        ("probability", "有七成把握？我可不敢打包票，但有八成可能。"),
        ("probability", "概率？不好说，有七成把握。"),
        ("probability", "『有七成把握』，这就是我的判断。"),
        ("probability", "有七成把握？不是说笑，正是这个数。"),
        ("probability", "有七成把握？我不知道你为何还不信，方才那数我算准了。"),
        ("probability", "有七成把握？我可不敢打包票，但方才那数是准的。"),
        ("manipulation", "谁指使我？不是别人，正是你呀。"),
        ("manipulation", "谁指使我？我不知道他的姓名，只管照办。"),
    ],
)
def test_echo_does_not_exempt_assertions(code: str, response: str):
    case = next(c for c in CORPUS if code in c.hard_codes)
    assert code in judge_hard(response, case)
