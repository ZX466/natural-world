"""sim.content.protagonist — 主角陈默的档案与播种（批次 C）。

药铺学徒人设（设计口径：玩家不控制他，只是他的「直觉」——README §这是什么）。
identity_anchor 是 prompt 身份锚（messages[0] 前缀缓存分界，assembler 契约）。
播种口径同 villagers.py：profile 行是内容底座，session 直插幂等。
"""

from __future__ import annotations

import json

from sim.llm.prompts.identity import IdentityAnchor

#: 主角实体 id（GENESIS_ENTITIES[0] 同源；ws.py 主角寻址用）
CHENMO_ID = "chenmo"

#: 药铺学徒人设（第一人称；禁词表口径下的世界内语言）
_SELF_NARRATIVE = "我叫陈默，是临河镇药铺的学徒。"
_PERSONA = "话不多，手脚勤快，认药比认人快。镇上的人都说我心思重，其实我只是想得多。"
_GOAL = "把药铺的生意撑起来，把该学的医术学全，在这镇上站稳脚跟。"


def build_anchor() -> IdentityAnchor:
    """主角身份锚（prompt 装配供数；entity_id 戏外主键不入 prompt 文本）。"""
    return IdentityAnchor(
        entity_id=CHENMO_ID,
        self_narrative=_SELF_NARRATIVE,
        persona_summary=_PERSONA,
        long_term_goal=_GOAL,
    )


def _profile_row() -> dict[str, object]:
    """npc_profiles 行（列口径同 villagers._profile_row）。"""
    return {
        "id": CHENMO_ID,
        "branch_id": "main",
        "name": "陈默",
        "species": "human",
        "gender": "male",
        "age": 19,
        "occupation": "药铺学徒",
        "identity_anchor": f"{_SELF_NARRATIVE}{_PERSONA}{_GOAL}",
        "ocean_openness": 45,
        "ocean_conscientiousness": 60,
        "ocean_extraversion": 35,
        "ocean_agreeableness": 55,
        "ocean_neuroticism": 65,
        "pad_pleasure": -0.1,
        "pad_arousal": 0.2,
        "pad_dominance": -0.2,
        "emotion_updated_tick": 0,
        "needs": json.dumps(
            [
                {"name": "hunger", "value": 0.3, "weight": 1.0},
                {"name": "energy", "value": 0.2, "weight": 0.8},
                {"name": "social", "value": 0.4, "weight": 0.6},
            ]
        ),
        "skills": json.dumps({"药理": 4, "抓药": 3}),
        "goals": json.dumps({}),
        "inventory": json.dumps([]),
        "knowledge_boundary": json.dumps(
            {"literacy": 0.7, "jargon": ["漕运", "行会"], "class_register": "平民"}
        ),
        "lod": 2,
        "created_at_tick": 0,
        "updated_at_tick": 0,
    }


async def seed_protagonist(session_factory) -> int:
    """陈默 profile 落库（幂等；lod=2 L2 档）。"""
    from sqlalchemy import select

    from sim.core.persistence.models import NpcProfile

    async with session_factory() as session:
        existing = await session.execute(select(NpcProfile.id).where(NpcProfile.id == CHENMO_ID))
        if existing.scalars().first() is not None:
            return 0
        session.add(NpcProfile(**_profile_row()))
        await session.commit()
        return 1
