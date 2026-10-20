"""sim.content.villagers — 50 村民确定性名册与播种（批次 B）。

DESIGN §13 / m2-npc-cognition：MVP = 50 NPC 自转。本模块是**内容面**：
确定性生成名册（无 random——重跑幂等、可 diff），落库幂等（已有 profile 即
跳过）。出生位散布见 spawn_positions（环形射线找可走格，确定性）。

L0/L1 配比：M2 收官线 50 全 L1（lod=1）起步；L0 统计档随 LOD 降格域启用
（runtime.tick 已按 lod>0 过滤，将来降格只改数据不动代码）。
"""

from __future__ import annotations

import hashlib
import json

from sim.npc.model import Need, NpcProfileData
from sim.world.map import TileMap

# ---------------------------------------------------------------------------
# 名册常量（确定性：任何生成规则改动都会改变名册 → 需重审事件兼容性）
# ---------------------------------------------------------------------------

#: 50 名村民姓名（临河镇风味；顺序即 id 序，禁重排）
VILLAGER_NAMES: tuple[str, ...] = (
    "赵铁柱",
    "钱小满",
    "孙二娘",
    "李阿婆",
    "周木匠",
    "吴秀才",
    "郑屠户",
    "王寡妇",
    "冯铁匠",
    "陈货郎",
    "褚大夫",
    "卫渔夫",
    "蒋樵夫",
    "沈绣娘",
    "韩书生",
    "杨豆腐",
    "朱猎户",
    "秦寡言",
    "尤灯匠",
    "许豆腐",
    "何篾匠",
    "吕窑工",
    "施茶博士",
    "张货郎",
    "孔账房",
    "曹鞋匠",
    "严药童",
    "华染坊",
    "金泥瓦",
    "魏船工",
    "陶罐匠",
    "姜烧饼",
    "戚剃头",
    "谢更夫",
    "邹木匠",
    "喻桶匠",
    "柏酒家",
    "水磨坊",
    "窦鸡贩",
    "章乞丐",
    "云游道",
    "苏教头",
    "潘裁缝",
    "葛园丁",
    "奚船家",
    "范盐商",
    "彭花匠",
    "郎游方",
    "鲁大脚",
    "韦小乙",
)

VILLAGER_IDS: tuple[str, ...] = tuple(f"villager_{i + 1:02d}" for i in range(len(VILLAGER_NAMES)))

#: GOD 古风外观池（2026-10-12 D1-D5 裁决兑现；产物由 build_god_characters.py
#: 生成 → client/public/assets/sprites/god_villager_*.png，前端 texture key 同名）。
#: D4 红线：军事/名人不入池；桃花源 12 张 + 空城计平民 5 张 = 17 张确定性轮转，
#: 治「全员同皮」。
GOD_SPRITE_POOL: tuple[str, ...] = (
    "god_villager_taocunzhang",
    "god_villager_acheng",
    "god_villager_ali",
    "god_villager_xiaolan",
    "god_villager_zhouyue",
    "god_villager_mengjiaoshou",
    "god_villager_xuning",
    "god_villager_taobo",
    "god_villager_axiu",
    "god_villager_ayuan",
    "god_villager_linkai",
    "god_villager_ada",
    "god_villager_zhibufu",
    "god_villager_liangcangguanshi",
    "god_villager_chuanlingbing",
    "god_villager_laojunhou",
    "god_villager_zuheshishen",
)


def sprite_for_entity(entity_id: str) -> str:
    """entity_id → 前端 texture key（确定性纯函数，sha256，C5 无 RNG）。

    chenmo 恒 "protagonist"（中性 texture key——出戏红线：快照文本禁含内部
    id 词面 "chenmo"，test_ws_gateway W 系列钉；villager → GOD 池哈希取模。
    只吃 entity_id，不吃世界状态——零出戏泄漏面（ws.py 出站口与
    测试同源调用，单一真相源）。
    """
    if entity_id == "chenmo":
        return "protagonist"
    digest = hashlib.sha256(f"sprite:{entity_id}".encode()).digest()
    return GOD_SPRITE_POOL[int.from_bytes(digest[0:4], "big") % len(GOD_SPRITE_POOL)]


