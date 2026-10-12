# GOD 地图包 / 角色包素材利用方案（专项 · 含授权与兼容核验）

> 上游文档：`docs/arch/god-reuse-analysis.md`（整体分析）。本文聚焦用户指定的目标：**利用 GOD 的地图包与角色包素材**。
> 核验日期：2026-10-12（本地两包 + 公开站扩展包两包实测）。所有授权结论均基于本地文件实证（ATTRIBUTION.md / Read Me.txt / LICENSE 原文），非推测。

---

## 1. 素材全景（本地两包逐目录盘点 + 公开站扩展包实测）

### 1.1 the_ville 包（复制自斯坦福 Generative Agents）

| 目录 | 内容 | 体积 | 授权实证 | 判定 |
|---|---|---|---|---|
| `visuals/map_assets/v1/` | interiors_pt1-5.png + Room_Builder_32x32.png（室内/房间构建 tileset） | 共 ~3.5MB | ATTRIBUTION 归属 **LimeZu**（Modern Interiors，免费版惯例为 CC BY 4.0，**需到 itch 页核对**） | ⚠️ 二档：核验后可用 |
| `visuals/map_assets/cute_rpg_word_VXAce/` | CuteRPG Desert/Field/Forest/Harbor/Mountains/Village ×9 | 共 ~180KB | **Read Me.txt 自证为 PixyMoon 付费 itch 包**（"thank you for purchasing my assets"） | 🔴 **不可用**：付费包素材，本项目未购买；GOD 公开再分发本身即存疑 |
| `visuals/map_assets/blocks/` | blocks_1-3.png（交互/碰撞块） | ~13KB | 同上随包 | 🔴 随 CuteRPG 不可用 |
| `characters/` | 25 张角色 spritesheet + atlas.json | 每张 4-6KB | ATTRIBUTION 混合归属 **PixyMoon / LimeZu / pipohi**，逐张来源无法区分；PixyMoon 部分可能源自同一付费包 | ⚠️/🔴 二档偏险：逐张核验成本高，性价比低 |
| `visuals/the_ville_jan7.json` | Tiled 地图（引用上述 tileset） | — | 地图结构本身无版权问题，但依赖的 tileset 授权混杂 | ⚠️ 仅结构可参考 |

### 1.2 PKU 包（GOD 作者自产，imagegen 生成）

| 目录 | 内容 | 体积 | 授权实证 | 判定 |
|---|---|---|---|---|
| `map_assets/pku_generated/` | pku_full_map_tileset.png（高精度校园渲染切片） | 5.2MB | ATTRIBUTION 明示 **package-local imagegen 生成**，不含官方地图图像 | ✅ 一档：Apache-2.0 |
| `map_assets/cute_rpg_word_VXAce/` | 生成版外观 tileset ×9（命名/尺寸对齐 the_ville） | 每张 ~450KB | README 明示 "**generated** PKU exterior tilesets"（名字沿用但内容是生成的） | ✅ 一档：Apache-2.0 |
| `map_assets/v1/` | 生成版室内/Room Builder tileset ×6 | 共 ~6MB | README 明示 generated | ✅ 一档：Apache-2.0 |
| `map_assets/blocks/` | 生成版交互块 ×3 | ~6KB | 同上 | ✅ 一档：Apache-2.0 |
| `characters/PKU_Agent_01-18.png` | **18 张通用角色 spritesheet**（32px，atlas.json 配套） | 每张 ~几 KB | ATTRIBUTION 明示 "generated 32px spritesheets" | ✅ 一档：Apache-2.0 |
| `characters/PKU_Agent_19-21`（Trump/Musk/黄仁勋） | 名人 sprite ×3 | — | 生成但涉肖像 | 🔴 不适用：肖像权 + 临河镇世界观不需要 |
| `visuals/map.json` | 140×100 Tiled 地图 | 2.8MB | 生成 | ✅ 一档（但整图引入价值低，见 §3） |

**关键结论**：PKU 包虽然名字蹭 the_ville 的目录结构，但**内容全部是 GOD 作者 AI 生成的原创素材**，随 Apache-2.0 仓库分发——这才是「可用素材」的主体。the_ville 包反而大部分不可用或需逐文件核验。

### 1.3 公开站扩展包（★ 2026-10-12 补充核验，素材价值反超本地两包）

