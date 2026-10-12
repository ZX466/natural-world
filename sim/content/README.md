# sim/content — 内容管线

DESIGN.md §5：地图源文件 / 素材清单 / 地标命名规范。

## 素材清单（DESIGN §20「M0 就列素材清单」兑现）

| 包 | 来源 | 许可 | 落点 | 登记日期 |
|---|---|---|---|---|
| Zelda-like tilesets and sprites | [ArMM1998 @ OpenGameArt](https://opengameart.org/content/zelda-like-tilesets-and-sprites) | **CC0**（公有领域，零限制，商用/署名均无需） | 原件 `assets/zelda-like/pkg/`（不入库，CC0 允许但保持仓库精瘦；下载脚本可重建）；运行时副本 `client/public/assets/`（入库） | 2026-10-05 |
| GOD 古风角色（桃花源 12 + 空城计平民 5） | [GOD](https://github.com/XiaoLuoLYG/GOD)（Apache-2.0，AI 生成） | **Apache-2.0**（署名义务已落 `THIRD-PARTY-NOTICES.md`） | 原件 `assets/god-packs/`（不入库可重建）；运行时副本 `client/public/assets/sprites/god_villager_*.png` 17 张（`build_god_characters.py` 生成） | 2026-10-12 |

> **2026-10-12 裁决记录（D1–D5，用户逐项拍板）**：D1=甲 素材缩半入 16px 管线；
> D2=甲 角色重切 16×32；D3=**采纳 Apache-2.0 突破 2026-10-05「CC0-only」裁定**
> （仅多署名义务，落点如上）；D4=只摘空城计平民 5 张，军事/名人不入库；
> D5=先入外观面角色分层（本次），古风 tileset 摘用与室内面待后续批次。
> 完整裁决链见 `docs/data/god-reuse-final.md` §5。

> 选型记录：原计划用 Sprout Lands（Cup Nooble，itch.io）——免费版仅限非商用且需人工购买页操作；
> 用户裁定换**完全 CC0、可脚本直链**的 Zelda-like 包。调色板/帧布局实测记录见
> `build_palette.py` 模块注释。

## 管线

- `build_palette.py`：从素材包生成运行时副本 + `client/public/assets/tilesets/sprout-palette.json`
  （调色板单一真相源，R5）。**改素材/加地形跑这里，勿手改调色板**。
- `build_town.py`：读调色板生成 48×48 小镇图 `linhe-town.json`（内部格式，
  `TileMap.from_json_file` 可加载；确定性可 diff）。
- 地标命名：戏内表达（禁止元信息词汇，§19）。
