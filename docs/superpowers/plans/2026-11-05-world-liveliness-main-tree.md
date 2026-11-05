# 世界可辨认性与自生长 — 主树实施计划（A / B1 / B4）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让临河镇「一眼能认出」（把已有 2240×1600 真美术按等距投影画出来），并让主角不再每帧闻到「奇怪气味」、LLM 拿到的地图尺寸正确。

**Architecture:** 三项互不依赖，各自独立成一组任务。A 只动 `client/src/game/render/iso-terrain.ts` 的绘制路径（新增 `paintTile` + frame 注册，保留 `paintBlock` 作兜底与编辑格），拾取/协议/后端一律不碰。B1 改感知层三处常量/阈值 + 一处叙事层跨帧抑制（落在 `main.py` 已有的 `_narrated_cache`，不改纯函数 `frame.narrated()`）。B4 只改一句 prompt 文案 + 补一条集合差测试。

**Tech Stack:** TypeScript / Phaser 3 / Vitest（前端）；Python 3 / pytest / pydantic（后端）；`uv` 管理环境，`npm` 管理前端。

**Spec:** `docs/arch/world-liveliness-design.md`（831 行，9 章；§3 = A，§4.1 = B1，§4.4 = B4，§8 = 24 条陷阱表）。执行者必须同时读 spec，本计划只写「spec 未替你决定的事」。

**不在本计划范围内：** B2（NPC 活动 + 建造四层阻断）与 B3（材料闭环 + 协议 1.15）派 **codex 树**，通过 `.orca/talking.txt` 派单。`take`/`give` 用户裁定单列（§9）。

## Global Constraints

- **协议 1.14 不动。** 本计划不产生协议变更（B3 才升 1.15，在 codex 树）。
- **`pickGround` / `pickVoxel` 逐字不动**（`iso-terrain.ts` 的拾取函数）。三次历史事故全在拾取。
- **不变量 `walkable ⇒ h == EARTH` 保持**，前后端都不碰。
- **两个同名不同值的常量不得「统一」**：`iso-terrain.ts:6` `GROUND_KEY='iso-ground-composite'` 与 `WorldScene.ts:82` `GROUND_KEY='ground-composite'`。
- **`paintGround` 的对角线遍历顺序不得改成行列序**（遮挡关系的唯一来源）。
- **`.orca/talking.txt` 永不 `git add`。**
- **门禁口径**（每次提交前按需跑子集，收尾全跑）：
  ```powershell
  uv run pytest -m "not bench"        # ~5.5 min
  uv run ruff check .; uv run ruff format --check .; uv run pyright
  cd client; npm run typecheck; npm run lint; npx prettier --check .; npx vitest run
  ```
- **管道陷阱**：`cmd 2>&1 | tail -3; echo $?` 报的是 `tail` 的退出码。一律 `cmd > log 2>&1; echo "EXIT:$?"`。
- **浏览器只用 `ms-playwright` 内打包版 chromium**，不得 `--browser chrome`。
- 提交用 conventional commits（`feat|fix|refactor|docs|test|chore`）。

## Review Focus

以下五类输入是本 spec 隐含、但没有任务测试会自然覆盖的，最容易咬到真实用户。每条都在对应任务的测试里钉住：

1. **`map.ground` 整个缺失（mock/网格模式）。** `MapStatic.ground` 类型上就是可选的（`world-mirror.ts:47`）。期望：退回现有色块渲染，不崩、不黑屏。→ Task 3。
2. **`gid == 0`（结构占地把 gid 抹成 0）。** 源图里没有这块像素。期望：画 `FALLBACK_COLOR=0x6b4f2a` 木色（既有契约），不是透明/黑色。→ Task 3。
3. **`gid` 超出源图范围（脏数据）。** `sampleTileColor` 已经 `gid <= 0 || gid > cols*rows` 兜底。期望：`paintTile` 走同一条兜底。→ Task 1 + Task 3。
4. **同一格的编辑状态在「编辑色恰好等于原色」时来回切。** 现有脏检测只看 `h`/`color`/`phase`，`EDIT_COLORS[3] == FALLBACK_COLOR == 0x6b4f2a` 是一个真实碰撞。期望：编辑状态变化一定触发重绘。→ Task 2。
5. **窗口 resize 拖拽时的全量重绘。** `redraw` 由 `WorldScene.ts:272` 的 `scale.on('resize')` 触发，是全量；逐帧路径走 `sync`→`paintGround(dirty)`。期望：`paintTile` 支持 dirty 矩形裁剪。→ Task 5。

## 会打红的既有测试（先读这一节，别在 Task 3/4 里被吓到）

`client/src/game/render/__tests__/iso-terrain.test.ts` 有 **27 条**用例，其中下列会被本计划改动打断。**逐条给出处置，不允许「跑红了一律改期望值」**：

| 行 | 用例 | 因哪个任务红 | 处置 |
|---|---|---|---|
| 181 | `expect(images).toHaveLength(3)` | Task 4（每格拆成 2 sprite） | 改用 `highCellCount()` 助手（见 Task 4 Step 1） |
| 193 | `expect(ground.ctx.fill).toHaveBeenCalledTimes(4)` | Task 3（改走 `drawImage`） | 改断言 `drawImage` 次数；`fill` 只应剩编辑格/兜底 |
| 202, 206, 218, 224, 227 | `expect(images).toHaveLength(N)` | Task 4 | 同上，`highCellCount()` |
| 261, 278, 289, 314 | `expect(images.filter(!destroyed)).toHaveLength(2)` | Task 4 | 同上 |
| 534 | `expect(ctx.fill).toHaveBeenCalledTimes(4800)` | Task 3 | 改为 `drawImage` 计数（40×40 全 gid 有效 ⇒ 1600 次 `drawImage`） |
| 539-551 | clipped repaint 的 `ctx.fill` 上下界断言 | Task 3 | 换到 `drawImage` 计数；上下界含义不变（全量 vs 裁剪） |
| 575, 606 | 两条**逐像素等价**（`ctx.pixels()` 对比） | Task 3 | **先做 Task 3b** 给 `rasterContext` 实现真 `drawImage`；否则这两条会退化成恒真，等于丢掉最强的回归网 |
| 363 | `shares a fixed height texture...` | Task 4 | 这条钉的正是要被拆掉的设计，**必须改写**（spec §3.4 判据） |
| 384 | 挖深柱显示石层 | Task 4 | 钉的是行为，只更新 `setTint`/`setDisplaySize` 期望值 |

> 判据（spec §3.4）：**钉的是旧实现细节还是旧行为？** 「一张共用纹理」「几个 Image 对象」是实现细节，该改；「挖掉树冠显示石层」是行为，不该改方向。

---

### Task 1: 等距图块投影的纯函数