#: 职业池（按序循环分配；与姓名风味对齐即可，无机械耦合）
OCCUPATIONS: tuple[str, ...] = (
    "农人",
    "商贩",
    "匠人",
    "渔夫",
    "樵夫",
    "伙计",
    "杂役",
    "艺人",
)

#: 需求初值（确定性哈希散布，人人略不同：hunger/energy/social ∈ [0.05,0.55]）
_NEED_BASE = ("hunger", "energy", "social")


def _hash_u32(*parts: object) -> int:
    digest = hashlib.sha256(":".join(str(p) for p in parts).encode()).digest()
    return int.from_bytes(digest[0:4], "big")


def build_roster() -> tuple[NpcProfileData, ...]:
    """确定性 50 村民名册（重跑逐位一致；frozen 数据类）。"""
    roster: list[NpcProfileData] = []
    for i, (nid, name) in enumerate(zip(VILLAGER_IDS, VILLAGER_NAMES, strict=True)):
        h1 = _hash_u32(nid, "ocean") % 101
        h2 = _hash_u32(nid, "pad") % 101
        needs = tuple(
            Need(
                name=n,
                value=round(0.05 + (_hash_u32(nid, n) % 51) / 100.0, 2),
                weight=1.0,
            )
            for n in _NEED_BASE
        )
        roster.append(
            NpcProfileData(
                npc_id=nid,
                name=name,
                occupation=OCCUPATIONS[i % len(OCCUPATIONS)],
                ocean=(
                    25.0 + h1 % 51,  # openness 25-75
                    25.0 + (h1 * 7) % 51,
                    25.0 + (h1 * 13) % 51,
                    25.0 + (h1 * 17) % 51,
                    25.0 + (h1 * 23) % 51,
                ),
                pad=((h2 % 41 - 20) / 20.0, 0.0, 0.0),
                needs=needs,
                lod=1,
            )
        )
    return tuple(roster)


# ---------------------------------------------------------------------------
# 出生位散布（世界装配用：创世名册 50+1 实体错格落可走草地）
# ---------------------------------------------------------------------------

#: 散布基点（2026-10-12 D6-D8 换图：村广场 anchor 侧；与 main.SPAWN_TILE 同源）
SPAWN_BASE: tuple[int, int] = (100, 53)


def territory_spawn_positions(
    tile_map: TileMap,
    roster: list[str],
    *,
    occupied: dict[str, tuple[int, int]] | None = None,
) -> dict[str, tuple[int, int]]:
    """出生=定籍点（D18）：每人落本人片区锚点邻域可走格（曼哈顿 ≤6 内确定性
    挑位，同环内 (x,y) 字典序；锚点被占向外退）。

    修前：全员从 SPAWN_BASE（药铺）环形散布 → 开局全员同向走回五片区=挤巷
    大迁徙。定籍出生后人就在村里，无迁徙。占位冲突按 roster 序先到先得
    （确定性，C5）。
    occupied（2026-10-12 换图补）: 先占格（主角 SPAWN 等）——村民不得同格。
    """
    from sim.npc.sim_exec import home_base_of

    taken: set[tuple[int, int]] = set(occupied.values()) if occupied else set()
    out: dict[str, tuple[int, int]] = {}
    for nid in roster:
        home = home_base_of(nid)
        hx, hy = home
        placed: tuple[int, int] | None = None
        for r in range(7):
            ring: list[tuple[int, int]] = []
            for x in range(hx - r, hx + r + 1):
                for y in (hy - r, hy + r):
                    ring.append((x, y))
            for y in range(hy - r + 1, hy + r):
                ring.extend([(hx - r, y), (hx + r, y)])
            for pos in sorted(set(ring)):
                x, y = pos
                if pos in taken:
                    continue
                if not (0 <= x < tile_map.width and 0 <= y < tile_map.height):
                    continue
                if not tile_map.is_walkable(x, y):
                    continue
                placed = pos
                break
            if placed is not None:
                break
        if placed is None:
            msg = f"定籍出生无位: {nid} @ {home}"
            raise ValueError(msg)
        taken.add(placed)
        out[nid] = placed
    return out


