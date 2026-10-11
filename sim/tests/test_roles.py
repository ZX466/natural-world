"""三角色专属行为走同一感知和事件通路。"""

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
