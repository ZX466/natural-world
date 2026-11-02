"""名册身份自洽：`identity_anchor` 必须与同一行的 `name`/`occupation` 一致。

根因（2026-11-02 实测）：`content/villagers.py::_profile_row` 的 `name`/`occupation`
走 `ROLES` 覆盖（`role[0] if role else p.name`），但 `identity_anchor` 用**名册原始值**
拼（`f"我是{p.name}，{p.occupation}。"`）。三个专属角色因此自相矛盾：

    villager_01  name=赵铁  occupation=镖师   identity_anchor="我是赵铁柱，农人。"
    villager_02  name=小满  occupation=乞丐   identity_anchor="我是钱小满，商贩。"
    villager_03  name=苏婉  occupation=药铺掌柜 identity_anchor="我是孙二娘，匠人。"

为什么现在才咬人：`agent/npc_l2.py:243` 把 `identity_anchor` 直接塞进
`IdentityAnchor.self_narrative` —— 是 prompt 的**第一条 system 消息**。第十九轮之前
L2 是空壳（全仓不读 `lod == 2`），这个矛盾没有观测面；接上之后，升格村民开口时
模型被告知「我是赵铁柱，农人」，而玩家头顶名牌写的是「赵铁·镖师」。

本测试锁两件事：
1. 纯函数层：`_profile_row` 产出的 `identity_anchor` 与同行 `name`/`occupation` 同源；
2. 落库层：`seed_villagers` 写入的行同样自洽（防将来绕过 `_profile_row`）。
"""

from __future__ import annotations

import json

import pytest

pytestmark = pytest.mark.t1


class TestProfileRowIdentity:
    @staticmethod
    def _rows() -> list[dict[str, object]]:
        from sim.content.villagers import _profile_row, build_roster

        return [_profile_row(p) for p in build_roster()]

    def test_every_row_anchor_matches_name_and_occupation(self) -> None:
        """全 50 行：`identity_anchor` == f"我是{name}，{occupation}。"。"""
        bad = []
        for row in self._rows():
            expected = f"我是{row['name']}，{row['occupation']}。"
            if row["identity_anchor"] != expected:
                bad.append((row["id"], row["identity_anchor"], expected))
        assert not bad, f"{len(bad)} 行身份锚与姓名/职业不符：{bad[:5]}"

    @pytest.mark.parametrize("npc_id", ["villager_01", "villager_02", "villager_03"])
    def test_role_overridden_rows_use_role_identity(self, npc_id: str) -> None:
        """三个专属角色：身份锚必须取 `ROLES` 覆盖后的姓名与职业（不是名册原值）。"""
        from sim.npc.roles import ROLES

        row = next(r for r in self._rows() if r["id"] == npc_id)
        role_name, _age, role_occupation = ROLES[npc_id]
        assert row["name"] == role_name
        assert row["occupation"] == role_occupation
        assert row["identity_anchor"] == f"我是{role_name}，{role_occupation}。"

    def test_non_role_row_keeps_roster_identity(self) -> None:
        """未被 `ROLES` 覆盖的村民仍取名册原值（改动不能波及 47 人）。"""
        from sim.content.villagers import build_roster

        roster = {p.npc_id: p for p in build_roster()}
        row = next(r for r in self._rows() if r["id"] == "villager_04")
        source = roster["villager_04"]
        assert row["name"] == source.name
        assert row["occupation"] == source.occupation
        assert row["identity_anchor"] == f"我是{source.name}，{source.occupation}。"


class TestSeededRowsIdentity:
    async def test_seeded_rows_anchor_matches_columns(self, tmp_path) -> None:
        """落库层同样自洽（读侧 `npc_store` 取的就是这三列）。"""
        from sqlalchemy import select
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

        from sim.content.villagers import seed_villagers
        from sim.core.persistence.database import init_database
        from sim.core.persistence.models import NpcProfile

        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'identity.db'}")
        await init_database(engine)
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        try:
            assert await seed_villagers(factory) == 50
            async with factory() as session:
                rows = (await session.execute(select(NpcProfile))).scalars().all()
            bad = [
                (r.id, r.name, r.occupation, r.identity_anchor)
                for r in rows
                if r.identity_anchor != f"我是{r.name}，{r.occupation}。"
            ]
            assert not bad, f"库内身份锚与姓名/职业不符：{bad[:5]}"
            # 锚必须能被 JSON 化的下游消费（L2 直接塞 prompt，不做转义）
            assert all(json.dumps(r.identity_anchor, ensure_ascii=False) for r in rows)
        finally:
            await engine.dispose()