**Files:**
- Create: `client/src/game/render/tile-projection.ts`
- Test: `client/src/game/render/__tests__/tile-projection.test.ts`

**Interfaces:**
- Consumes: 无（不依赖 Phaser、不依赖 `iso.ts`）。
- Produces:
  - `frameOf(gid: number, source: { width: number; height: number }): { x: number; y: number; w: number; h: number }` — gid（1-based）→ 源图矩形；`w/h` 恒 `TILE=16`；gid 无效时返回全零矩形。
  - `paintTile(ctx: CanvasRenderingContext2D, image: CanvasImageSource, sx: number, sy: number, gid: number, source: { width: number; height: number }): boolean` — `true` = 画了图块，`false` = gid 无效，调用方走 `paintBlock` 兜底。

**为什么列数从 `source` 推导、而不是硬编 140：** `sampleTileColor`（`iso-terrain.ts:43-49`）的 `cols = Math.floor(w / TILE)` 是从图像宽度算的。若 `frameOf` 硬编 140 而测试/换图时源图不是 2240 宽，顶面图块会整体偏移一格——spec §3.1 明确警告「两处必须一致」。**让两者都从同一个 `source.width` 推导，才能结构上杜绝漂移。**

- [ ] **Step 1: Write the failing test**

```ts
import { describe, expect, it } from 'vitest';
import { frameOf, paintTile } from '../tile-projection';

const TILE = 16;
const REAL = { width: 2240, height: 1600 }; // 140×100 个 16px 格
const SMALL = { width: 16, height: 16 };    // 测试夹具的 1×1 图

describe('frameOf', () => {
  it('maps gid to the same source rect the colour sampler reads', () => {
    expect(frameOf(1, REAL)).toEqual({ x: 0, y: 0, w: TILE, h: TILE });
    expect(frameOf(140, REAL)).toEqual({ x: 139 * TILE, y: 0, w: TILE, h: TILE });
    expect(frameOf(141, REAL)).toEqual({ x: 0, y: TILE, w: TILE, h: TILE });
    expect(frameOf(14000, REAL)).toEqual({ x: 139 * TILE, y: 99 * TILE, w: TILE, h: TILE });
  });

  it('derives the column count from the source image, not a hard-coded 140', () => {
    // 16×16 源图只有 1 列 1 行 ⇒ 只有 gid 1 有效
    expect(frameOf(1, SMALL)).toEqual({ x: 0, y: 0, w: TILE, h: TILE });
    expect(frameOf(2, SMALL)).toEqual({ x: 0, y: 0, w: 0, h: 0 });
  });

  it('returns a zero rect for gids that have no source pixels', () => {
    for (const gid of [0, -3, 14001, 1.5, Number.NaN]) {
      expect(frameOf(gid, REAL)).toEqual({ x: 0, y: 0, w: 0, h: 0 });
    }
  });
});

describe('paintTile', () => {
  it('draws the source cell through the exact iso projection and reports success', () => {
    const calls: unknown[] = [];
    const ctx = {
      imageSmoothingEnabled: true,
      save: () => calls.push('save'),
      restore: () => calls.push('restore'),
      transform: (...a: number[]) => calls.push(['transform', ...a]),
      drawImage: (...a: unknown[]) => calls.push(['drawImage', ...a]),
    } as unknown as CanvasRenderingContext2D;
    expect(paintTile(ctx, {} as CanvasImageSource, 100, 50, 141, REAL)).toBe(true);
    // 2:1 等距顶面：四点 (sx,sy-hh)(sx+hw,sy)(sx,sy+hh)(sx-hw,sy)
    // ⇒ transform(1, 0.5, -1, 0.5, sx, sy - 8)
    expect(calls).toContainEqual(['transform', 1, 0.5, -1, 0.5, 100, 42]);
    expect(calls).toContainEqual(['drawImage', {}, 0, 16, 16, 16, 0, 0, 16, 16]);
    expect(ctx.imageSmoothingEnabled).toBe(false);
  });

  it('returns false without touching the context when the gid has no pixels', () => {
    const calls: unknown[] = [];
    const ctx = {
      save: () => calls.push('save'),
      restore: () => calls.push('restore'),
      transform: () => calls.push('transform'),
      drawImage: () => calls.push('drawImage'),
    } as unknown as CanvasRenderingContext2D;
    expect(paintTile(ctx, {} as CanvasImageSource, 100, 50, 0, REAL)).toBe(false);
    expect(calls).toEqual([]);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd client; npx vitest run src/game/render/__tests__/tile-projection.test.ts`
Expected: FAIL — `Cannot find module '../tile-projection'`

- [ ] **Step 3: Implement `client/src/game/render/tile-projection.ts`**

- `frameOf(gid, source)`：`cols = Math.floor(source.width / 16)`、`rows = Math.floor(source.height / 16)`。非整数 / `gid <= 0` / `gid > cols*rows` → 全零矩形。否则 `x = ((gid-1) % cols) * 16`、`y = Math.floor((gid-1) / cols) * 16`。
- `paintTile`：先 `frameOf`；`w === 0` → `return false`（**不要**碰 ctx，测试钉了零调用）。否则 `ctx.save(); ctx.imageSmoothingEnabled = false; ctx.transform(1, 0.5, -1, 0.5, sx, sy - 8); ctx.drawImage(image, f.x, f.y, 16, 16, 0, 0, 16, 16); ctx.restore(); return true;`
- 仿射系数 `(1, 0.5, -1, 0.5)` 与 `block-atlas.ts:112` 的 `face()` 对顶面 `p=[sx,sy-8, sx+16,sy, sx,sy+8, sx-16,sy]` 算出的完全相同（spec §3.1 已数值验证）。**不要**改成反解 (u,v) 的写法（spec 陷阱 #1：反解只画出半个菱形）。

- [ ] **Step 4: Run test to verify it passes**

Run: `cd client; npx vitest run src/game/render/__tests__/tile-projection.test.ts`
Expected: PASS（5 tests）

- [ ] **Step 5: Commit**

```bash
git add client/src/game/render/tile-projection.ts client/src/game/render/__tests__/tile-projection.test.ts
git commit -m "feat(render): add iso tile projection helpers for terrain baking"
```

---

### Task 2: `SurfaceCell` 增加 `edited` 标志

**Files:**
- Modify: `client/src/game/render/iso-terrain.ts`（`SurfaceCell` ~24-34 行；cell 构造 ~240-250 行；两处脏检测 ~257、~289 行）
- Test: `client/src/game/render/__tests__/iso-terrain.test.ts`

**Interfaces:**
- Consumes: 无。
- Produces: `SurfaceCell` 新增 `edited: boolean`（Task 3 用它分流）。

- [ ] **Step 1: Write the failing test**

