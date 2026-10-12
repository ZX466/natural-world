# GOD 可利用部分分析与冲突核验（外部项目调研 · 只读结论）

> 调研对象：`D:\压缩包\GOD\GOD`（GOD · Govern · Observe · Direct，EMNLP 2026 System Demonstrations 录用）
> 调研日期：2026-10-12。本文为**分析与核验记录**，不含实施计划；按 DESIGN §18，列入条目属于「MVP 后清单」候选，不回写里程碑。
> 结论速览：**A级（静态回放导出）无架构冲突、可直接排期；B级（the_ville 素材）与既有素材裁定冲突，默认不引入；C/D 级为 M6 后候选。**

---

## 1. 来源项目定位

| 项 | 事实 |
|---|---|
| 是什么 | agent 社会仿真的「上帝控制台」：回放运行、暂停时间、向任意居民发问（/ask）、干预下一步（/intervene）、导出可复现实验包 |
| 构成 | `agentsociety2`（step 循环仿真框架 + FastAPI 后端 + React 控制台）+ `jiuwenclaw`（华为 MaaS 助理框架，与本调研无关）+ SQLite replay store |
| 学术背景 | EMNLP 2026 System Demonstrations 录用 |
| 许可证 | 主仓 / agentsociety / jiuwenclaw 三处均为 **Apache-2.0** |
| 与临河镇关系 | 定位不同（研究检查工具 vs 沉浸游戏），技术栈同构（FastAPI + React + 像素小镇 + OpenAI 协议）；临河镇缺的回放分享与实验组织恰是 GOD 最强项 |

## 2. 可利用部分清单

### A 级：静态回放导出（浏览器打开即看，无安装无 key）

**GOD 做法**：`agentsociety2/backend/services/public_replay_export.py` 把一次运行从 SQLite 导出为静态 JSON + 素材目录，GitHub Pages 托管；前端 `PixelReplay` 页面纯静态渲染时间轴、地图、agent 状态、操作员命令记录。

**临河镇落点**：
- 长跑验收的呈现：真实 20 差事长局（当前头号待办）跑完 → 导出 → 人工回看审查
- T5 golden 宏观断言可配可视化回放；T4 探针轮对话取证
- 分享用：「陈默的一天」一个链接

**实施形态**（若立项）：`sim/tools/export_replay.py` 导出器 + 复用临河镇现有 Phaser 场景做只读回放模式。数据源是**事件日志重放**（C4 天然支持），不是运行时抓帧。

### B 级：地图包格式与像素素材

**GOD 做法**：`custom/maps/<map_id>/` 文件夹 = `map.yaml`（locations + anchor_tile + aliases + spawn_points）+ Tiled JSON + 角色图集；自动发现热插拔。随仓带 the_ville（斯坦福 Generative Agents 经典小镇）与 PKU 校园图。

**可取点**：
- `map.yaml` 的 `aliases` 语义（"home"/"house"/"住所" 同义指代）对 NPC 语言理解与 prompt 地标指代有参考价值——仅格式思想，非素材
- the_ville 的 25 个角色 sprite 图集（见 §3 冲突核验，**默认不引入**）

### C 级：/ask 定向提问交互（M6 候选）

**GOD 做法**：命令输入器 `/ask @Name #id` 向某 agent、群组或全镇提问，live 与 replay 均可。

**临河镇落点**：玩家点击村民提问 → 该 NPC 经 LOD 升格 L2 → LLM 第一人称回答（受自身知识边界约束，只说亲眼见过的事）→ 30 游戏秒后降格写回记忆。比 GOD 更符合世界真实性（回答被信息边界约束）。与念头注入不冲突：念头只通主角，/ask 对象是 NPC。

### D 级：实验包目录约定（不排期，仅备档）

`quick_experiments/<hypothesis>/<experiment>/` + ZIP 导入导出。对未来 L3 层验收（LLM 裁判/人类盲测）是成熟组织方式，等盲测需求出现再议。

## 3. 冲突核验（逐条实证）

| # | 核验点 | 核验方式 | 结论 |
|---|---|---|---|
| 1 | **回放导出 vs C3 零元信息** | GOD 导出格式直接暴露 step/seq/agent 内部字段；临河镇 `outbound_guard.py` 的 `assert_outbound_clean` / `strip_outbound_forbidden` 为独立纯函数（ws.py 咽喉闸之外可直接调用） | **有冲突，可解**：导出器必须复用 outbound 投影，只导出叙事化帧（玩家视角所见）；导出格式不进 WS 协议版本管理（独立静态面），但出站口径与协议面同源 |
| 2 | **回放数据量 vs 60 tick/秒** | GOD 为 step 粒度（低频）；临河镇 tick 粒度全量导出不可行 | **有冲突，可解**：事件驱动关键帧 + 前端位置插值（`world-mirror.ts` 平滑逻辑可参考） |
| 3 | **the_ville 素材 vs 既有素材裁定** | the_ville `ATTRIBUTION.md`：素材复制自斯坦福 Generative Agents（PixyMoon / LimeZu / pipohi 归属，**非 CC0**，上游授权无法本地核验）；而临河镇 `build_palette.py` 头注明载用户已裁定 **CC0-only**（Sprout Lands 因「仅非商用」被裁掉换 CC0 直链包） | **🔴 直接冲突：默认不引入**。引入非 CC0 素材违反既有裁定，除非用户显式重新裁定并接受署名/授权核验义务 |
| 4 | **/ask vs 念头注入设计** | 念头注入是「玩家=直觉、只通主角」；/ask 对象是 NPC，走 LOD 升降格 | **无冲突**，但属玩法增量（M6），不进当前验收阶段 |
| 5 | **/intervene 干预机制** | GOD 的干预是上帝指令直改下一步 | **🔴 设计冲突：明确不引入**。与「玩家只是直觉」核心设计相悖（DESIGN §9/§10） |
| 6 | **agentsociety2 框架本体** | 松散 step 循环，无事件溯源、无确定性、无出站闸 | **🔴 架构冲突：不引入**。移植等于降级临河镇地基 |
| 7 | **DESIGN §18 冻结基线** | DESIGN.md L495：新想法先进「MVP 后清单」，不回写里程碑 | **本文档遵守**：全文为分析与核验记录，不构成里程碑变更；A级若采纳，属于验收深度阶段的工具项而非里程碑内容 |
| 8 | **Apache-2.0 引入义务** | 三处 LICENSE 均 Apache-2.0；临河镇 License 未定（私有） | **合规可解**：A 级导出器为全新实现（数据源不同：事件日志 vs step 帧），只借交互思路不抄代码则无义务；若日后抄任何代码段，需保留版权与许可声明 |

## 4. 待用户裁决项

| # | 事项 | 建议 |
|---|---|---|
| 1 | A 级静态回放导出是否立项 | 建议采纳：无架构冲突，正中验收深度阶段（长跑验收呈现）需求 |
| 2 | B 级 the_ville 素材引入 | 建议默认**不引入**（与 CC0-only 裁定冲突）；若要引入需先核验 PixyMoon/LimeZu 上游授权并接受署名义务 |
| 3 | `map.yaml` aliases 语义是否吸收进 `sim/content/` 地标规范 | 可选、零成本（纯格式思想，不涉授权），建议 M6 内容阶段顺手做 |

## 5. 合规备忘

- 只借鉴交互思路（静态回放、/ask、地图包组织）：无版权义务
- 引入 Apache-2.0 代码段：需保留原版权与许可声明
- the_ville 素材：上游为 Generative Agents 项目素材（PixyMoon/LimeZu/pipohi），历史授权偏研究用途，商用发布前必须逐项核验
