"""terrain_class.py — 桃花源整图的单一地形分类真相源。

## 为什么需要这一层

`god-packs/taohuayuan-online` 是**整幅绘画按 1:1 切片**的贴图：
`Bottom Ground` 用 14000 个不同 gid 覆盖 14000 格（每格一个不同图集瓦片），
`tilesets[0].tiles` 为空——**没有任何瓦片语义**（无 collision 属性、无类型标记）。
源包自带的 `Collisions` 层与 `World Blocks` 逐字节相同，只画了三条贯穿建筑与
河道的直线带（820/14000 = 5.9% 可走），既不是美术对齐的碰撞，也不是可行走区域。

因此「能不能走」和「多高」必须由本项目自己从画面推导，且**只能有一个推导源**：
本模块的分类结果同时供给

  1. `linhe-town.json` 的 collision 位（sim 碰撞真相 / 寻路 / 放置门槛）
  2. `linhe-height.json` 的 h 值（等距渲染高度 + V4b 材料 h=1/2/3）
  3. `linhe-block-atlas.json` 的四档基色

三者同源是硬要求：若碰撞与高度各自独立推导，就会出现「看得见的高方块却能穿过去」
（2026-10-28 用户报告的「障碍物可以穿过」正是这个错位的表现）。

## 分类方法

整图每格 16×16 像素，而画面语义比格子还细，逐像素分类必为噪点。
分两步：

  1. **每格特征**：统计该格 256 个像素中各类占比
     - `walk`：明亮（V>=0.45）且非水非植被 —— 土路/铺地/广场
     - `canopy`：粉色（H>=285）或饱和绿（H 62..175, S>=0.28）—— 树冠
     - `water`：蓝（H 175..250, B>R）
  2. **空间平滑**：对每张特征图做 5×5 均值滤波 4 轮。画面本身是空间连贯的
     （房子成块、河道连续），逐格噪声在平滑后收敛为结构 —— 实测连通块
     从 1239 降到 5，正是这一步把「噪点」变成「地图」。
  3. **只留最大连通块**：剩下的 4 个小岛玩家永远到不了，且会把后续挖通道
     引向错误方向，故直接削掉（实测 4332 → 4278）。

## 作者真值的优先级

源包 `Spawning Blocks` 的 90 格与 `map_pack.json` 的 10 个地标锚点是作者
标注的「人站的地方」。分类器对它们可能有误判（尤其院落铺地被树冠遮挡处），
故以它们为**硬约束**：这些格必须可走，不可走则从该格挖一条最短通道接回主网。

水永远是障碍：即便真值格落在水面上也不强制可走（分类器判水的强制格实测为 0）。
"""

from __future__ import annotations

import colorsys
from collections import deque
from typing import Final

#: 每格 16x16 = 256 像素。
CELL_PIXELS: Final = 256

#: 可走判定阈值（平滑后）。
WALK_THRESHOLD: Final = 0.45
#: 树冠判定阈值（平滑后）——决定 h=3(木) 与 h=2(石) 的分界。
CANOPY_THRESHOLD: Final = 0.45
#: 水面判定阈值（平滑后）。
WATER_THRESHOLD: Final = 0.25
#: 土坎判定阈值（**逐瓦片原始值，不平滑**）。
#: 阻挡格里，瓦片本身「亮且非植被非水」占比够高者判为矮土坎（h=1，可挖出 earth）。
#: 这是 earth 的唯一来源：`place` 消耗目标格材料，而可走格全是 h=1(earth)，
#: 若土坎也判 h=2 则 earth 永不产出 → 「只挖不放」（2026-10-28 用户症状）。
#: 实测分离度：屋顶瓦片 raw_walk 0.05..0.17，田垄/土坎 0.38..1.00。
EARTH_BANK_THRESHOLD: Final = 0.45

#: 平滑窗口半径 2（5x5）与轮数 4。实测这是连通块收敛到 5 的最小配置。
SMOOTH_RADIUS: Final = 2
SMOOTH_ROUNDS: Final = 4

#: 特征像素的 HSV 门限。
_BRIGHT_VALUE: Final = 0.45
_WATER_HUE: Final = (175.0, 250.0)
_WATER_MIN_SAT: Final = 0.18
_CANOPY_PINK_HUE: Final = 285.0
_CANOPY_PINK_MIN_SAT: Final = 0.12
_CANOPY_GREEN_HUE: Final = (62.0, 175.0)
_CANOPY_GREEN_MIN_SAT: Final = 0.28

