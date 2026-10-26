# sim/content — 内容管线

DESIGN.md §5：地图源文件 / 素材清单 / 地标命名规范。

## 素材清单（DESIGN §20「M0 就列素材清单」兑现）

| 包 | 来源 | 许可 | 落点 | 登记日期 |
|---|---|---|---|---|
| Zelda-like tilesets and sprites | [ArMM1998 @ OpenGameArt](https://opengameart.org/content/zelda-like-tilesets-and-sprites) | **CC0**（公有领域，零限制，商用/署名均无需） | **2026-10-26 退役**：运行时副本（`actors/chenmo.png`、`actors/villager.png`）仍在使用，但生成脚本 `build_palette.py` 已删除，原件与布局记录见 git 历史 | 2026-10-05 |
| GOD 古风角色（桃花源 12 + 空城计平民 5） | [GOD](https://github.com/XiaoLuoLYG/GOD)（Apache-2.0，AI 生成） | **Apache-2.0**（署名义务已落 `THIRD-PARTY-NOTICES.md`） | 原件 `assets/god-packs/`（不入库可重建）；运行时副本 `client/public/assets/sprites/god_villager_*.png` 17 张（`build_god_characters.py` 生成） | 2026-10-12 |
| 临河镇等距方块图集 | `build_block_atlas.py` 程序化生成；颜色采样既有 GOD 桃花源图 | 无新增外部素材或许可；既有 GOD 素材声明不变 | `client/public/assets/tilesets/linhe-block-atlas.png` + 同名 JSON；四高度档 × 三面 16×16 纹理 | 2026-10-23 |

> **2026-10-12 裁决记录（D1–D5，用户逐项拍板）**：D1=甲 素材缩半入 16px 管线；
> D2=甲 角色重切 16×32；D3=**采纳 Apache-2.0 突破 2026-10-05「CC0-only」裁定**
> （仅多署名义务，落点如上）；D4=只摘空城计平民 5 张，军事/名人不入库；
> D5=先入外观面角色分层（本次），古风 tileset 摘用与室内面待后续批次。
> 完整裁决链见 `docs/data/god-reuse-final.md` §5。

> 选型记录：原计划用 Sprout Lands（Cup Nooble，itch.io）——免费版仅限非商用且需人工购买页操作；
> 用户裁定换**完全 CC0、可脚本直链**的 Zelda-like 包。该包的角色帧布局实测记录见
> git 历史中的 `build_palette.py`（2026-10-26 随旧图管线删除）。

## 管线

现行管线（按执行顺序）：

- `build_god_town.py`：从 GOD 桃花源原件生成整图 `linhe-town.json`（140×100，内部格式）
  与 `client/public/assets/tilesets/god-town-16.png`。**改地图跑这里**，确定性可 diff。
- `build_height_map.py`：从入库地图与图集生成等距高度表 `linhe-height.json`；
  `--check` 逐字节对照已提交产物。
- `build_block_atlas.py`：仅从入库的 `god-town-16.png` 与 `linhe-town.json` 按 ground gid
  采中心 4×4 均色，生成四高度档/三面方块图集；前端以共享遮罩加逐格 tint 保留色差。
  运行 `uv run python -m sim.content.build_block_atlas`；`--check` 两次临时重建并逐字节
  对照 PNG/JSON，禁止随机数与时间戳。
- `build_god_characters.py`：从 GOD 角色包切片生成 `client/public/assets/sprites/god_villager_*.png`。
- `png_codec.py`：以上脚本共用的零依赖 PNG 编解码（zlib+struct）。

已退役：旧 Zelda-like 地图管线（`build_town.py`、`build_palette.py` 与 `sprout-*.{json,png}`）
于 2026-10-26 删除，D10 已将其退休出运行时；完整实现可从 git 历史找回。
地标命名：戏内表达（禁止元信息词汇，§19）。
