# sim/content — 内容管线

DESIGN.md §5：地图源文件 / 素材清单 / 地标命名规范。

## 素材清单（DESIGN §20「M0 就列素材清单」兑现）

| 包 | 来源 | 许可 | 落点 | 登记日期 |
|---|---|---|---|---|
| Zelda-like tilesets and sprites | [ArMM1998 @ OpenGameArt](https://opengameart.org/content/zelda-like-tilesets-and-sprites) | **CC0**（公有领域，零限制，商用/署名均无需） | 原件 `assets/zelda-like/pkg/`（不入库，CC0 允许但保持仓库精瘦；下载脚本可重建）；运行时副本 `client/public/assets/`（入库） | 2026-10-05 |

> 选型记录：原计划用 Sprout Lands（Cup Nooble，itch.io）——免费版仅限非商用且需人工购买页操作；
> 用户裁定换**完全 CC0、可脚本直链**的 Zelda-like 包。调色板/帧布局实测记录见
> `build_palette.py` 模块注释。

## 管线

- `build_palette.py`：从素材包生成运行时副本 + `client/public/assets/tilesets/sprout-palette.json`
  （调色板单一真相源，R5）。**改素材/加地形跑这里，勿手改调色板**。
- `build_town.py`：读调色板生成 48×48 小镇图 `linhe-town.json`（内部格式，
  `TileMap.from_json_file` 可加载；确定性可 diff）。
- 地标命名：戏内表达（禁止元信息词汇，§19）。