关键：必须构造一个**颜色不变、只有编辑状态变**的格子，否则测试恒真。

`setup()` 的源图是 16×16 纯色（`100,150,200`）⇒ 只有 gid 1 有效，取色 `0x6496c8`；`gid 0` 或 gid>1 取 `FALLBACK_COLOR = 0x6b4f2a`。而 `EDIT_COLORS[3] === FALLBACK_COLOR === 0x6b4f2a`。所以：**gid=0 的格子 + 高度 3 的编辑**，颜色前后都是 `0x6b4f2a`，只有 `edited` 翻转。

```ts
it('repaints when only the edited flag flips, even if the colour is identical', () => {
  const { terrain, map, structures, canvases } = setup([1, 1, 1, 1], 2, 2, true);
  map.ground!.fill(0); // 全部 gid=0 ⇒ 颜色 = FALLBACK_COLOR = 0x6b4f2a
  const edits = new Map<
    string,
    { x: number; y: number; action: 'dig' | 'place'; gid: number; height: number }
  >();
  terrain.redraw(map, structures, edits);
  const ground = canvases.find((c) => c.width > 32 && c.height > 32)!;
  const before = ground.ctx.drawImage.mock.calls.length + ground.ctx.fill.mock.calls.length;
  // 编辑色 0x6b4f2a 与原色完全相同，唯一变化是 edited: false → true
  edits.set('0,0', { x: 0, y: 0, action: 'place', gid: 0, height: 3 });
  terrain.sync(map, structures, edits);
  const after = ground.ctx.drawImage.mock.calls.length + ground.ctx.fill.mock.calls.length;
  expect(after).toBeGreaterThan(before); // 无 edited 标志时不会重绘 ⇒ 本条红
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd client; npx vitest run src/game/render/__tests__/iso-terrain.test.ts -t "only the edited flag flips"`
Expected: FAIL — `after === before`（颜色未变，脏检测不置位）

- [ ] **Step 3: Add `edited` to `SurfaceCell` and both dirty checks**

1. `SurfaceCell` 接口加 `edited: boolean;`（放在 `bank` 之后）。
2. cell 构造加 `edited: edits.has(key)`——**无条件**记录（注意现有的 `edits.has(key) && phase === undefined` 是**选色**条件，别把两个混成一处）。
3. 两处脏检测都加 `|| prior?.edited !== <新值>`：~257 行的 `prior?.h !== h || prior.color !== color`，~289 行的 `prior?.h !== cell.h || prior.color !== cell.color || prior.phase !== cell.phase`。

- [ ] **Step 4: Run test to verify it passes**

Run: `cd client; npx vitest run src/game/render/__tests__/iso-terrain.test.ts`
Expected: PASS（全部 27 条；本任务不改变绘制路径，所以计数断言不受影响。若有用例构造了 `SurfaceCell` 字面量而红，补 `edited: false`）

- [ ] **Step 5: Commit**

```bash
git add client/src/game/render/iso-terrain.ts client/src/game/render/__tests__/iso-terrain.test.ts
git commit -m "refactor(render): track edited state on surface cells"
```

---

### Task 3b: 给测试光栅器实现真 `drawImage`（先做，Task 3 依赖它）

**Files:**
- Modify: `client/src/game/render/__tests__/raster-context.ts`
- Test: `client/src/game/render/__tests__/raster-context.test.ts`（新建）

**Interfaces:**
- Consumes: 现有 `rasterContext(size)` 的 `save/restore/rect/clip/fillStyle/fill/pixels`。
- Produces: `rasterContext` 增加 `transform(a,b,c,d,e,f)`、`drawImage(src, sx, sy, sw, sh, dx, dy, dw, dh)`、`imageSmoothingEnabled`，使 `pixels()` 反映真实的仿射贴图。

**为什么必须做：** `iso-terrain.test.ts:575` 与 `:606` 两条用例靠 `ctx.pixels()` 逐像素比对「裁剪重绘」与「全量重绘」等价。现在 `drawImage` 是空 mock，地面一旦改走 `paintTile`，两条比对会退化成「两边都是空」⇒ 恒真 ⇒ **丢掉本轮最强的回归网**。

- [ ] **Step 1: Write the failing test**

```ts
import { describe, expect, it } from 'vitest';
import { rasterContext } from './raster-context';

function ctxOf(w: number, h: number) {
  const canvas = { width: w, height: h };
  return rasterContext(() => canvas);
}

describe('rasterContext drawImage', () => {
  it('maps a 16×16 source cell through the iso affine and lands pixels', () => {
    const ctx = ctxOf(64, 64);
    const src = { width: 16, height: 16, pixels: new Uint32Array(256).fill(0xff00ff00) };
    ctx.save();
    ctx.transform(1, 0.5, -1, 0.5, 32, 24); // 顶面：中心 (32,32)
    ctx.drawImage(src, 0, 0, 16, 16, 0, 0, 16, 16);
    ctx.restore();
    const px = ctx.pixels();
    expect(px[32 * 64 + 32]).toBe(0xff00ff00); // 中心被覆盖
    expect(px[0]).toBe(0);                     // 远处不受影响
  });

  it('respects save/restore of the transform stack', () => {
    const ctx = ctxOf(64, 64);
    const src = { width: 16, height: 16, pixels: new Uint32Array(256).fill(0xffff0000) };
    ctx.save();
    ctx.transform(1, 0.5, -1, 0.5, 32, 24);
    ctx.restore();
    ctx.drawImage(src, 0, 0, 16, 16, 0, 0, 16, 16); // 恒等变换 ⇒ 画在左上角
    const px = ctx.pixels();
    expect(px[4 * 64 + 4]).toBe(0xffff0000);
    expect(px[32 * 64 + 32]).toBe(0);
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd client; npx vitest run src/game/render/__tests__/raster-context.test.ts`
Expected: FAIL — `ctx.transform is not a function`

- [ ] **Step 3: Implement transform + drawImage in `raster-context.ts`**

要点（算法不在测试里）：
- 维护当前 2×3 仿射矩阵 `[a,b,c,d,e,f]`（初值恒等 `1,0,0,1,0,0`）；`save/restore` 连同矩阵一起入栈/出栈（现有栈已存 `clipping` 与 `fillStyle`，加一个 `matrix` 字段）。
- `transform(a,b,c,d,e,f)`：`matrix = compose(current, [a,b,c,d,e,f])`（标准 2×3 矩阵乘法：`[a1*a2+c1*b2, b1*a2+d1*b2, a1*c2+c1*d2, b1*c2+d1*d2, a1*e2+c1*f2+e1, b1*e2+d1*f2+f1]`）。
- `drawImage(src, sx, sy, sw, sh, dx, dy, dw, dh)`：对目标矩形 `[dx,dx+dw)×[dy,dy+dh)` 的**每个像素中心**，先经 `matrix` 求逆映射回源坐标 `(u,v)`；若落在 `[sx,sx+sw)×[sy,sy+sh)` 内，则取源像素 `src.pixels[(sy+⌊v⌋)*src.width + (sx+⌊u⌋)]` 写入。`imageSmoothingEnabled === false` 时取最近邻（上面就是这个）；为 `true` 时也按最近邻（测试只用到 `false`，不必实现双线性——**写注释说明**）。
- 裁剪（`clipping`）与 `clearRect` 的既有语义保持不变：`drawImage` 也要尊重 `clipping`。