公开站 `https://xiaoluolyg.github.io/GOD/map-packs/` 共 **10 个地图包**，比本地仓库多 8 个，全部经 GitHub Releases（`public-site-packs` tag）以 ZIP 分发。其中两个与临河镇世界观高度契合，已下载实测（`%TEMP%\god-packs\`）：

#### 桃花源 Online（taohuayuan-online）——**与临河镇匹配度最高的包**

| 项 | 实测 |
|---|---|
| 题材 | 古风中国村落：祠堂、染坊市集、梯田、溪桥、书塾、祖屋、客栈院落 |
| 角色 | **12 张村民 sprite（96×128，约 32×32 帧 × 4 向行走）**：村长/织染匠/返乡青年/民俗学者/守旧老农/游客/平台运营等 |
| tileset | `tileset-0.png` ~19.8MB（4480 级别大幅面，古风村落全套瓦片） |
| 地图 | 140×100 Tiled @32px + 10 张场景插画卡（`location-assets/`，每张 ~50KB） |
| 授权 | 包内无第三方归属文件；随 Apache-2.0 仓库 Releases 分发；角色全为虚构村民（无肖像权问题） |
| 判定 | ✅ **一档首选**：织染匠/村长/老农的着装与临河镇「药铺/零工/村民」社会构成直接对口 |

#### 空城门开之后（empty-city-gate）

| 项 | 实测 |
|---|---|
| 题材 | 三国空城计：完整中国古城池（瓮城/垛口/重檐歇山顶），城外魏军营地 |
| 角色 | **13 张 sprite（96×128）**：诸葛亮/司马懿/姜维（历史人物，无肖像权）+ 老军侯/魏斥候/传令兵/死守队长/伤兵/粮仓管事/织布妇/隐蔽鼓手/主和士绅 |
| tileset | `tileset-0.png` ~20.6MB，城墙体系完整（转角/垛口/敌楼模块化好） |
| 地图 | 140×100 Tiled @32px + 10 张场景插画卡 |
| 判定 | ✅ 一档：军事元素对临河镇非必需，但**城墙/城门瓦片与平民角色（织布妇/粮仓管事/传令兵）可摘用** |

#### 其余 6 个扩展包（未下载，仅登记）

Fuji Ashfall Town（富士山灰灾小镇）/ Gaokao Blackout（高考停电）/ Hogwarts Parent Meeting（霍格沃茨家长会）/ Idol Rift Variety Studio（综艺摄影棚）/ Lunar Condo（月面公寓）/ Sunblade Palace（鬼灭风宫殿）——题材均与临河镇世界观不符，**不引入**；但其存在证明 GOD 作者持续按此「生成式素材包」模式产出，未来若出古风市集/水乡题材包可直接复用本方案路径。

#### 对 §1.1/§1.2 结论的修正

**公开站扩展包的素材价值反超本地两个包**：桃花源 + 空城计合计 **25 张古风中国角色 sprite**（vs PKU 的 18 张现代学生装），美学上与临河镇「药铺学徒/古风小镇」直接同频——此前「PKU 生成素材为第一档主体」的结论应修订为：**古风两包为一档首选，PKU 退为补充（现代装角色对临河镇世界观不符，基本不采用）**。

## 2. 兼容性核验（临河镇侧）

| 维度 | 临河镇现状（实证） | GOD 素材 | 差异与解法 |
|---|---|---|---|
| tile 尺寸 | `TILE = 16`（WorldScene.ts:21） | 32px（两包一致） | **2 倍差**。解法二选一：甲=素材缩半入库（16px，AI 生成素材缩半通常可接受）；乙=项目整体升 32px（调色板/地图/主角/村民全链重制，工程量大） |
| 人物帧 | 16×32（头身比，2026-10-12 刚修过「有头没身」） | 32×32（GOD atlas 标准帧） | 帧尺寸与比例都不同。PKU 角色缩半为 16×16 会破坏临河镇 16×32 头身惯例；**建议维持村民现渲染，PKU 角色仅作外观多样性参考或按 16×32 重切** |
| 精灵格式 | 自定义 `SheetGeometry`（线性帧号，actors.ts） | 标准 Phaser atlas JSON（frames 数组 + frame/anchor） | GOD 格式是 Phaser 原生 atlas，接入反而更标准；在 content 管线加一个 atlas→SheetGeometry 适配即可，前端零改动 |
| 调色板管线 | `build_palette.py` 单一真相源（sprout-palette.json），改素材必须走管线 | — | 新素材**必须走同一管线**登记，禁止手撒 PNG 进 `client/public/assets/` |
| 素材清单 | `sim/content/README.md` 仅 1 行（Zelda-like CC0） | — | 新增行登记：来源 / 许可 Apache-2.0 / 署名义务 / 落点 |
| 协议面 | 外观无需出站：villagers.py 确定性名册 → sprite id 确定性映射（纯前端静态映射，零协议变更） | — | 与 C3 无冲突 |

## 3. 接入方案（分档 · 按 §1.3 修订后优先级）

### 第一档：桃花源 + 空城计古风素材（公开站扩展包，建议直接采纳）

1. **古风角色 sprite（桃花源 12 + 空城计平民角色摘用 ≈ 16 张）** → 村民外观分层主体。50 村民确定性轮转（villagers.py 名册哈希映射），解决「全员同皮」且**美学与古风世界观同频**（织染匠/村长/老农/粮仓管事对着临河镇的职业构成）。军事角色（魏斥候/死守队长等）视世界观裁决决定是否入库。
2. **古风 tileset 摘用** → 桃花源的祠堂/染坊/梯田/溪桥瓦片与空城计的城墙/城门体系走 `build_palette.py` 管线扩展，缩半至 16px。收益：替换/补充现有 Zelda-like 西幻瓦片中的古风短板（临河镇现在是西幻混古风）。
3. **场景插画卡（`location-assets/`，20 张）** → 可作为地点面板/加载图等 UI 面（非游戏内俯视面），零管线成本，暂存备选。
4. **整张 Tiled 地图** → 不引入（临河镇有自己的确定性建图与五片区语义）；但 `map_pack.json` 的 `locations + anchor_tile + aliases + interactions` 语义可对照临河镇地标规范（见 god-reuse-analysis B 级）。

### 第二档：PKU 生成素材（退为补充，基本不采用）

- 18 张现代学生装角色与临河镇古风世界观不符，仅在未来「时代混搭」设定出现时再议
- 生成版室内/Room Builder tileset：室内维度仍空白时可回头取用（授权干净，无时效问题）

### 第三档：the_ville 部分素材（核验后可用，默认缓办）

- `v1/` 室内 tileset：LimeZu Modern Interiors 免费版条款核验（itch.io 页面，预期 CC BY 4.0 → 署名可用）
- `characters/` 26 张：混合来源逐张不可分——**建议放弃**，古风两包的 25 张已够第一版分层

### 第四档：明确不引入

- CuteRPG_VXAce 全部（PixyMoon 付费包，Read Me 自证）
- 名人 sprite（肖像权）
- the_ville 整张地图（tileset 授权混杂）
- 公开站其余 6 个题材包（世界观不符）

**署名义务**：Apache-2.0 要求保留版权与许可声明——落点为 `sim/content/README.md` 素材清单新行 + 仓库级 THIRD-PARTY-NOTICES（若引入代码则后者必加；纯素材建议清单行注明即可，从严处理两个都做）。

## 4. 待用户裁决

| # | 决策点 | 选项与建议 |
|---|---|---|
| 1 | 像素规格路线 | **甲（建议）：素材缩半入 16px 管线**——只动 content 管线，前端零改动；乙：全项目升 32px——古风两包 tileset 本就是 32px 高清像素（实测质量足以支撑），若走乙反而零缩放损耗，但要重制 chenmo/villager/调色板/地图全链，建议留到「美术打磨」阶段一并做 |
| 2 | 角色帧规格 | 古风角色为 96×128 sheet（约 32×32 帧 × 4 向）；缩半后 16×16 与临河镇 16×32 头身惯例冲突。甲（建议）：重切/裁切为 16×32（AI 素材上裁下身代价小）；乙：村民整体换 16×16 chibi 风格（改动最小但与主角 16×32 不同帧高，需裁决是否统一） |
| 3 | Apache-2.0 素材是否突破「CC0-only」既有裁定 | 2026-10-05 裁定为 CC0-only（针对 tileset 选型）；Apache-2.0 仅多一条署名义务。**用户本轮意向即视为重新裁定的动议**，确认后请在 `sim/content/README.md` 选型记录处补一行裁决 |
| 4 | 军事角色是否入库 | 空城计 13 张中约 6 张为军事角色（斥候/校尉/鼓手等）；临河镇无军事面，建议只摘平民角色（织布妇/粮仓管事/传令兵/老军侯/主和士绅），军事角色弃用 |
| 5 | 室内 tileset 引入时机 | 现在只入外观面角色分层（最小步）；室内面等「建筑可进入」玩法立项时再入 |

## 5. 合规红线（一句话版）

- 用桃花源/空城计/PKU 生成素材：保留 Apache-2.0 署名（素材清单 + 通知文件），合规；包内无第三方归属文件，历史人物（诸葛亮等）无肖像权问题
- 用 the_ville 任何素材前：必须先核验 LimeZu/pipohi 上游条款，PixyMoon 名下内容一律视为未购买不可用
- CuteRPG 目录：无论如何不碰
- 扩展包 zip 不入仓库（保持精瘦）：下载源为 `github.com/XiaoLuoLYG/GOD/releases` tag `public-site-packs`，content 管线应记录可重建下载脚本（同 Zelda-like 惯例）