#: 材质分档（与 sim/agent/voxel_exec.py::_MATERIAL_BY_HEIGHT 对齐）。
HEIGHT_WATER: Final = 0
HEIGHT_EARTH: Final = 1
HEIGHT_STONE: Final = 2
HEIGHT_WOOD: Final = 3


def tile_features(pixels: list[list[tuple[int, int, int, int]]]) -> tuple[float, float, float]:
    """一格图集瓦片 → (walk_frac, canopy_frac, water_frac)，各为 0..1。

    `pixels` 是该瓦片的 16x16 RGBA 切片。
    """
    walk = canopy = water = 0
    for row in pixels:
        for r, g, b, _a in row:
            hue, sat, val = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
            hue *= 360
            if _WATER_HUE[0] <= hue <= _WATER_HUE[1] and b > r and sat >= _WATER_MIN_SAT:
                water += 1
            elif (hue >= _CANOPY_PINK_HUE and sat >= _CANOPY_PINK_MIN_SAT) or (
                _CANOPY_GREEN_HUE[0] <= hue <= _CANOPY_GREEN_HUE[1] and sat >= _CANOPY_GREEN_MIN_SAT
            ):
                canopy += 1
            elif val >= _BRIGHT_VALUE:
                walk += 1
    n = float(len(pixels) * len(pixels[0]))
    return walk / n, canopy / n, water / n


def smooth(field: list[float], w: int, h: int, rounds: int = SMOOTH_ROUNDS) -> list[float]:
    """5x5 均值滤波（边界按实际邻居数归一）。纯确定性，无 RNG。"""
    radius = SMOOTH_RADIUS
    cur = list(field)
    for _ in range(rounds):
        nxt = list(cur)
        for y in range(h):
            for x in range(w):
                total = 0.0
                n = 0
                for dy in range(-radius, radius + 1):
                    ny = y + dy
                    if not (0 <= ny < h):
                        continue
                    base = ny * w
                    for dx in range(-radius, radius + 1):
                        nx = x + dx
                        if 0 <= nx < w:
                            total += cur[base + nx]
                            n += 1
                nxt[y * w + x] = total / n
        cur = nxt
    return cur


def neighbours(index: int, w: int, h: int):
    """4 邻域（确定性序：左、右、上、下）。"""
    x, y = index % w, index // w
    if x > 0:
        yield index - 1
    if x < w - 1:
        yield index + 1
    if y > 0:
        yield index - w
    if y < h - 1:
        yield index + w


def largest_component(mask: list[bool], w: int, h: int) -> list[bool]:
    """保留最大 4 连通块，其余置 False。

    平滑后的可走面仍会留下若干小岛（实测 5 块：3877/229/114/74/38）。玩家只能
    在最大块内走动，小岛既到不了又会把「挖通道」引到错误方向，故先削掉。
    """
    seen = [False] * len(mask)
    best: list[int] = []
    for start in range(len(mask)):
        if seen[start] or not mask[start]:
            continue
        seen[start] = True
        queue = deque([start])
        cells: list[int] = []
        while queue:
            node = queue.popleft()
            cells.append(node)
            for nxt in neighbours(node, w, h):
                if mask[nxt] and not seen[nxt]:
                    seen[nxt] = True
                    queue.append(nxt)
        if len(cells) > len(best):
            best = cells
    keep = [False] * len(mask)
    for i in best:
        keep[i] = True
    return keep


def _is_earth_bank(
    index: int,
    ground_gids: list[int],
    tile_samples: dict[int, tuple[float, float, float]],
    walkable: list[bool],
    w: int,
    h: int,
) -> bool:
    """阻挡格是否「土坎」：瓦片本身像土面，且不是被空地围住的墙/篱笆。

    - 用**逐瓦片原始** walk 占比（不平滑）：平滑会把屋顶拉成土色，
      实测屋顶 raw 0.05..0.17、田垄/土坎 0.38..1.00，逐瓦片才分得开。
    - 4 邻可走数 ≤2：排除三面是空地的格。那种格「看着能走却进不去」是隐形墙，
      最刺眼（实测全图仅 4 格：墙头/篱笆/桥栏）。
    """
    gid = ground_gids[index]
    if gid == 0 or tile_samples[gid][0] < EARTH_BANK_THRESHOLD:
        return False
    return sum(1 for n in neighbours(index, w, h) if walkable[n]) <= 2