- [ ] **Step 4: Run to verify it passes**

Run: `cd client; npx vitest run src/game/render/__tests__/raster-context.test.ts`
Expected: PASS（2 tests）

- [ ] **Step 5: Commit**

```bash
git add client/src/game/render/__tests__/raster-context.ts client/src/game/render/__tests__/raster-context.test.ts
git commit -m "test(render): rasterize drawImage affines in the software context"
```

---

### Task 3: 地面烘焙——`paintGround` 走 `paintTile`

**Files:**
- Modify: `client/src/game/render/iso-terrain.ts`（`paintGround` ~345-385 行；`readColors` ~537 行保留并顺带缓存源图）
- Test: `client/src/game/render/__tests__/iso-terrain.test.ts`（含上面「会打红」表里的 193 / 534 / 539-551 / 575 / 606）

**Interfaces:**
- Consumes: Task 1 的 `paintTile`/`frameOf`；Task 2 的 `cell.edited`；Task 3b 的光栅器。
- Produces: `IsoTerrain` 新增私有字段 `sourceImage: CanvasImageSource | null` 与 `sourceSize: { width: number; height: number } | null`（Task 4 复用）。

- [ ] **Step 1: Write the failing tests**

```ts
it('bakes the real tileset pixels into the ground for unedited low cells', () => {
  const { terrain, map, structures, textures, canvases } = setup([1, 1, 1, 1], 2, 2, true);
  textures.set('god-town-16', { width: 2240, height: 1600 }); // 让 gid 1/2/141 都有效
  map.ground!.set([1, 2, 141, 0]);
  terrain.redraw(map, structures);
  const ground = canvases.find((c) => c.width > 32 && c.height > 32)!;
  // 三个有效 gid 走 drawImage；gid=0 走 paintBlock 的 fill 兜底
  expect(ground.ctx.drawImage).toHaveBeenCalledTimes(3);
});

it('falls back to flat polygons when the map carries no ground layer', () => {
  const { terrain, map, structures, canvases } = setup([1, 1, 1, 1], 2, 2, true);
  delete (map as { ground?: Uint16Array }).ground;
  terrain.redraw(map, structures);
  const ground = canvases.find((c) => c.width > 32 && c.height > 32)!;
  expect(ground.ctx.drawImage).not.toHaveBeenCalled();
  expect(ground.ctx.fill).toHaveBeenCalled(); // 仍是色块渲染
});

it('keeps flat polygons for edited cells even when the gid is valid', () => {
  const { terrain, map, structures, textures, canvases } = setup([1, 1, 1, 1], 2, 2, true);
  textures.set('god-town-16', { width: 2240, height: 1600 });
  map.ground!.set([1, 2, 141, 0]);
  const edits = new Map([
    ['0,0', { x: 0, y: 0, action: 'dig' as const, gid: 0, height: 1 }],
  ]);
  terrain.redraw(map, structures, edits);
  const ground = canvases.find((c) => c.width > 32 && c.height > 32)!;
  expect(ground.ctx.drawImage).toHaveBeenCalledTimes(2); // 只剩两个未编辑格
});

it('falls back when the gid is outside the source image', () => {
  const { terrain, map, structures, canvases } = setup([1, 1, 1, 1], 2, 2, true);
  map.ground!.set([1, 2, 3, 4]); // 夹具源图 16×16 ⇒ 只有 gid 1 有效
  terrain.redraw(map, structures);
  const ground = canvases.find((c) => c.width > 32 && c.height > 32)!;
  expect(ground.ctx.drawImage).toHaveBeenCalledTimes(1);
  expect(ground.ctx.fill).toHaveBeenCalled();
});
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd client; npx vitest run src/game/render/__tests__/iso-terrain.test.ts -t "bakes the real tileset pixels"`
Expected: FAIL（现在零 `drawImage`）

- [ ] **Step 3: Rewrite the `paintGround` inner loop**

**保留**：`dirty` 裁剪、`first`/`last`/`minY`/`maxY` 的对角线枚举、`if (cell.h >= 2) continue;`、`isoProject`。**只替换最后三行**：

```ts
const gid = map.ground?.[y * map.w + x] ?? 0;
const painted =
  !cell.edited &&
  this.sourceImage !== null &&
  this.sourceSize !== null &&
  paintTile(ctx, this.sourceImage, top.sx, top.sy, gid, this.sourceSize);
if (!painted) {
  if (this.atlas) this.atlas.paintBlock(ctx, top.sx, top.sy, cell.h, cell.color);
  else paintBlock(ctx, top.sx, top.sy, cell.h, cell.color);
}
```

`sourceImage` / `sourceSize` 在 `readColors()` 里顺便赋值（它本来就要 `getSourceImage()`）；纹理不存在时两者置 `null`。**不要**在 `paintGround` 里逐格取纹理。

`map.ground` 缺失 ⇒ `gid` 恒 0 ⇒ 全部兜底 ⇒ 与今天逐像素相同（Review Focus #1）。`gid === 0` 走兜底且 `cell.color` 已是 `FALLBACK_COLOR`（木色正确，Review Focus #2）。`gid` 超范围 ⇒ `paintTile` 返回 false ⇒ 兜底（Review Focus #3）。

- [ ] **Step 4: Update the assertions listed in the「会打红」表**

按表逐条改：193 / 534 / 539-551 换成 `drawImage` 计数；575 / 606 因为 Task 3b 已给光栅器真 `drawImage`，**应该直接保持绿**——若红，说明 Task 3b 的逆映射与 `paintTile` 的正变换不自洽，**先修 Task 3b，别改断言**。

- [ ] **Step 5: Run the whole render suite**

Run: `cd client; npx vitest run src/game/render`
Expected: PASS（含 `iso-banks.test.ts` 368 行那套）

- [ ] **Step 6: Commit**

```bash
git add client/src/game/render/iso-terrain.ts client/src/game/render/__tests__/iso-terrain.test.ts
git commit -m "feat(render): bake real tileset pixels into the isometric ground"
```

---

### Task 4: 高格顶面贴真实图块（`syncBlock` 拆顶面/侧面）