def spawn_positions(
    tile_map: TileMap, *, base: tuple[int, int], count: int
) -> list[tuple[int, int]]:
    """确定性散布 count 个出生位：以 base 为心，按曼哈顿环半径从内向外扫描，
    同环内按 (x,y) 字典序；跳过 base 与已占位；不可走格跳过。"""
    bx, by = base
    taken: set[tuple[int, int]] = {base}
    out: list[tuple[int, int]] = []
    for r in range(1, 64):  # 63 环理论容量 ~8064 格；96 图实测上界 6760（D16 后仍充裕）
        ring: list[tuple[int, int]] = []
        for x in range(bx - r, bx + r + 1):
            for y in (by - r, by + r):
                ring.append((x, y))
        for y in range(by - r + 1, by + r):
            ring.extend([(bx - r, y), (bx + r, y)])
        for pos in sorted(set(ring)):
            if len(out) >= count:
                return out
            if pos in taken:
                continue
            x, y = pos
            if not (0 <= x < tile_map.width and 0 <= y < tile_map.height):
                continue
            if not tile_map.is_walkable(x, y):
                continue
            taken.add(pos)
            out.append(pos)
        if len(out) >= count:
            break
    if len(out) < count:
        msg = f"散布空间不足: 需 {count} 得 {len(out)}"
        raise ValueError(msg)
    return out


# ---------------------------------------------------------------------------
# 幂等播种（lifespan 首启调用）
# ---------------------------------------------------------------------------


def _profile_row(p: NpcProfileData) -> dict[str, object]:
    """NpcProfileData → npc_profiles 行（分支 main；列口径同 M2 测试夹具）。"""
    from sim.npc.roles import ROLES

    role = ROLES.get(p.npc_id)
    return {
        "id": p.npc_id,
        "branch_id": "main",
        "name": role[0] if role else p.name,
        "species": "human",
        "gender": "unknown",
        "age": role[1] if role else 30 + (_hash_u32(p.npc_id, "age") % 40),
        "occupation": role[2] if role else p.occupation,
        "identity_anchor": f"我是{p.name}，{p.occupation}。",
        "ocean_openness": int(p.ocean[0]),
        "ocean_conscientiousness": int(p.ocean[1]),
        "ocean_extraversion": int(p.ocean[2]),
        "ocean_agreeableness": int(p.ocean[3]),
        "ocean_neuroticism": int(p.ocean[4]),
        "pad_pleasure": p.pad[0],
        "pad_arousal": p.pad[1],
        "pad_dominance": p.pad[2],
        "emotion_updated_tick": 0,
        "needs": json.dumps(
            [{"name": n.name, "value": n.value, "weight": n.weight} for n in p.needs]
        ),
        "skills": json.dumps({}),
        "goals": json.dumps({}),
        "inventory": json.dumps([]),
        "knowledge_boundary": json.dumps({"class_register": p.class_register}),
        "lod": p.lod,
        "created_at_tick": 0,
        "updated_at_tick": 0,
    }


async def seed_villagers(session_factory) -> int:
    """名册落库（幂等）：已存在的 id 跳过，只插缺行；返回新增行数。

    profile 行是**内容底座**（创世数据，非运行时状态变化）——C4 写路径约束的
    是世界状态变更；此处同 M2 测试夹具口径直插 session。判定按 id 存在性
    （部分残留补齐；内容不可变，改名单要显式重置库）。
    """
    from sqlalchemy import select

    from sim.core.persistence.models import NpcProfile

    roster = build_roster()
    async with session_factory() as session:
        existing_rows = (await session.execute(select(NpcProfile.id))).scalars().all()
        existing = set(existing_rows)
        missing = [p for p in roster if p.npc_id not in existing]
        for p in missing:
            session.add(NpcProfile(**_profile_row(p)))
        await session.commit()
        return len(missing)
