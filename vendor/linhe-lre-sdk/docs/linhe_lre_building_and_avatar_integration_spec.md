# 《临河镇》3D 分节体素角色 × LRE-DT100 液体火箭试车台地标建筑 · 本地 Agent 嵌入规范

本文档与配套代码模块专为本地 Coding Agent 设计，无需依赖任何外部 `.gltf` / `.png` 静态文件，即可将 **1.8 格 3D 分节体素角色系统（含主角陈默、村民与 17 套古风 NPC）** 与 **LRE-DT100 液体火箭发动机 3D 数字孪生试车台地标建筑（含 24 个精密工业子部件、四阶爆炸拆解、PBR/HOLO/FLIR 三视图及 12 章 180 秒电影导览）** 直接嵌入《临河镇》Three.js 项目。

---

## 一、 直接复制给本地 Coding Agent 的执行指令（Prompt）

请将以下指令直接复制发送给你的本地 Coding Agent：

> **任务指令：将《临河镇》3D 分节体素角色与 LRE-DT100 试车台地标建筑模块嵌入现有 Three.js 游戏工程**
>
> 1. **文件放置**：
>    - 将 `src/characters/linhe_voxel_avatar_3d.js` 与 `src/characters/character_Presets.json` 复制到项目的 `src/characters/` 目录。
>    - 将 `src/buildings/linhe_lre_test_stand_building.js` 复制到项目的 `src/buildings/` 目录。
> 2. **相机与坐标硬约束**：
>    - 保持《临河镇》透视相机规范：`fov = 60°`，方位角 `0–360°` 自由旋转，俯角严格限制在 `3°–80°`，缩放距离严格限制在 `3–24 格`。
>    - 试车台建筑通过 `new LRETestStandBuilding({ tileX: 0, tileZ: -3, groundY: 1.0, scale: 1.0 })` 实例化并挂载到 `scene`。模块内部已将原模型 `-6.05` 的底部地基自动抬升 `+6.05` 归零对齐至 `building.root = (0, 0, 0)`，因此 `groundY: 1.0` 会严丝合缝贴合在高度 1 的土方块顶面上。
> 3. **地形碰撞与寻路注册**：
>    - 调用 `building.getOccupiedTiles()` 获取试车台 `16 × 14 格` 混凝土地基台面（顶面高度 `1.52 格`）的格子坐标，写入地图的 `tileHeightMap`。
>    - 二层维护平台站立点可通过 `building.getPlatformStandPoint('left' | 'right')` 获取（世界高度 `8.65 格`）。
> 4. **替换 2D Billboard 角色为 1.8 格 3D 分节体素模型**：
>    - 使用 `new VoxelAvatar3D({ presetId: 'chenmo', x: 0, y: 1.0, z: 6.0 })` 创建主角陈默，以及 `god_villager_01 ~ 17` 创建 17 套古风 NPC。
>    - 角色原点严格位于双脚底面中心 `(0, 0, 0)`，站在高度 `H ∈ {1, 2, 3}` 的方块上时直接设置 `avatar.root.position.y = H`。
>    - 旧版 2D 图集行号调用 `legacyRowToFacing(row, isAncientNpc)` 转换为显式 `Facing` 枚举，彻底消除主角与古风 NPC 行序颠倒的朝向 bug。
>    - 头顶名字标签/气泡统一挂载在 `avatar.getTopAnchor()` 返回的世界坐标（即 `脚底 Y + 1.95 格` 并随跳跃重心动态起伏）。
> 5. **主循环与射线交互接入**：
>    - 在 `requestAnimationFrame` 主循环中每帧调用 `building.update(dt, elapsedSec)` 与 `avatar.update(dt)`。
>    - 将 `building.interactiveMeshes` 接入鼠标 `Raycaster`，悬停时设置 `building.hoveredPartId = hit.object.userData.partId` 并调用 `building.applyHighlightStates()`；点击时触发部件聚焦特写与右侧工程档案卡更新。

---

## 二、 核心错误修复说明（对比此前截断代码片段）

在本次导出的正式版模块与预览中，已完成以下 4 项关键修复：

