"""三角色专属行为走同一感知和事件通路。"""

import pytest

from sim.npc.roles import role_events
from sim.perception.frame import Channel, Observation, PerceptionFrame
from sim.perception.senses import rtoken_of


def test_xiaoman_collects_heard_information_and_suwan_retains_uncertainty():
    frame = PerceptionFrame(
        observer="rt-role",
        tick=1,
        observations=(
            Observation(
                channel=Channel.HEARING,
                subject="other",
                description="货郎说河边的船迟了。",
                strength=0.5,
            ),
        ),
    )
    events = role_events("villager_02", frame, 1)
    assert "货郎" in str(events[0].payload["content"])
    assert "说不准" in str(role_events("villager_03", frame, 1)[0].payload["content"])


@pytest.mark.parametrize(
    "description",
    [
        # `narrate_sound` 的真实产出形态（perception/narrate.py:63）
        "传来一阵脚步声，像是奚船家。",
        "有扇门开了又关。",
        "有人喊了一嗓子！",
        "那边传来打斗的响动？",
        # 无标点的短句（防御：别把中间的字剥掉）
        "有些动静",
    ],
)
def test_heard_clause_never_doubles_punctuation(description: str) -> None:
    """感知描述是**完整句**，嵌进「听见…，」时必须先去尾句号。

    真实库 `npc.monologue` 实测：209 条里 **60 条**命中（= thought 面全部 60 条），
    形态是 `听见传来一阵脚步声，像是奚船家。，先记在心里。`「句号紧跟逗号」。
    """
    frame = PerceptionFrame(
        observer="rt-role",
        tick=1,
        observations=(
            Observation(
                channel=Channel.HEARING, subject="other", description=description, strength=0.5
            ),
        ),
    )
    for npc_id in ("villager_02", "villager_03"):
        content = str(role_events(npc_id, frame, 1)[0].payload["content"])
        assert "。，" not in content, f"{npc_id} 出现「句号紧跟逗号」：{content!r}"
        assert "！，" not in content and "？，" not in content, f"{npc_id}：{content!r}"
        # 剥标点不能剥掉正文
        assert description.rstrip().rstrip("。？！") in content


def test_zhaotie_loyalty_and_conscience_react_to_heard_violence():
    frame = PerceptionFrame(
        observer=rtoken_of("villager_01"),
        tick=1,
        observations=(
            Observation(
                channel=Channel.HEARING,
                subject="other",
                description="来人啊，他行凶了！",
                strength=0.8,
            ),
        ),
    )
    content = str(role_events("villager_01", frame, 1)[0].payload["content"])
    assert "镖局" in content and "救" in content
