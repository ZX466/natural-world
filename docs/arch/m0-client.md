# M0 前端渲染闭环设计（TASK-C02）

> 依据 DESIGN.md（v2.1）§3 架构、§4 技术栈、§5 目录、§10 界面双层铁律。
> 范围：M0 的 `client/`——Phaser 瓦片地图渲染 + 摄像机 + 角色精灵 + React 覆盖层桥接。
> 不涉及：LLM 独白/思维面板（M1+）、念头注入 UI（M4）、出戏边界字段清单（kilo/codex）——M0 前端只做「世界可见的壳」。

---

## 0. M0 前端目标

交付一条**端到端渲染闭环**：sim 的世界状态经 WS → client → Phaser 画出地图和能走动的角色，React 画出壳 UI（时钟/倍速/连接状态）。验证的是「世界状态 → 像素」这条链路，为后面所有表现层（独白气泡、弹幕、光照）打底。

铁律（DESIGN §10 + §4 硬约束）：
- **Phaser 只画 canvas 内的世界，React 只画 canvas 外的 UI，不共享 DOM。** 两边唯一的桥是 Zustand store。
- 前端永不渲染戏外信息（tick 序号、seed、entity 内部 id、世界真相）——M0 就立规矩，后面不会破。

---

## 1. 总体结构

```
┌─ React 壳（canvas 外）────────────────────────┐
│  <TopBar/>  时钟 · 倍速 · 连接状态              │
│  <CanvasHost/>  ← Phaser 挂载点（唯一 DOM 交界） │
│  <PanelHost/> M1+ 思维面板/计划看板（占位，M0 空）│
└────────────────────────────────────────────────┘
              ▲ Zustand store（唯一桥）
┌─ Phaser 世界（canvas 内）──────────────────────┐
│  WorldScene: tilemap 渲染 / 精灵 / 摄像机 / 光照 │
└────────────────────────────────────────────────┘
```

- `CanvasHost` 是一个 `<div ref>`，Phaser `new Game({ parent: ref })` 挂进去。这是 React 与 Phaser 唯一的 DOM 交接点，之后各管各。
- React 与 Phaser **不互相 import 组件**；通信只经 store（React→Phaser 的控制指令）和事件总线（Phaser→React 的世界状态摘要）。

---

## 2. client/src 结构（对齐 §5）

```
client/src/
├─ game/            # Phaser 侧
│  ├─ main.ts       # new Phaser.Game(config)，parent=CanvasHost div
│  ├─ scenes/
│  │  ├─ BootScene.ts    # 加载 tilemap JSON + tileset + 精灵表
│  │  └─ WorldScene.ts   # 主场景：地图/精灵/摄像机/输入转发
│  ├─ render/
│  │  ├─ tilemap.ts      # 地图层渲染与碰撞调试层（dev）
│  │  ├─ entities.ts     # 实体精灵管理（pool，避免每帧 new）
│  │  └─ camera.ts       # 摄像机控制
│  └─ lighting.ts        # M0 简单昼夜调光（读 store 的 phase_of_day）
├─ ui/              # React 侧
│  ├─ App.tsx
│  ├─ TopBar.tsx    # 时钟(戏内时间)/倍速按钮/连接状态点
│  ├─ CanvasHost.tsx
│  └─ PanelHost.tsx # M0 占位空
├─ net/
│  ├─ ws.ts         # WS 客户端：连接/重连/消息分发
│  └─ protocol.ts   # re-export shared/protocol.ts（自动生成，不手写）
└─ store/
   ├─ worldStore.ts  # 世界状态摘要（实体位置、戏内时间、光照相位）
   └─ uiStore.ts     # UI 状态（倍速、暂停、选中实体）
```

---

## 3. 渲染闭环数据流

```
sim tick loop
   │  state_delta（每 tick 增量，kilo 协议）
   ▼ WS
net/ws.ts  ──► worldStore.ingest(delta)   # 应用增量到本地世界镜像
   │                                          │
   ├─► game/render/entities.ts               │（Phaser 每帧读镜像画精灵）
   │                                          │
   └─► uiStore（戏内时间/相位等 UI 关心字段）──► React TopBar
```

**要点**：
- client 维护一份**世界镜像**（只读视图），WS 增量进来就合并。Phaser 渲染和 React UI 都从镜像读，不各自连 WS。
- 实体精灵用**对象池**：`entities.ts` 按 entity_id 维护 sprite 池，delta 说出现就取、消失就还，移动就插值——避免每帧创建销毁（元气骑士式流畅感的底层）。
- **插值**：sim 是 tick 驱动（60/s），Phaser 是 rAF（通常 60fps 但不同步）。精灵位置在相邻两个 tick 快照间线性插值，消除步进感。M0 只有匀速移动，线性插值足够。

---

## 4. Phaser 侧设计

### 4.1 BootScene
- 加载 Tiled 导出的 tilemap JSON + tileset 图片 + 角色精灵表（M0 占位素材）。
- 加载完成 → 启动 WorldScene。