**Files:**
- Modify: `client/src/game/render/iso-terrain.ts`（`syncBlock` ~307-340 行；销毁循环 ~285-295 行；`BlockView` ~17-21 行）
- Modify: `client/src/game/render/__tests__/iso-terrain.test.ts`（改写 363；更新 384 的期望值；替换 ~10 处 Image 计数断言）

**Interfaces:**
- Consumes: Task 1 `frameOf`；Task 3 的 `sourceImage`/`sourceSize`。
- Produces: `BlockView` 变为 `{ side: Image; top: Image | null; texture: string; phase: string | undefined }`。

- [ ] **Step 1: Add the test helper and rewrite the pinned test**

在测试文件顶部加助手（把「数格子」与「数 sprite」解耦）：

```ts
/** 高格是每格 2 个 sprite（side + top），所以按格子计数，而不是按 Image 计数。 */
function highCells(images: { key: string }[]): string[] {
  return images
    .map((image) => image.key)
    .filter((key) => key.startsWith('tile-') || key.startsWith('iso-block-'));
}
```

替换 363 行的用例：

```ts
it('gives each high cell its own tileset frame while keeping shared side masks', () => {
  const { terrain, map, structures, textures, images } = setup([2, 2, 2, 2], 2, 2);
  textures.set('god-town-16', { width: 2240, height: 1600 });
  map.ground!.set([1, 2, 141, 140]);
  terrain.redraw(map, structures);
  // 侧面仍共用 mask 纹理（只有 iso-block-2）
  expect([...textures.keys()].filter((k) => k.startsWith('iso-block-'))).toEqual(['iso-block-2']);
  // 顶面：4 个不同 gid → 4 个不同 frame 名
  const tops = images.filter((i) => i.key.startsWith('tile-'));
  expect(new Set(tops.map((i) => i.key)).size).toBe(4);
});

it('does not share a top texture between two cells with different gids', () => {
  const { terrain, map, structures, textures, images } = setup([2, 2, 2, 2], 2, 2);
  textures.set('god-town-16', { width: 2240, height: 1600 });
  map.ground!.set([1, 2, 141, 140]);
  terrain.redraw(map, structures);
  const tops = images.filter((i) => i.key.startsWith('tile-'));
  expect(tops[0]!.key).not.toBe(tops[1]!.key);
});
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd client; npx vitest run src/game/render/__tests__/iso-terrain.test.ts -t "own tileset frame"`
Expected: FAIL（现在所有 h=2 共用 `iso-block-2`，零 `tile-*`）

- [ ] **Step 3: Split the block sprite into side + top**

`syncBlock` 每格产出**两个** Image：

1. **侧面**：沿用现有逻辑（共用 `iso-block-${h}` canvas 纹理 + `setTint(color)`），但 `setDisplaySize(ISO.TW, h*ISO.HH)`（**去掉**原来那 `+ ISO.TH`），位置 `base.sy`，`depth = depthKey(x, y) - 0.01`。
2. **顶面**：`setTexture(TILESET_KEY, 'tile-' + gid)`，`setDisplaySize(ISO.TW, ISO.TH)`，位置 `base.sy - h*ISO.HH`（顶面中心），`depth = depthKey(x, y)`。gid 从 `map.ground` 取；无效/缺失 ⇒ **不建顶面**（侧面纹理里的 top face 已兜底）。

新增私有方法 `ensureTileFrames(map)`，在 `redraw` 开头调一次：

```ts
const tex = this.scene.textures.get(TILESET_KEY);
if (!tex || !this.sourceSize) return;
for (let y = 0; y < map.h; y++)
  for (let x = 0; x < map.w; x++) {
    const gid = map.ground?.[y * map.w + x] ?? 0;
    const name = 'tile-' + gid;
    if (gid <= 0 || tex.has(name)) continue;
    const f = frameOf(gid, this.sourceSize);
    if (f.w === 0) continue;
    tex.add(name, 0, f.x, f.y, f.w, f.h);
  }
```

> Phaser `Texture.add(name, sourceIndex, x, y, w, h)` 只登记元数据、不复制像素（spec §3.1 已论证显存代价为 0）。测试的 mock `textures.get()` 只返回 `{ getSourceImage }`，所以 **mock 也要补 `has` 与 `add`**（见 Step 4）。

- [ ] **Step 4: Update the test mock and the count assertions**

1. `setup()` 的 `scene.textures.get` 改为返回带 `has`/`add` 的对象：
   ```ts
   get: (key: string) => {
     const frames = new Map<string, unknown>();
     return { getSourceImage: () => textures.get(key), has: (n: string) => frames.has(n), add: (n: string) => { frames.set(n, true); return {}; } };
   },
   ```
   ⚠ 每次 `get()` 返回新对象会让 `has` 永远 false ⇒ `add` 被反复调用。**把 `frames` 提到 `setup()` 外层**，按 key 缓存。

2. 按「会打红」表把 `expect(images).toHaveLength(N)` 类断言改成 `highCells()` 计数（181 / 202 / 206 / 218 / 224 / 227 / 261 / 278 / 289 / 314）。

3. 更新 177 行的锚点断言：`setDisplaySize(32, height*16)`（侧面，不含顶面）与顶面的 `setDisplaySize(32, 16)` 分别断言。

4. 384（挖深柱显示石层）：**行为不变**，只更新期望值。

- [ ] **Step 5: Update the destroy loop**

销毁循环改为 `view.side.destroy()` 与 `view.top?.destroy()`；`transitions` 里若按 image 索引，两个都登记。

- [ ] **Step 6: Run the whole render suite**