def _carve(mask: list[bool], water: list[bool], targets: list[int], w: int, h: int) -> int:
    """把每个不可走目标用最短 4 邻通道接回**主可走区**。返回新挖的格数。

    BFS 从目标外扩到第一个已在 mask 内的格（主区已由 largest_component 削成
    单块），再沿 prev 链回填。不穿水。
    """
    carved = 0
    for target in targets:
        if mask[target] or water[target]:
            continue
        prev: dict[int, int] = {target: -1}
        queue = deque([target])
        hit = -1
        while queue:
            node = queue.popleft()
            if mask[node] and node != target:
                hit = node
                break
            for nxt in neighbours(node, w, h):
                if nxt not in prev and not water[nxt]:
                    prev[nxt] = node
                    queue.append(nxt)
        if hit < 0:
            continue
        node = hit
        while node != -1:
            if not mask[node]:
                mask[node] = True
                carved += 1
            node = prev[node]
    return carved


def classify(
    ground_gids: list[int],
    tile_samples: dict[int, tuple[float, float, float]],
    w: int,
    h: int,
    *,
    forced_walkable: tuple[int, ...] = (),
) -> tuple[list[int], list[bool], dict[str, int]]:
    """主入口：返回 (heights, walkable, stats)。

    - `ground_gids`：行主序 w*h，0 = 空
    - `tile_samples`：gid → tile_features() 结果
    - `forced_walkable`：作者真值格索引（出生点 + 地标锚点）

    返回的 heights 与 walkable **由同一份分类产出**，二者严格一致：
    `heights[i] == HEIGHT_EARTH` **当且仅当** walkable[i]（可走 ⇔ 土面）。

    例外是「土坎」：阻挡但材质本身是土面的格，也标 HEIGHT_EARTH。它不可走
    （`place` 需要可走格，`dig` 需要阻挡格），但材料是土——这是 earth 的
    唯一来源。若把土坎也判 stone，行囊永远挖不出土，`place` 就永久缺料，
    表现即「只挖不放」（2026-10-28 用户症状）。故：

        walkable[i]  ⇒ heights[i] == HEIGHT_EARTH   （单向，渲染不得错位）
        heights[i] == HEIGHT_EARTH  ⇏ walkable[i]   （土坎：可挖不可走）
    """
    n = w * h
    walk_field = smooth([tile_samples[g][0] if g else 0.0 for g in ground_gids], w, h)
    canopy_field = smooth([tile_samples[g][1] if g else 0.0 for g in ground_gids], w, h)
    water_field = smooth([tile_samples[g][2] if g else 0.0 for g in ground_gids], w, h)

    water = [water_field[i] >= WATER_THRESHOLD for i in range(n)]
    raw = [walk_field[i] >= WALK_THRESHOLD and not water[i] for i in range(n)]
    walkable = largest_component(raw, w, h)

    carved = _carve(walkable, water, list(forced_walkable), w, h)

    heights: list[int] = []
    banks = 0
    for i in range(n):
        if walkable[i]:
            heights.append(HEIGHT_EARTH)
        elif water[i]:
            heights.append(HEIGHT_WATER)
        elif canopy_field[i] >= CANOPY_THRESHOLD:
            heights.append(HEIGHT_WOOD)
        elif _is_earth_bank(i, ground_gids, tile_samples, walkable, w, h):
            heights.append(HEIGHT_EARTH)
            banks += 1
        else:
            heights.append(HEIGHT_STONE)

    stats = {
        "walkable": sum(walkable),
        "raw_walkable": sum(raw),
        "earth_banks": banks,
        "dropped_islands": sum(raw) - sum(walkable),
        "water": sum(1 for x in heights if x == HEIGHT_WATER),
        "earth": sum(1 for x in heights if x == HEIGHT_EARTH),
        "stone": sum(1 for x in heights if x == HEIGHT_STONE),
        "wood": sum(1 for x in heights if x == HEIGHT_WOOD),
        "carved": carved,
    }
    return heights, walkable, stats
