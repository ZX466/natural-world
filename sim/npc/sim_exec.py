"""sim.npc.sim_exec — NPC 决策的实况执行面（批次 B）。

NpcRuntime.tick 产出的 NPC_ACT 批次 → 可观察后果（C4 唯一写路径）：
每个动作都有「去做事的地方」的位移面——eat 去食摊、rest 回家、work 去农田、
request_chat 走向交谈对象、wander/move 哈希散布闲逛。到站后再决策原地停留
（goal == pos → 退化为闲逛，镇子不停摆）。

确定性账（C5）：目标解析是 (action, npc_id, tick, state) 的纯函数、无 RNG
状态流——重放时执行面不参与（WorldState 只由事件 fold），同事件序列逐位
一致不受执行面影响；执行面只在实况侧把决策翻译成事件。
效用矩阵不动（M2 定标内容常量、有测试钉）：实测分布 rest/chat/eat 占优、
wander 零票——本执行面让**全部动作族**都产生走动，镇子活性不依赖 wander 胜出。
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import replace

from sim.core.events import WorldEvent, move_event, npc_chat_event, npc_monologue_event
from sim.core.world import WorldState
from sim.world.pathfinding import Pathfinder

# ---------------------------------------------------------------------------
# 意愿独白（批次 D2：NPC 开口）——节流常数
# ---------------------------------------------------------------------------

#: 同 NPC 两次 bubble 独白的最小间隔（tick；300 = 5 游戏分）。batch B 实测
#: 每 10 tick 一决策，50 人不节流每分钟可产 3000 条独白帧（刷屏+烧 WS）。
_MONOLOGUE_COOLDOWN_TICKS = 300

#: D10 开口稀疏化：冷却按 NPC 散布 [2400, 9600) tick（40~160 游戏分）。
#: D2 的 300 tick/人 × 50 人 = 全镇同一节拍齐射 50 帧同文（「心之声凌乱」
#: 根因）——间隔固定时齐射节拍固定，散布把开口时点岔开（确定性哈希，C5）。
_MONOLOGUE_COOLDOWN_MIN_TICKS = 2400
_MONOLOGUE_COOLDOWN_SPAN_TICKS = 7200

#: D10 每决策节拍全镇 bubble 出镇上限（保险丝：冷却散布仍有概率撞拍；
#: 50 人同拍开口最多放行 2 条，其余静默丢——表现面节流，非世界真相）。
_MONOLOGUE_QUOTA_PER_BEAT = 2

#: E1 聊天冷却（D10 同手法：按 NPC 散布防齐射）。[1800, 7200) tick =
#: 30~120 游戏分——同 NPC 两次面对面聊天最小间隔。
_CHAT_COOLDOWN_MIN_TICKS = 1800
_CHAT_COOLDOWN_SPAN_TICKS = 5400
#: 到站开口半径（曼哈顿；review I1：开口对象=此邻域内最近者）。
_CHAT_ARRIVAL_RADIUS = 2


def _chat_cooldown_ticks(npc_id: str) -> int:
    """npc_id → 聊天冷却时长（tick）：[MIN, MIN+SPAN) 均匀散布（C5 哈希）。"""
    span = _hash_u32("chat-cooldown", npc_id) % _CHAT_COOLDOWN_SPAN_TICKS
    return _CHAT_COOLDOWN_MIN_TICKS + span


#: E2 retell 冷却：[3600, 14400) tick = 60~240 游戏分（学舌比聊天更稀）。
_RETELL_COOLDOWN_MIN_TICKS = 3600
_RETELL_COOLDOWN_SPAN_TICKS = 10800


def retell_template(speaker_name: str, content: str) -> str:
    """转述模板（外在可观察面：路人听见 A 向 B 学舌）。"""
    return f"听{speaker_name}说，{content}"


#: E3 谋生：work 到站计酬（一次 5 文；冷却 [3600, 10800) tick = 60~180 游戏分
#: ——防同拍连刷；工钱是戏内事实，数额可出站）。
_WAGE_AMOUNT = 5
_WAGE_COOLDOWN_MIN_TICKS = 3600
_WAGE_COOLDOWN_SPAN_TICKS = 7200


def _wage_cooldown_ticks(npc_id: str) -> int:
    """npc_id → 计酬冷却（tick）：[MIN, MIN+SPAN) 均匀散布（C5 哈希）。"""
    span = _hash_u32("wage-cooldown", npc_id) % _WAGE_COOLDOWN_SPAN_TICKS
    return _WAGE_COOLDOWN_MIN_TICKS + span


def _cooldown_ticks(npc_id: str) -> int:
    """npc_id → 冷却时长（tick）：[MIN, MIN+SPAN) 均匀散布（sha256 截断，C5）。"""
    digest = hashlib.sha256(f"monologue-cooldown:{npc_id}".encode()).digest()
    span = int.from_bytes(digest[0:4], "big") % _MONOLOGUE_COOLDOWN_SPAN_TICKS
    return _MONOLOGUE_COOLDOWN_MIN_TICKS + span

# ---------------------------------------------------------------------------
# 动作目的地（批次 B 内容面；坐标须在 linhe-town.json 可走格上）
# ---------------------------------------------------------------------------

#: eat → 食摊锚点（「做事的地方」是**邻域**而非一格——D12 散点化，
#: 50 人目的地 distinct 23→40+，最热点 13→≤6 人，聚团定量钉锁死）
EAT_SITE: tuple[int, int] = (10, 15)
#: rest → 两宅门前锚点（按 npc_id 哈希选一家；「家」概念随 M4 日程域细化）
REST_SITES: tuple[tuple[int, int], ...] = ((34, 13), (34, 39))
#: work → 农田锚点
WORK_SITE: tuple[int, int] = (13, 35)

#: 站点散点半径（曼哈顿距离；散点生成在锚点 ±R 内挑可走格）。
#: 4 = 5×9 邻域（约 30+ 可走格），50 人同拍打散后最热点 ≤6 人。
_SITE_SCATTER_RADIUS = 4

# ---------------------------------------------------------------------------
# D16 定籍领地（「每个 npc 在固定的区域呆着」——用户验收口径）
# ---------------------------------------------------------------------------

#: 五片区锚点（build_town.py 96×96 布局同源，锚点自身必须可走）：
#: 中心镇集 / 西村 / 东村 / 南村 / 北村——每区一宅（rest=自家门前）。
HOME_BASES: tuple[tuple[int, int], ...] = (
    (28, 42),   # 中心镇集（药铺/食摊一带）
    (14, 68),   # 西村（西村宅前）
    (82, 38),   # 东村（东村宅前，水塘上方）
    (46, 86),   # 南村（南村宅前，农田带）
    (78, 75),   # 北村（北村宅前，水塘下方）
)

#: 领地内散步半径（曼哈顿）：闲逛只在本人片区 ±R 内——「一部分区域乱走」
#: 的根因收口（D14 的 wander_near(entity.pos) 锚定当前位置，随机游走逐拍
#: 累积仍会漂出街区；定籍后目标恒落本片区，漂移不再累积）。
_TERRITORY_RADIUS = 10


def home_base_of(npc_id: str) -> tuple[int, int]:
    """npc_id → 定籍片区锚点（纯函数：均衡轮转 + 区内确定性，C5 同输入同输出）。

    D18 均衡制：先按 npc_id 序**轮转均分**到五区（每区人数相等——首版纯哈希
    实测 14/14/10/6/6，中心区仍挤），区序由 sha256 决定打散名字与区的直觉
    关联（C5：同 id 恒同区）。定籍是**表现面确定性**（不出事件、不进世界态），
    与 D12 散点、D10 冷却同族。
    """
    idx = _TERRITORY_ORDER.get(npc_id)
    if idx is None:
        # 名册外 id（测试/未来扩员）：退回哈希分布（均衡钉只管 50 人正册）
        digest = _hash_u32("home-base", npc_id)
        return HOME_BASES[digest % len(HOME_BASES)]
    return HOME_BASES[idx]


#: D18 均衡定籍表：50 人正册 → 区序（每区 10 人；区序=sha256(npc_id) 洗牌后的
#: 确定性轮转——首次构建时排序生成，之后硬编为常量（重跑逐位一致）。
_DISTRICT_SIZES = 10  # 每区人数（50 人 ÷ 5 区）

_D4 = hashlib.sha256


def _home_digest(nid: str) -> int:
    return int.from_bytes(_D4(f"home-base:{nid}".encode()).digest()[:4], "big")


_sorted_ids = sorted(
    (_home_digest(f"villager_{i:02d}"), f"villager_{i:02d}") for i in range(1, 51)
)
_TERRITORY_ORDER = {
    nid: (rank // _DISTRICT_SIZES) % len(HOME_BASES)
    for rank, (_digest, nid) in enumerate(_sorted_ids)
}


#: 片区 → 本区站点（eat/rest/work 全部落本人片区——不再全镇挤唯一摊）。
#: 布局与 build_town.py 96×96 同源：rest=本区宅门前；eat=本区路旁食摊；
#: work=南村农田带（农活集中在南村，其余区走田埂路去——劳作是跨街的，
#: 去程也是「在片区间活动」的戏内图景）。
_TERRITORY_EAT: dict[tuple[int, int], tuple[int, int]] = {
    (28, 42): (30, 46),   # 中心镇集：食摊
    (14, 68): (20, 62),   # 西村：十字路西南口
    (82, 38): (70, 38),   # 东村：村口路旁（D18：本区吃饭，不再走去镇集）
    (46, 86): (40, 80),   # 南村：农田带路旁
    (78, 75): (70, 72),   # 北村：村口（D18：本区吃饭，不再走去镇集）
}
_TERRITORY_REST: dict[tuple[int, int], tuple[int, int]] = {
    (28, 42): (28, 41),   # 中心区 → 中心住宅门前
    (14, 68): (14, 67),   # 西村 → 西村宅门前
    (82, 38): (82, 37),   # 东村 → 东村宅门前
    (46, 86): (48, 85),   # 南村 → 南村宅门前
    (78, 75): (78, 73),   # 北村 → 北村宅门前
}
_TERRITORY_WORK: dict[tuple[int, int], tuple[int, int]] = {
    (28, 42): (26, 76),   # 中心区 → 农田北缘
    (14, 68): (26, 76),   # 西村 → 农田北缘
    (82, 38): (26, 76),   # 东村 → 农田北缘
    (46, 86): (26, 80),   # 南村 → 农田心（就近）
    (78, 75): (26, 76),   # 北村 → 农田北缘
}

#: D14：动作 → 呈现用 anim 词（前端姿势行选择；villager 素材行序
#: R0-R3=四向走环 / R4-7=劳作姿势——work/eat/rest/chat 各有站姿差异）。
#: wander/move 是行走态（前端按位移自动播走环，不依赖本字段）。
_ANIM_OF_ACTION: dict[str, str] = {
    "work": "work",
    "eat": "eat",
    "rest": "rest",
    "request_chat": "chat",
    "wander": "walk",
    "move": "walk",
}


def anim_of_action(action: str) -> str:
    """动作 → anim 词（未知动作退化为 walk——fail-soft 不崩前端）。"""
    return _ANIM_OF_ACTION.get(action, "walk")


def _scatter_near(
    site: tuple[int, int],
    npc_id: str,
    pathfinder: Pathfinder,
    *,
    seed: int,
) -> tuple[int, int]:
    """站点邻域确定性散点：锚点曼哈顿 ≤R 的可走格里按哈希挑一个。

    **tick 无关**（每人固定私位）：D3 到站判定用同参比较——出发决策与
    到达判定的 tick 相差几十上百 tick，若散点随 tick 漂移则 `pos == goal`
    永假 → 生理回写永不到账。tick 无关散点 = 常客有固定摊位（更戏内），
    且到站判定闭合。候选按 (dx,dy) 字典序固定序遍历 → 哈希取模（C5）；
    候选集恒非空（锚点自身可走——build_town 站点坐标约束），锚点兜底。
    """
    sx, sy = site
    digest = _hash_u32("site-scatter", npc_id, sx, sy, seed)
    candidates: list[tuple[int, int]] = []
    for dy in range(-_SITE_SCATTER_RADIUS, _SITE_SCATTER_RADIUS + 1):
        for dx in range(-_SITE_SCATTER_RADIUS, _SITE_SCATTER_RADIUS + 1):
            if abs(dx) + abs(dy) > _SITE_SCATTER_RADIUS:
                continue
            x, y = sx + dx, sy + dy
            if 0 <= x < pathfinder.tile_map.width and 0 <= y < pathfinder.tile_map.height \
                    and pathfinder.tile_map.is_walkable(x, y):
                candidates.append((x, y))
    if not candidates:
        return site  # 锚点兜底（理论不可达：站点坐标自身必可走）
    return candidates[digest % len(candidates)]


def _hash_u32(*parts: object) -> int:
    digest = hashlib.sha256(":".join(str(p) for p in parts).encode()).digest()
    return int.from_bytes(digest[0:4], "big")


def wander_goal(seed: int, tick: int, npc_id: str, w: int, h: int) -> tuple[int, int]:
    """确定性闲逛目标：(seed, tick, npc_id) 哈希散布进 [0,w)×[0,h)。

    同输入恒同输出（无随机流）；不同 npc_id 散布开（sha256 雪崩）。
    D14 后 wander 位移面改走 `wander_near`（邻域化）；本函数保留给
    wander/move 的兜底调用点（D14 起 plan_npc_move 不再退化闲逛，
    只剩测试/兼容消费）。
    """
    digest = _hash_u32(seed, tick, npc_id)
    return (digest % w, (digest // w) % h)


#: D14 闲逛半径（曼哈顿）：闲逛不再横穿小镇——从「家」出门走走就回。
_WANDER_RADIUS = 6


def wander_near(
    home: tuple[int, int],
    npc_id: str,
    pathfinder: Pathfinder,
    *,
    seed: int,
    tick: int,
) -> tuple[int, int] | None:
    """D14 邻域闲逛目标：home 曼哈顿 ≤R 的可走格（排除原格），哈希挑一个。

    候选按 (dx,dy) 字典序固定序 → 哈希取模（C5）。候选空（围死）→ None。
    """
    hx, hy = home
    digest = _hash_u32("wander-near", npc_id, seed, tick)
    candidates: list[tuple[int, int]] = []
    for dy in range(-_WANDER_RADIUS, _WANDER_RADIUS + 1):
        for dx in range(-_WANDER_RADIUS, _WANDER_RADIUS + 1):
            if abs(dx) + abs(dy) > _WANDER_RADIUS or (dx == 0 and dy == 0):
                continue
            x, y = hx + dx, hy + dy
            if 0 <= x < pathfinder.tile_map.width and 0 <= y < pathfinder.tile_map.height \
                    and pathfinder.tile_map.is_walkable(x, y):
                candidates.append((x, y))
    if not candidates:
        return None
    return candidates[digest % len(candidates)]


def _site_anchor_of(action: str, npc_id: str) -> tuple[int, int] | None:
    """动作 → 站点锚点（D16 定籍制：eat/rest/work 全部落**本人片区**站点；
    None=无站点）。片区锚点表缺项时退回全镇站点（fail-safe 不炸）。
    """
    home = home_base_of(npc_id)
    if action == "eat":
        return _TERRITORY_EAT.get(home, EAT_SITE)
    if action == "rest":
        return _TERRITORY_REST.get(home, REST_SITES[0])
    if action == "work":
        return _TERRITORY_WORK.get(home, WORK_SITE)
    return None


def _chat_target_of(state: WorldState, npc_id: str, *, tick: int) -> str | None:
    """聊天目标选择（D18 本区化）：同片区人优先，同区无人 → 跨区兜底。

    修前从全镇 50 人哈希挑 1——多人同拍抽中同一目标即全村互吸（聚团主源）。
    同区候选按 id 序 + 哈希挑（C5）；同区仅自己 → None（无目标）。
    """
    others = sorted(eid for eid in state.entities if eid != npc_id)
    if not others:
        return None
    home = home_base_of(npc_id)
    same = [eid for eid in others if home_base_of(eid) == home]
    if same:
        return same[_hash_u32("chat-target", npc_id, tick) % len(same)]
    return others[_hash_u32("chat-target", npc_id, tick) % len(others)]


def _nearest_other(entity: object, state: WorldState) -> str | None:
    """到站邻域内最近的其他人（review I1：开口对象与寻路目的地脱钩——
    「走到了谁面前就跟谁说」）。曼哈顿 ≤2 内按距离取最近；并列按 id 序
    （C5 确定性）；无人在邻域 → None（走了全程没人可说，静默是常态路径）。
    """
    nearest: str | None = None
    nearest_dist = _CHAT_ARRIVAL_RADIUS + 1
    eid_self = getattr(entity, "entity_id", "")
    for eid, other in sorted(state.entities.items()):
        if eid == eid_self:
            continue
        dist = abs(other.pos[0] - entity.pos[0]) + abs(other.pos[1] - entity.pos[1])
        if dist <= _CHAT_ARRIVAL_RADIUS and dist < nearest_dist:
            nearest = eid
            nearest_dist = dist
    return nearest


def _resolve_goal(
    state: WorldState,
    npc_id: str,
    action: str,
    *,
    seed: int,
    tick: int,
    w: int,
    h: int,
    pathfinder: Pathfinder,
) -> tuple[int, int] | None:
    """动作 → 目的地（纯函数）；None = 该动作无位移面。

    D12：eat/rest/work 落站点**邻域散点**（不再全镇挤一格）；
    D16：站点=本人片区站点（定籍制）；闲逛锚定**本片区**（不再锚定当前
    位置——随机游走漂移收口）；request_chat 仍跨片区（社交不缩水）。
    """
    if action in ("wander", "move"):
        # D16：闲逛锚定本人片区（人在片区外先走回家再溜达——归巢语义）。
        return wander_near(home_base_of(npc_id), npc_id, pathfinder, seed=seed, tick=tick)
    if action in ("eat", "rest", "work"):
        anchor = _site_anchor_of(action, npc_id)
        assert anchor is not None  # 三动作恒有锚点
        return _scatter_near(anchor, npc_id, pathfinder, seed=seed)
    if action == "request_chat":
        target = _chat_target_of(state, npc_id, tick=tick)
        if target is None:
            return wander_near(
                home_base_of(npc_id), npc_id, pathfinder, seed=seed, tick=tick
            )
        return _scatter_near(
            state.entities[target].pos, npc_id, pathfinder, seed=seed
        )
    return None


#: 路径扰动半径（每段尝试的垂直偏移距离，格）。
_JITTER_OFFSET = 1
#: 扰动最小路径长度（≤2 格不扰——端点约束高、收益低）。
_JITTER_MIN_LEN = 3


def _jitter_path(
    path: tuple[tuple[int, int], ...],
    npc_id: str,
    *,
    tick: int,
    pathfinder: Pathfinder,
) -> tuple[tuple[int, int], ...]:
    """确定性路径扰动（D20 治「固定轨迹」列车化）：同 OD 的 A* 最短路人人
    同一条街；本函数在中间格按 (npc_id, tick) 哈希做**局部横向绕行**——
    每隔 _JITTER_STEP 格尝试向垂直方向偏移一格再折回（若两侧都可走则哈希
    挑一侧，一侧可走则绕该侧，都不可走保持原格）。

    C5：哈希纯函数、无随机；起终点不动；长度上界 = 基线 ×1.6 +1（钉）。
    扰动只发生在**可走格之间**——寻路面不新增不可达。
    """
    if len(path) < _JITTER_MIN_LEN:
        return path
    digest = _hash_u32("path-jitter", npc_id, tick)
    step = 3 + (digest % 2)  # 每 3-4 格一个扰动点（步长哈希微变，路线不齐步）
    out: list[tuple[int, int]] = [path[0]]
    i = 1
    while i < len(path) - 1:
        x, y = path[i]
        # 扰动判定：段首格才尝试（步长节奏）；基线相邻格方向决定垂直向
        if (i - 1) % step == 0 and i + 1 < len(path) - 1:
            px, py = path[i - 1]
            dx, dy = x - px, y - py
            # 垂直方向两个候选
            cands = [(x - dy, y - dx), (x + dy, y + dx)]
            walkable = [c for c in cands if pathfinder.tile_map.is_walkable(*c)]
            if walkable:
                pick = walkable[(digest >> 8) % len(walkable)]
                # 绕行：当前格 → 偏移格 → 回到当前格（两格换一格的三拍）
                out.append(pick)
        out.append((x, y))
        i += 1
    out.append(path[-1])
    # 长度上界护栏（理论 1.5x 内，防御性 clamp 到钉值）
    base_len = len(path)
    if len(out) > int(base_len * 1.6) + 1:
        return path
    return tuple(out)


def plan_npc_move(
    state: WorldState,
    npc_id: str,
    action: str,
    pathfinder: Pathfinder,
    *,
    seed: int,
    tick: int,
) -> WorldEvent | None:
    """单个动作 → move_event（去「做事的地方」）；不该动/动不了 → None。

    D14 移动纪律（「NPC 随便移动」根治）：
    - 未知实体 / 在途（剩余 path 未耗尽）→ None（防抖）；
    - **到站停留**：eat/rest/work/request_chat 已在目的地 → None——人在
      饭摊就站着吃（需求回写驱动停留时长），不再「到站即被赶去全图闲逛」
      （D2 起「goal==pos → 退化为闲逛」是全镇横穿的主犯）；
    - 不可达 → None（原地待着，**不再**退化为全图闲逛——错上加错）；
    - wander/move 无站点语义 → 邻域闲逛目标（wander_near）。
    D16 定籍领地：eat/rest/wander 全部锚定本人片区（home_base_of）——
    「一部分区域乱走」的根因收口；request_chat 仍跨片区（社交不缩水）。
    返回的 move_event **不入流**（无 enqueue）——调用方决定入流时机与 tick。
    """
    entity = state.entities.get(npc_id)
    if entity is None or entity.path:
        return None
    w, h = pathfinder.tile_map.width, pathfinder.tile_map.height
    start = entity.pos
    if action in ("eat", "rest", "work", "request_chat"):
        goal = _resolve_goal(
            state, npc_id, action, seed=seed, tick=tick, w=w, h=h, pathfinder=pathfinder
        )
        if goal is None:
            return None
        # D14 到站判定（放宽到散点邻域）：人在自己私位**或锚点邻域内**
        # 都算到站——「他在饭摊边上」就该站着吃，而不是被差遣到隔壁格
        # （修前 goal==pos 判定：散点私位 ≠ 锚点 → 人在锚点仍被赶走）。
        if action != "request_chat":
            from sim.npc.sim_exec import _site_anchor_of

            anchor = _site_anchor_of(action, npc_id)
            if anchor is not None:
                dist = abs(start[0] - anchor[0]) + abs(start[1] - anchor[1])
                if dist <= _SITE_SCATTER_RADIUS:
                    return None  # 到站停留（停留由需求回写驱动）
        if goal == start:
            return None
        try:
            path = pathfinder.find(start, goal)
        except ValueError:
            return None  # D14：不可达原地待着（不再退化全图闲逛）
        path = _jitter_path(path, npc_id, tick=tick, pathfinder=pathfinder)  # D20 轨迹扰动
        return move_event(
            tick=0,  # tick 由调用方改写（issue 时点）；工厂校验 path 完整性
            actor_id=npc_id,
            start=start,
            goal=path[-1],
            path=path,
        )
    # wander/move：D16 定籍闲逛——目标锚定本人片区（人在片区外=归巢途中）
    goal = wander_near(home_base_of(npc_id), npc_id, pathfinder, seed=seed, tick=tick)
    if goal is None or goal == start:
        return None
    try:
        path = pathfinder.find(start, goal)
    except ValueError:
        return None
    path = _jitter_path(path, npc_id, tick=tick, pathfinder=pathfinder)  # D20 轨迹扰动
    return move_event(
        tick=0,
        actor_id=npc_id,
        start=start,
        goal=path[-1],
        path=path,
    )


def npc_events_for_tick(
    runtime: object,
    state: WorldState,
    tick: int,
    pathfinder: Pathfinder,
    *,
    seed: int,
    monologue_last: dict[str, int] | None = None,
    monologue_quota: dict[int, int] | None = None,
    chat_last: dict[str, int] | None = None,
    display_name_of: Mapping[str, str] | None = None,
    chat_ledger: object | None = None,
    retell_last: dict[str, int] | None = None,
    wage_last: dict[str, int] | None = None,
    coin_ledger: object | None = None,
) -> list[WorldEvent]:
    """一个决策节拍的事件批次：NpcRuntime.tick → NPC_ACT 批次 + MOVE 交错。

    每个活跃 NPC 恰一条 NPC_ACT（决策记录）；移动类决策紧跟同 NPC 的
    move_event（日志可读序：ACT → MOVE）。runtime.tick 返回的意愿独白
    （NPC_MONOLOGUE，M4-B3 通路）按 `monologue_last` 节流后原样并入批次
    （batch D2：NPC 开口——D10 起冷却按 NPC 散布 [2400,9600) tick，见
    `_cooldown_ticks`；另有每节拍全镇出镇上限 `_MONOLOGUE_QUOTA_PER_BEAT`）。
    `monologue_last`：{npc_id: 上次发表 tick}，调用方持有（跨拍记忆态，
    确定性不受影响——节流只发生在实况侧，不进重放面）。
    `monologue_quota`：{tick: 本拍已出镇条数}（D10 撞拍保险丝账本；调用方
    持有，与 last 同口径的表现面记忆态。None = 不设配额，兼容既有测试）。

    runtime 参数是 NpcRuntime（object 注解避免内核↔npc 域反向依赖——
    实际调用点在 main.py 装配层）。
    """
    acts = runtime.tick(tick)  # type: ignore[attr-defined]
    events: list[WorldEvent] = []
    for event in acts:
        if event.event_type.value == "npc.monologue":
            npc_id = str(event.payload.get("npc_id", ""))
            if monologue_last is not None:
                cooldown = _cooldown_ticks(npc_id)
                last = monologue_last.get(npc_id, -(cooldown + 1))
                if tick - last < cooldown:
                    continue  # 冷却期内：静默丢弃（表现面节流，非世界真相）
                monologue_last[npc_id] = tick
            if monologue_quota is not None:
                used = monologue_quota.get(tick, 0)
                if used >= _MONOLOGUE_QUOTA_PER_BEAT:
                    continue  # 配额用尽：静默丢弃（冷却已记，不会连拍重试）
                monologue_quota[tick] = used + 1
            # 意愿独白的呈现面转换：runtime 产 thought（M4-B3 硬编码），但村民
            # 的意愿挣扎是**外在可观察面**（路人可见的嘟囔）——投影为 bubble
            # （广播面）。thought 私密面归 chenmo L2（driver 侧不经此路）。
            # 事件入流前替换 payload：内容逐位不变，仅 form 呈现档（见 M5-K8
            # 投递面契约：bubble=广播）。frozen 事件用 model_copy。
            if event.payload.get("form") == "thought":
                event = event.model_copy(
                    update={"payload": {**event.payload, "form": "bubble"}}
                )
            events.append(event)
            continue
        if event.event_type.value != "npc.act":
            continue
        events.append(event)
        npc_id = str(event.payload.get("npc_id", ""))
        action = str(event.payload.get("action", ""))
        # 批次 D3：生理闭环——动作**到站**才回写需求（吃了才算吃）。
        # D14 到站口径与 plan_npc_move 同源：人在站点锚点邻域（≤散点半径）
        # 即视为到站——散点私位与锚点的偏差不再让回写漏账。
        entity = state.entities.get(npc_id)
        if entity is not None and not entity.path and action in ("eat", "rest", "work"):
            anchor = _site_anchor_of(action, npc_id)
            profiles = getattr(runtime, "profiles", None)
            if anchor is not None and profiles is not None and npc_id in profiles:
                dist = abs(entity.pos[0] - anchor[0]) + abs(entity.pos[1] - anchor[1])
                if dist <= _SITE_SCATTER_RADIUS:
                    from sim.npc.needs import apply_remedy

                    p = profiles[npc_id]
                    profiles[npc_id] = replace(p, needs=apply_remedy(p.needs, action))
            # E3 谋生：work 到站计酬（到站才发——没到田里没有工钱，D3 口径）。
            if (
                action == "work"
                and anchor is not None
                and entity is not None
                and not entity.path
                and wage_last is not None
                and coin_ledger is not None
            ):
                dist = abs(entity.pos[0] - anchor[0]) + abs(entity.pos[1] - anchor[1])
                if dist <= _SITE_SCATTER_RADIUS:
                    _wage_never = -(_WAGE_COOLDOWN_MIN_TICKS + _WAGE_COOLDOWN_SPAN_TICKS)
                    last_w = wage_last.get(npc_id, _wage_never)
                    if tick - last_w >= _wage_cooldown_ticks(npc_id):
                        wage_last[npc_id] = tick
                        from sim.core.events import coin_grant_event
                        from sim.world.economy import CoinLedger

                        assert isinstance(coin_ledger, CoinLedger)
                        coin_ledger.apply_grant(npc_id, _WAGE_AMOUNT, tick=tick)
                        events.append(
                            coin_grant_event(
                                tick=tick, owner_id=npc_id, delta=_WAGE_AMOUNT, note="wage:work"
                            )
                        )
        # 批次 E1：request_chat 到站开口。**开口对象 = 到站邻域内最近的其他人**
        # （review I1 修复：决策 tick 与开口 tick 相差几十 tick,哈希含 tick 的
        # _chat_target_of 重算会选出另一个目标——走了全程却对不上人。到站邻域
        # 最近者 = 「走到了谁面前就跟谁说」,与寻路目的地脱钩但戏内自洽）。
        if (
            action == "request_chat"
            and entity is not None
            and not entity.path
            and chat_last is not None
        ):
            target_id = _nearest_other(entity, state)
            if target_id is not None:
                last = chat_last.get(
                    npc_id, -(_CHAT_COOLDOWN_MIN_TICKS + _CHAT_COOLDOWN_SPAN_TICKS)
                )
                if tick - last >= _chat_cooldown_ticks(npc_id):
                    chat_last[npc_id] = tick
                    from sim.agent.dialogue import template_line

                    listener = (display_name_of or {}).get(target_id, target_id)
                    line = template_line(npc_id, listener, tick)
                    events.append(
                        npc_chat_event(
                            tick=tick, npc_id=npc_id, to_id=target_id, line=line
                        )
                    )
                    # E2：聊天落账本——好感漂移 + 双方记忆（进程内 runtime 态）。
                    if chat_ledger is not None:
                        from sim.npc.chat_ledger import ChatLedger

                        assert isinstance(chat_ledger, ChatLedger)
                        chat_ledger.adjust(npc_id, target_id, kind="chat")
                        # E2 retell：开口同拍，学舌**开口前**已记住的旧闻
                        # （本拍的话对方刚听过——复读不传播新信息；流言=
                        # 传播先前获得的内容，故先取旧记忆再落新记忆）。
                        _prior_mems = chat_ledger.memories_of(npc_id)
                        chat_ledger.remember(npc_id, line, tick=tick)
                        chat_ledger.remember(target_id, line, tick=tick)
                        if retell_last is not None and _prior_mems:
                            cool = _RETELL_COOLDOWN_MIN_TICKS + (
                                _hash_u32("retell-cooldown", npc_id)
                                % _RETELL_COOLDOWN_SPAN_TICKS
                            )
                            last_r = retell_last.get(npc_id, -(cool + 1))
                            if tick - last_r >= cool:
                                retell_last[npc_id] = tick
                                _tick_src, _content = _prior_mems[-1]
                                _speaker = (display_name_of or {}).get(npc_id, npc_id)
                                _line = retell_template(_speaker, _content)
                                events.append(
                                    npc_monologue_event(
                                        tick=tick,
                                        npc_id=npc_id,
                                        form="bubble",
                                        content=_line,
                                    )
                                )
                                chat_ledger.adjust(npc_id, target_id, kind="retell")
        mv = plan_npc_move(
            state,
            npc_id,
            action,
            pathfinder,
            seed=seed,
            tick=tick,
        )
        if mv is not None:
            events.append(_retick(mv, tick))
    return events


def _retick(event: WorldEvent, tick: int) -> WorldEvent:
    """move_event 以 tick=0 占位构造后改写为本节拍 tick（frozen → model_copy）。"""
    return event.model_copy(update={"tick": tick})