Run: `cd client; npx vitest run src/game/render`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add client/src/game/render/iso-terrain.ts client/src/game/render/__tests__/iso-terrain.test.ts
git commit -m "feat(render): texture high-cell tops with real tileset frames"
```

---

### Task 5: dirty 裁剪护栏

**Files:**
- Modify: `client/src/game/render/iso-terrain.ts`（`paintGround` 的 dirty 分支）
- Test: `client/src/game/render/__tests__/iso-terrain.test.ts`

**Interfaces:**
- Consumes: Task 3 的 `paintTile` 路径。
- Produces: 无。

- [ ] **Step 1: Write the failing test**

```ts
it('limits a dirty repaint to the changed cell instead of redrawing the whole map', () => {
  const { terrain, map, structures, textures, canvases } = setup([1, 1, 1, 1], 2, 2, true);
  textures.set('god-town-16', { width: 2240, height: 1600 });
  map.ground!.set([1, 2, 141, 140]);
  terrain.redraw(map, structures);
  const ground = canvases.find((c) => c.width > 32 && c.height > 32)!;
  ground.ctx.drawImage.mockClear();
  map.ground![3] = 139; // 只改 (1,1) 的 gid
  terrain.sync(map, structures);
  expect(ground.ctx.drawImage.mock.calls.length).toBeLessThan(4); // 全量会是 4
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd client; npx vitest run src/game/render/__tests__/iso-terrain.test.ts -t "limits a dirty repaint"`
Expected: FAIL（`paintTile` 不认 dirty 裁剪，仍画 4 次）

- [ ] **Step 3: Skip cells outside the dirty rect**

在 `paintGround` 的对角线内层循环里、取完 `top` 之后加（**不要**用 `ctx.clip()`——`rasterContext` 只实现了矩形 clip，而旋转菱形的包围盒判定更直接）：

```ts
if (dirty) {
  const left = top.sx - 16, right = top.sx + 16;
  const up = top.sy - 8 - cell.h * 16, down = top.sy + 8;
  if (right < dirty.left || left > dirty.right || down < dirty.top || up > dirty.bottom) continue;
}
```

- [ ] **Step 4: Run to verify pass**

Run: `cd client; npx vitest run src/game/render`
Expected: PASS（575 / 606 的逐像素等价仍必须绿——它们正是在验「裁剪重绘 == 全量重绘」）

- [ ] **Step 5: Commit**

```bash
git add client/src/game/render/iso-terrain.ts client/src/game/render/__tests__/iso-terrain.test.ts
git commit -m "perf(render): clip dirty ground repaints to the affected rect"
```

---

### Task 6: 前端全门禁 + 真实地图拾取基线复跑

**Files:** 无代码改动（纯验证）。

- [ ] **Step 1: Client gates**

```powershell
cd client
npm run typecheck > ..\logs\typecheck.log 2>&1; echo "EXIT:$?"
npm run lint > ..\logs\lint.log 2>&1; echo "EXIT:$?"
npx prettier --check . > ..\logs\prettier.log 2>&1; echo "EXIT:$?"
npx vitest run > ..\logs\vitest.log 2>&1; echo "EXIT:$?"
```

Expected: 四个 `EXIT:0`。vitest 基线 **399P/53F**（第二十二轮），本计划只应增加通过数、不得新增失败。

- [ ] **Step 2: Re-run the real-map picking baseline**

用第二十二轮已有的入口（codex 树 `.orca/audits/round22-2026-11-04/measure.cjs`，复制到主树临时目录跑；**别在真实库上做实验**）。

Expected（第二十二轮实测基线，不得回退）：土坎 **448/448**、可走 **3947/3947**、高块 **7141/7373**。

任一项变化 ⇒ **停下来查**。本计划不碰拾取，变化意味着 Task 3/4 的绘制改动间接影响了 `pickVoxel`（它依赖 `isBank` 与深度序）。

- [ ] **Step 3: Browser check（ms-playwright chromium only）**

启动后端 + 前端，用 `ms-playwright` 打包的 chromium 截图，与 `.orca/tmp/preview/variant-d.png` 对照：桃花林/溪流/石桥/瓦顶/梯田一眼可辨；挖一格、放一格仍有立体反馈；1440 / 1024 / 390 三种宽度无横向溢出、零 pageerror。

---

### Task 7: 气味源强度与独立门槛（B1 代码侧）

**Files:**
- Modify: `sim/perception/smell_world.py:20`
- Modify: `sim/perception/profiles/base.py`
- Modify: `sim/perception/senses.py:323`
- Modify: `sim/perception/narrate.py:80-91`
- Test: 新建 `sim/tests/test_smell_calibration.py`；改 `sim/tests/test_m2_smell_wiring.py`

**Interfaces:**
- Consumes: `SmellWorld.step(positions, wind)`（已存在）。
- Produces: `PerceptionProfile.smell_floor: float = 0.08`；`narrate_smell` 四档阈值 `0.55 / 0.30 / 0.18 / 0.08`。

**定标依据（spec §4.1 实测，直接用，不要重测）：** strength=0.04、floor=0.08 ⇒ 独行 0.063（不触发）、稀疏 10 人 0/10、聚集 50 人 50/50（min 0.168 / med 0.350 / max 0.430）。

- [ ] **Step 1: Write the failing calibration test**

```python
"""B1 定标：人群密集可闻、独行不可闻（spec §4.1 的实测口径写成回归钉）。"""

from __future__ import annotations

import numpy as np

from sim.perception.smell_world import SMELL_SOURCE_STRENGTH, SmellWorld
from sim.perception.profiles.base import PerceptionProfile

TICKS = 200
WIND = (0.0, 0.0)  # 静风 = 最坏情形（不吹散）


def _settle(positions: dict[str, tuple[int, int]]) -> np.ndarray:
    world = SmellWorld(height=100, width=140)
    values = np.zeros(0)
    for _ in range(TICKS):
        samples = world.step(positions, wind=WIND)
        values = np.array(list(samples.values()), dtype=np.float64)
    return values


def _clustered(n: int, seed: int = 42) -> dict[str, tuple[int, int]]:
    rng = np.random.default_rng(seed)
    anchors = ((100, 52), (72, 52))
    return {
        f"npc_{i}": (
            anchors[i % 2][0] + int(rng.integers(-4, 5)),
            anchors[i % 2][1] + int(rng.integers(-4, 5)),
        )
        for i in range(n)
    }


def test_source_strength_is_calibrated_for_crowds() -> None:
    assert SMELL_SOURCE_STRENGTH == 0.04


def test_smell_floor_is_its_own_knob() -> None:
    profile = PerceptionProfile(species="human", vision_radius=12.0, hearing_radius=14.0)
    assert profile.smell_floor == 0.08
    assert profile.smell_floor != profile.hearing_floor


def test_a_lone_walker_never_smells_the_crowd() -> None:
    values = _settle({"walker": (100, 52)})
    assert float(values.max()) < 0.08, "独行者不该闻到味道（用户反馈的直接来源）"


def test_a_crowd_always_smells() -> None:
    values = _settle(_clustered(50))
    assert int((values >= 0.08).sum()) == 50


def test_the_floor_coincides_with_the_lowest_text_tier() -> None:
    """门槛必须与最低档重合，否则「过了门槛却落不进任何档」的死区（spec 陷阱 #7）。"""
    from sim.perception.narrate import narrate_smell

    assert narrate_smell(0.08) != narrate_smell(0.079)
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest sim/tests/test_smell_calibration.py -q`
Expected: FAIL（`SMELL_SOURCE_STRENGTH == 1.0`；`PerceptionProfile` 无 `smell_floor`）

- [ ] **Step 3: Implement the three constants**

1. `smell_world.py:20` → `SMELL_SOURCE_STRENGTH: float = 0.04`。
2. `profiles/base.py` 加 `smell_floor: float = 0.08  # 嗅觉显著性地板（与「隐约」档同值，spec §4.1）`。
3. `senses.py:323` → `smell_floor = profile.smell_floor`（删掉「暂与听觉同档」注释）。
4. `narrate.py:80-91` 四档改 `>= 0.55 / >= 0.30 / >= 0.18 / >= 0.08`；`< 0.08` 仍返回「隐约有一丝陌生的气味。」（调用方已在地板过滤，这里只是防御）。

- [ ] **Step 4: Fix the fixture that pinned the old strength**

`test_m2_smell_wiring.py::test_frame_contains_smell_observation` 用两人相距 1 格（(10,10)/(11,10)），新强度下浓度仅 0.0196 ⇒ **必然红**。这是**夹具设计问题**（spec §4.1 明写）：一格外的一个人本来就不该让人闻到。改 `_state()` 为 ≥5 人密集聚集（`alice (10,10)`、`bob (10,10)`、`carol (10,11)`、`dave (11,10)`、`erin (11,11)`），断言不变。

**不要**把 `smell_floor` 降到 0.02 来救它（spec 陷阱 #8）。

- [ ] **Step 5: Run both files + the wider perception suite**

```powershell
uv run pytest sim/tests/test_smell_calibration.py sim/tests/test_m2_smell_wiring.py -q
uv run pytest sim/tests -k "smell or perception or senses" -q
```

Expected: PASS。若有其它用例硬编旧强度或旧档位文案，按「描述现在 / 记载过去」判据逐个处理。

- [ ] **Step 6: Commit**

```bash
git add sim/perception/smell_world.py sim/perception/profiles/base.py sim/perception/senses.py sim/perception/narrate.py sim/tests/test_smell_calibration.py sim/tests/test_m2_smell_wiring.py
git commit -m "fix(perception): calibrate smell so crowds smell and lone walkers do not"
```

---

### Task 8: 气味叙事的跨帧抑制（B1 叙事层）

**Files:**
- Create: `sim/api/narration_cache.py`
- Modify: `sim/api/main.py:537-550`、`:1257`
- Test: 新建 `sim/tests/test_smell_repeat_suppression.py`

**Interfaces:**
- Consumes: `PerceptionFrame`（frozen）与 `frame.narrated(language=...)`（**纯函数，不改**）。
- Produces: `NarratedCache`，方法 `remember(key: str, entry: tuple[object, str]) -> str` 与 `clear() -> None`。

**为什么落在 `main.py` 而不是 `frame.narrated()`：** `narrated()` 是 `ConfigDict(frozen=True)` 的纯方法、帧每拍重建，无处记状态，且被大量测试直调（spec §4.1、陷阱 #22）。

- [ ] **Step 1: Write the failing test**

```python
"""B1 叙事层：同档气味文案不连续重复（spec §4.1 的抑制口径）。"""

from __future__ import annotations

from sim.api.narration_cache import NarratedCache

SMELLY = "你闻到：空气里飘着一股明显的味道。"


def _frame(text: str = SMELLY) -> tuple[object, str]:
    return (object(), text)


def test_second_identical_line_is_softened() -> None:
    cache = NarratedCache()
    first = cache.remember("chenmo", _frame())
    second = cache.remember("chenmo", _frame())
    assert "明显的味道" in first
    assert "还在" in second, "第二次应换成省略式，而不是原句"


def test_third_and_later_are_dropped() -> None:
    cache = NarratedCache()
    for _ in range(2):
        cache.remember("chenmo", _frame())
    third = cache.remember("chenmo", _frame())
    assert third == "四周很安静。", "第三次起整句不出现，回落到空帧文案"


def test_a_different_line_resets_the_counter() -> None:
    cache = NarratedCache()
    cache.remember("chenmo", _frame())
    cache.remember("chenmo", _frame())
    assert "还在" not in cache.remember("chenmo", _frame("你闻到：隐约有一丝陌生的气味。"))


def test_a_new_frame_object_resets_the_counter() -> None:
    cache = NarratedCache()
    first_frame = _frame()
    cache.remember("chenmo", first_frame)
    cache.remember("chenmo", (first_frame[0], first_frame[1]))  # 同一帧对象，同句 ⇒ 抑制
    assert "还在" in cache.remember("chenmo", (first_frame[0], first_frame[1]))


def test_clear_resets_everything() -> None:
    cache = NarratedCache()
    cache.remember("chenmo", _frame())
    cache.remember("chenmo", _frame())
    cache.clear()
    assert "还在" not in cache.remember("chenmo", _frame())
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest sim/tests/test_smell_repeat_suppression.py -q`
Expected: FAIL — `No module named 'sim.api.narration_cache'`

- [ ] **Step 3: Implement `sim/api/narration_cache.py`**

- 内部 `dict[str, _Entry]`，`_Entry = (frame_identity, smell_line, repeat_count)`。
- `remember(key, (frame, text))`：
  1. 从 `text` 抽「你闻到：…。」那一行（没有则原样返回并重置计数）。
  2. 若 `frame_identity is entry.frame and smell_line == entry.line`：`count += 1`；`count == 2` → 该行替换为 `你闻到：那股味道还在。`；`count >= 3` → 删掉该行，整段为空则返回 `"四周很安静。"`。
  3. 否则 `count = 1`，缓存新行。
- `clear()` 清空。
- **只压嗅觉那一句**：内感受/视觉/听觉照常逐帧出（spec §4.1 表格）。

- [ ] **Step 4: Wire it into `_hidden_context`**

`main.py:537` 的 `_narrated_cache` 换成 `_narration = NarratedCache()`；`_hidden_context` 里改为：

```python
text = frame.narrated(language=language if npc_id == CHENMO_ID else None)
return _narration.remember(npc_id, (frame, text))
```

`main.py:1257` 的 `_narrated_cache.clear()` → `_narration.clear()`。

- [ ] **Step 5: Run tests + regression suites**

```powershell
uv run pytest sim/tests/test_smell_repeat_suppression.py -q
uv run pytest sim/tests -k "perception or narrated or monologue" -q
```

Expected: PASS。纯函数层「同一帧连调两次 `narrated()` 结果相同」的用例不受影响（抑制在 `main.py` 层）。

- [ ] **Step 6: Commit**

```bash
git add sim/api/narration_cache.py sim/api/main.py sim/tests/test_smell_repeat_suppression.py
git commit -m "fix(narration): stop repeating the same smell line frame after frame"
```

---

### Task 9: B4 — prompt 地图尺寸订正 + 动作面集合差测试

**Files:**
- Modify: `sim/llm/prompts/assembler.py:35`
- Test: 新建 `sim/tests/test_action_surface.py`

**Interfaces:**
- Consumes: `M1_SUPPORTED_ACTIONS`（`gate.py:33`）、`IntentAction`（`intent.py:12`）、`_REQUIREMENTS_TEXT`（`assembler.py:30`）。
- Produces: 无新接口。

- [ ] **Step 1: Write the failing test**

```python
"""B4：prompt 里的地图尺寸必须是真的；动作面各层必须一一对应。"""

from __future__ import annotations

from typing import get_args

from sim.agent.gate import M1_SUPPORTED_ACTIONS
from sim.agent.intent import IntentAction
from sim.llm.prompts.assembler import _REQUIREMENTS_TEXT


def test_prompt_states_the_real_map_size() -> None:
    assert "140×100" in _REQUIREMENTS_TEXT
    assert "96×96" not in _REQUIREMENTS_TEXT


def test_only_demolish_and_use_are_parseable_but_gated_out() -> None:
    """这两个有意保留在解析层、被闸门明确拒（明确拒绝 > 解析错误）。"""
    assert set(get_args(IntentAction)) - M1_SUPPORTED_ACTIONS == {"demolish", "use"}


def test_the_known_silent_actions_are_explicitly_listed() -> None:
    """take/give 本轮不动（用户裁定单列）：它们落到尾部独白、零副作用。

    这条把「已知的技术债」显式钉住，防止它悄悄扩大，也防止有人删掉白名单项
    却忘了同步这个清单。
    """
    known_silent = {"take", "give"}
    assert known_silent <= M1_SUPPORTED_ACTIONS, "技术债项若已移除，请同步更新本测试"
```

> 第三条**不**去读 `execute_pending` 的分支（那要靠 AST 或 mock，脆弱）。行为覆盖由 `test_m4c_llm_driver.py` 的逐动作用例承担（`wait` 已有 `test_wait_intent_no_move`）。

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest sim/tests/test_action_surface.py -q`
Expected: FAIL — `"140×100" not in _REQUIREMENTS_TEXT`

- [ ] **Step 3: Fix the prompt text**

`assembler.py:35`：`"镇子是 96×96 的格子，路面和空地能走，屋顶、水塘、树林进不去，"` → `"镇子是 140×100 的格子，路面和空地能走，屋顶、水塘、树林进不去，"`。

**只改这一处。** `ws.py:894` 是旧图名的兼容说明（不改）；5 个测试文件里的 `96×96` 是历史注释（不改）。判据见 spec §4.4 第 1 条。

- [ ] **Step 4: Run to verify pass + no regressions**

```powershell
uv run pytest sim/tests/test_action_surface.py -q
uv run pytest sim/tests -k "intent or gate or prompt or assembler" -q
```

Expected: PASS。前缀缓存契约只锚 `messages[0]`，`_REQUIREMENTS_TEXT` 在 `messages[1]` 尾部，不应受影响。

- [ ] **Step 5: Commit**

```bash
git add sim/llm/prompts/assembler.py sim/tests/test_action_surface.py
git commit -m "fix(llm): state the real 140x100 map size in the action contract"
```

---

### Task 10: 主树全门禁 + 收尾

**Files:** 无代码改动（除 Step 4 的文档读数）。

- [ ] **Step 1: Full backend gates**

```powershell
uv run pytest -m "not bench" > logs\pytest.log 2>&1; echo "EXIT:$?"
uv run ruff check . > logs\ruff.log 2>&1; echo "EXIT:$?"
uv run ruff format --check . > logs\rufffmt.log 2>&1; echo "EXIT:$?"
uv run pyright > logs\pyright.log 2>&1; echo "EXIT:$?"
```

Expected: 四个 `EXIT:0`。

- [ ] **Step 2: Full client gates**

同 Task 6 Step 1。Expected: 全 `EXIT:0`，vitest 不低于 399P。

- [ ] **Step 3: Asset `--check`（本计划未动资产，但门禁要求）**

```powershell
uv run python -m sim.content.build_height_map --check > logs\hm.log 2>&1; echo "EXIT:$?"
uv run python -m sim.content.build_block_atlas --check > logs\atlas.log 2>&1; echo "EXIT:$?"
```

Expected: 两个 `EXIT:0`（逐字节一致）。

- [ ] **Step 4: 把实测读数写进 spec**

`docs/arch/world-liveliness-design.md` §6.2 的 A 与 B1 小节填实测数字（**只填读数，不改设计结论**）。

- [ ] **Step 5: Commit**

```bash
git add docs/arch/world-liveliness-design.md
git commit -m "docs: record main-tree gate readings for A/B1/B4"
```

---

## 给 codex 的派单（不在本计划执行）

B2 与 B3 走 `.orca/talking.txt`。派单时带 spec §4.2 / §4.3 全文与 §8 陷阱 #16-#24。三条最易踩的已在 talking.txt 的「六条提醒」里，**不要重复扩写**。

## Self-Review 记录

**1. Spec 覆盖**
- §3（A）→ Task 1、2、3b、3、4、5、6。
- §4.1（B1）→ Task 7（代码侧三处）、Task 8（叙事层抑制）。
- §4.4（B4）→ Task 9。
- §4.2 / §4.3 → 明确划给 codex，不属本计划。
- §9 三条裁定 → Global Constraints + Task 9 的 `known_silent` 清单。

**2. 已修正的自检问题**（初稿的错误，留档防复发）
- `frameOf(gid)` 硬编 140 列 → 与 `sampleTileColor` 的「从图像宽度算」不一致，会造成顶面偏移一格（spec §3.1 警告的正是这个）。**已改为 `frameOf(gid, source)` 从源图尺寸推导。**
- Task 2 初稿的测试**恒真**（原色与编辑色必然不同，无 `edited` 也会重绘）。**已改为 gid=0 + 高度 3 编辑**——`EDIT_COLORS[3] === FALLBACK_COLOR === 0x6b4f2a`，颜色不变、只有 `edited` 翻转。
- 初稿完全没提既有测试的破坏面。**已新增「会打红」表 + Task 3b**（给 `rasterContext` 实现真 `drawImage`，否则两条逐像素等价测试退化成恒真）。

**3. 类型一致**
`frameOf` / `paintTile`（Task 1 定义，Task 3/4 引用，签名未变）；`SurfaceCell.edited`（Task 2 定义，Task 3 用）；`IsoTerrain.sourceImage/sourceSize`（Task 3 定义，Task 4 用）；`BlockView.side/top`（Task 4 定义并使用）；`NarratedCache.remember/clear`（Task 8 定义并使用）。

**4. Review Focus 五条**各自落到 Task 3（#1 #2 #3）、Task 2（#4）、Task 5（#5），均有对应测试。

**5. 比例**：计划 966 行，spec 831 行——略多于 spec，因为其中约 400 行是**测试代码**（TDD 要求测试可逐字执行）。实现步骤多为签名 + 要点，未替实现者写完整函数体。