| 问题编号 | 错误现象与原因 | 修复方案 |
| :--- | :--- | :--- |
| **1. 代码截断与语法错误** | 原代码片段首尾存在 `<!-- ... existing code ... -->` 占位符，且 `function buildExternalTestStand() {` 未闭合即跳至文件末尾，触发 `SyntaxError: Unexpected end of input` | 已完整补齐 HTML/FUI 面板、24 个工业子部件建模函数、流光回路、超音速马赫环尾焰、1.8 格体素角色与 12 章导览逻辑，通过 `node --check` 零错误校验 |
| **2. 全息扫描着色器 (`holoMaterial`) 世界高度错位** | 试车台放入《临河镇》后，`worldRoot` 世界中心高度为 `Y = groundY + 6.05 = 7.05`。原代码仅在 `flirMaterial` 中减去了 `7.05`，而 `holoMaterial` 仍直接用世界坐标 `vWorldPos.y - uScanY`，导致全息激光面在地下扫掠 | 在 `LRETestStandBuilding` 中新增动态 Uniform `uWorldCenter`，在 `holoMaterial` 与 `flirMaterial` 中统一使用 `float localY = vWorldPos.y - uWorldCenter.y;`，无论建筑放在地图哪个格子都能精准扫描 |
| **3. 部件特写与 12 章导览运镜坐标未偏移** | 原导览与部件聚焦配置 `PART_CAMERA_PROFILES` / `TOUR_CHAPTERS` 的 `target` 基于原点 `(0,0,0)`，直接赋给《临河镇》相机时镜头会看向地下 `(0, -0.2, 0)` | 统一通过 `worldRoot.localToWorld(target)` 叠加建筑世界中心偏移 `(tileX, groundY + 6.05, tileZ)`，并将相机最低高度限制为 `Y >= 1.25`，杜绝穿地 |
| **4. 富文本不间断空格 (`\u00A0`)** | 缩进中包含大量 `0xA0` 字符，部分严格打包器（Vite/Webpack）会报错 | 已全部清理并替换为标准 ASCII 空格 (`0x20`) |

---

## 三、 模块接口速查表

### 1. 试车台地标建筑模块 (`src/buildings/linhe_lre_test_stand_building.js`)

```javascript
import {
  LRETestStandBuilding,
  SYSTEMS_CATALOG,
  PARTS_BY_ID,
  PART_CAMERA_PROFILES,
  TOUR_CHAPTERS
} from './buildings/linhe_lre_test_stand_building.js';

// 1. 在《临河镇》北郊 (X=0, Z=-3) 高 1 土块顶面 (Y=1.0) 创建试车台建筑
const testStand = new LRETestStandBuilding({
  tileX: 0,
  tileZ: -3.0,
  groundY: 1.0,
  scale: 1.0
});
scene.add(testStand.root);

// 2. 注册地基碰撞高度到地图
for (const tile of testStand.getOccupiedTiles()) {
  map.setTileHeight(tile.gx, tile.gz, tile.topY);
}

// 3. 切换科学探测视图 ('pbr' | 'holo' | 'flir')
testStand.setViewMode('holo');

// 4. 控制四阶梯爆炸拆解 (0 ~ 100) 与变推力节流 (0.0 ~ 1.15)
testStand.setExplodePercentage(50);
testStand.throttleValue = 1.05;

// 5. 在每帧渲染循环中更新转子自转、TVC 矢量摆动与尾焰水雾粒子
const telemetry = testStand.update(dt, elapsedSeconds);
```

### 2. 1.8 格 3D 分节体素角色模块 (`src/characters/linhe_voxel_avatar_3d.js`)

```javascript
import {
  VoxelAvatar3D,
  Facing,
  legacyRowToFacing,
  getSubTileSlotOffset
} from './characters/linhe_voxel_avatar_3d.js';

// 创建主角陈默（高 1.8 格，带背后立体竹药篓与朱红腰带跳色）
const chenmo = new VoxelAvatar3D({
  presetId: 'chenmo',
  x: 0,
  y: 1.0, // 直接取脚下方块顶面高度 (1.0 / 2.0 / 3.0)
  z: 6.0,
  facing: Facing.NORTH
});
scene.add(chenmo.root);

// 切换动作 ('idle' | 'walk' | 'run' | 'jump')
chenmo.playAnim('run');

// 每帧更新骨骼动画与平滑朝向插值
chenmo.update(dt);

// 获取头顶气泡/名字标签挂点 (Y + 1.95 格)
const bubblePos = chenmo.getTopAnchor();
```

---

## 四、 交付包目录结构 (`linhe_lre_building_and_avatar_sdk.zip`)

```text
linhe_lre_building_and_avatar_sdk/
├── docs/
│   └── linhe_lre_building_and_avatar_integration_spec.md  # 本集成规范文档（含 Agent Prompt）
├── src/
│   ├── buildings/
│   │   └── linhe_lre_test_stand_building.js               # LRE-DT100 试车台 3D 建筑独立 ES Module
│   └── characters/
│       ├── linhe_voxel_avatar_3d.js                       # 1.8 格分节体素人物独立 ES Module
│       └── character_Presets.json                         # 19 套角色（主角+村民+17古风NPC）色板与配件配表
└── previews/
    └── linhe_town_lre_game_preview.html                   # 零依赖单文件完整实机交互预览（可直接双击运行）
```