### 4.2 WorldScene
- **地图**：`this.make.tilemap()`，按层渲染（ground / 碰撞调试层默认隐藏 / 实体层）。碰撞层仅供 dev 可视化，不进正式渲染。
- **实体**：`render/entities.ts` 从 worldStore 读实体列表，池化 sprite 同步位置。M0 一个可操控角色（陈默）+ 若干静态占位 NPC。
- **摄像机**：`cameras.main` 跟随主角；`setBounds` 限制在地图内；支持缩放（元气骑士俯视调性，M0 固定 2x 像素缩放）。
- **输入**：M0 极简——点击地图 → 发 `move_intent` 到 sim（经 WS），**路径由 sim 的 A\* 算**，前端不寻路（世界真相在 sim，前端只是视图，对齐 C1 双域分离的雏形）。
- **光照**：`lighting.ts` 读 store 的 `phase_of_day`，叠加一层昼夜调色（M0 用全屏半透明色罩即可，元气骑士式点光源/弹幕光照后置 M4+）。

### 4.3 不做什么（M0 边界）
- 不做独白气泡/思维面板（M1）。
- 不做弹幕/受击表现（M4 战斗）。
- 不做区块迷雾渲染（M3）。
- 不做点光源光照（M4+，M0 全屏色罩代替）。

---

## 5. React 侧设计

### 5.1 TopBar（M0 唯一真 UI）
- **戏内时间**：来自 store 的 `game_time`（HH:MM + 第几天 + 集市日标记），**绝不显示 tick**（C3 界面双层铁律，M0 就立住）。
- **倍速控制**：暂停 / 1x / 4x / 16x 按钮 → 发 `control` 消息到 sim（kilo 协议）。
- **连接状态**：绿/黄/红点（WS connected / reconnecting / disconnected）。

### 5.2 PanelHost
- M0 空壳占位，只定挂载位置和布局约束（右侧栏），M1 思维面板、M4 计划看板往里填。现在放空是为了让布局骨架 M0 定型，后面只填内容不改结构。

### 5.3 uiStore vs worldStore 分离
- `worldStore`：世界状态镜像（实体、时间、光照相位）。数据来自 sim，只读。
- `uiStore`：纯前端 UI 状态（当前倍速、暂停、选中实体、面板开合）。数据来自用户操作。
- 分开是为了：**世界状态的变化永不直接驱动 UI 重渲染整棵树**——React 只订阅它关心的少数字段（Zustand selector），Phaser 的高频更新完全绕开 React。

---

## 6. 性能与边界（呼应 pi 的预算）

| 关注点 | M0 对策 |
|---|---|
| 高频 tick 更新打爆 React | 世界镜像进 worldStore，React 只 selector 订阅低频字段（时间/相位/连接态）；实体位置更新不进 React 树 |
| 精灵创建销毁开销 | 对象池（§3） |
| WS 每 tick 全量太大 | 只发增量 state_delta（kilo 定格式）；M0 50 实体增量很小 |
| 60fps 渲染 vs 60tick/s 模拟 | rAF 与 tick 解耦 + 位置插值（§3） |

---

## 7. M0 前端验收映射

| 验收 | 由哪部分保证 |
|---|---|
| 可走动（看到角色在地图上移动） | WorldScene 精灵同步 + 插值 + 点击寻路 |
| 界面双层铁律（C3） | TopBar 只显示戏内时间，无 tick/seed/id；戏外调试层默认关 |
| Phaser/React 不共享 DOM | CanvasHost 唯一交界 + store 唯一桥 |
| 元气骑士调性雏形 | 俯视瓦片 + 2x 像素缩放 + 昼夜色罩 |

---

## 8. 依赖声明

| 依赖 | 提供方 | 我需要什么 |
|---|---|---|
| client 骨架 + 依赖锁定 | cline TASK-001 | Vite+Phaser+React+Zustand+Tailwind 的 `client/` 可运行骨架 |
| WS 消息格式 | kilo TASK-001 | `state_delta` / `move_intent` / `control` 的字段 schema 与 `shared/protocol.ts` 生成物 |
| 协议类型 | kilo TASK-001 | openapi-typescript 生成的 TS 类型（`net/protocol.ts` re-export） |
| 实体/时间的戏内表达 | kilo + codex | 协议层「前端可见字段白名单」，确保不泄 tick/seed/id |

**边界**：本文不定 WS 消息字段（kilo）、不定后端怎么算 state_delta（sim 内核 m0-core.md §5.1）、不定戏内字段白名单（codex 安全清单）——只声明前端要消费的形状。

---

## 9. 开放问题（提交评审）

1. 世界镜像放 Zustand 还是独立类？Zustand 方便 React 订阅，但 Phaser 高频读可能想要更轻的普通对象。倾向：镜像用普通 TS 类 + 一个薄 Zustand 适配层只暴露 UI 低频字段。评审裁决。
2. M0 点击寻路：点击地图坐标 → sim 算路径 → 角色走。是否允许前端做「目标点合法性预检」（点在碰撞层上直接不可点）？涉及世界真相是否下发碰撞层。倾向下发只读碰撞层（反正玩家看得见墙），评审裁决。
3. 摄像机跟随 vs 自由漫游：M0 先跟随主角；自由漫游（拖动看全图）是否 M0 就要？倾向 M0 只做跟随，漫游后置。评审裁决。
