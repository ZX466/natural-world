"""build_god_characters.py — GOD 古风角色接入管线（2026-10-12 D1-D5 裁决兑现）。

裁决记录（GOD 素材裁决记录 §5 已归档至 git 历史；2026-10-12 用户逐项拍板）:
- D1=甲 素材缩半入 16px 管线（前端零改动）
- D2=甲 角色重切 16x32（与主角帧高一致）
- D3=采纳 Apache-2.0 突破 CC0-only（署名义务: sim/content/README.md 素材清单
  新行 + 仓库级 THIRD-PARTY-NOTICES）
- D4=只摘平民 5 张（织布妇/粮仓管事/传令兵/老军侯/主和士绅），军事 6 张弃用
- D5=甲 先入外观面角色分层（最小步）；室内 tileset 等「建筑可进入」玩法立项

素材事实（2026-10-12 实测，agentsociety atlas.json 同族实证）:
- sheet 96x128 = 3 列 x 4 行 @32x32；行序 下/左/右/上（down/left/right/up）；
- col1 = 站立帧（walk.001 与裸方向帧同 rect——PKU atlas.json 实证）；
- 行内 0/2 为步帧。

管线产物: 16x32 逐角色 sheet（48x128 = 3 列 x 4 行 @16x32）——
前端 SheetGeometry {cols:3, framesPerRow:3, standCol:1} 现成适配（actors.ts），
行序重排为前端惯例 下/上/右/左（facingRow: s=0/n=1/e=2/w=3）。

原件不入库（gitignore `sim/content/assets/god-packs/`，~66MB 可重建；
下载源与选片规则见该目录 README.md）。本脚本从原件区只读，产物写
client/public/assets/sprites/（入库）。
"""

from __future__ import annotations

from pathlib import Path

if __package__:
    from .png_codec import read_png_rgba, write_png_rgba
else:  # 保留 python path/to/build_god_characters.py 的直接脚本入口。
    from png_codec import read_png_rgba, write_png_rgba

# --- 布局几何常量（唯一真相源；测试钉同源） ---------------------------------

GRID_COLS = 3
GRID_ROWS = 4
FRAME_W = 32
FRAME_H = 32
OUT_FRAME_W = 16
OUT_FRAME_H = 32
GOD_CHARACTER_SHEET_W = OUT_FRAME_W * GRID_COLS  # 48
GOD_CHARACTER_SHEET_H = OUT_FRAME_H * GRID_ROWS  # 128

#: 原件区根（gitignore，缺席时管线整体 skip——不假绿不报错）
GOD_PACKS_DIR = Path("sim/content/assets/god-packs")

#: D4 白名单：空城计平民 5 张（文件名关键字；军事/名人/游客一律不接）
D4_CIVILIAN_SET = ("织布妇", "粮仓管事", "传令兵", "老军侯", "主和士绅")

#: 桃花源 12 张（D3+D5 全接——古风村民主体）
_TAOHUAYUAN_ALL = (
    "陶村长",
    "阿澄",
    "阿梨",
    "外来博主小岚",
    "文旅经理周越",
    "民俗学者孟教授",
    "基层干部许宁",
    "守旧派陶伯",
    "织染匠阿绣",
    "返乡青年阿远",
    "游客林川",
    "平台运营_Ada",
)

#: 戏内名 → slug（文件名 ASCII 化，前端 sprite key 用）
_SLUGS = {
    "织布妇": "zhibufu",
    "粮仓管事": "liangcangguanshi",
    "传令兵": "chuanlingbing",
    "老军侯": "laojunhou",
    "主和士绅": "zuheshishen",
    "陶村长": "taocunzhang",
    "阿澄": "acheng",
    "阿梨": "ali",
    "外来博主小岚": "xiaolan",
    "文旅经理周越": "zhouyue",
    "民俗学者孟教授": "mengjiaoshou",
    "基层干部许宁": "xuning",
    "守旧派陶伯": "taobo",
    "织染匠阿绣": "axiu",
    "返乡青年阿远": "ayuan",
    "游客林川": "linkai",
    "平台运营_Ada": "ada",
}

#: GOD 行序（down/left/right/up）→ 前端行序（s/n/e/w = 下/上/右/左）
GOD_ROW_TO_OUT = {0: 0, 1: 3, 2: 2, 3: 1}  # down→s, left→w, right→e, up→n


def god_character_out_name(display: str) -> str:
    """戏内名 → 产物文件名（god_villager_<slug>.png）。"""
    return f"god_villager_{_SLUGS[display]}.png"


def god_pack_characters() -> list[tuple[str, Path]]:
    """扫描原件区，返回 (戏内名, 原件路径) 列表。

    只返回 D4 白名单（空城计平民）+ 桃花源 12 张；原件区缺席返回空表
    （调用方 skip，不报错——素材区是 gitignore 可重建资产，CI 无此目录）。
    """
    found: list[tuple[str, Path]] = []
    if not GOD_PACKS_DIR.is_dir():
        return found
    ecg = GOD_PACKS_DIR / "empty-city-gate" / "characters"
    for display in D4_CIVILIAN_SET:
        p = _find_character_file(ecg, display)
        if p is not None:
            found.append((display, p))
    thy = GOD_PACKS_DIR / "taohuayuan-online" / "characters"
    for display in _TAOHUAYUAN_ALL:
        p = _find_character_file(thy, display)
        if p is not None:
            found.append((display, p))
    return found


def _find_character_file(directory: Path, display: str) -> Path | None:
    """按戏内名关键字在 characters/ 目录找 PNG（Agent_NN_<名>.png 命名）。"""
    if not directory.is_dir():
        return None
    for f in sorted(directory.glob("*.png")):
        if display in f.stem:
            return f
    return None


def slice_and_scale_sheet(src: Path, dst: Path) -> Path:
    """96x128 原件 → 48x128 产物（16x32 帧，行序重排）。

    纯 PNG 切块 + 最近邻缩半（AI 生成素材线条硬，最近邻不糊边）；
    alpha 全程保留。零 Pillow 依赖（标准库解 PNG：zlib + filter 还原 +
    重编码）——管线在 uv 环境外也要能跑。
    """
    raw = read_png_rgba(src, allow_rgb=False)
    # 32x32 帧 → 水平缩半 16 + 垂直保高 32（D2=甲：头身比重切——
    # 32x32 帧的头身比约 1:1，垂直取中保留上半身、截掉下半身 16px 会切脚；
    # 实测素材人物脚贴帧底、头顶留白 ~4px：垂直直接保高、水平缩半，
    # 得 16x32 头身比 1:2，与 ArMM1998 16x32 惯例对齐）
    out_w = GOD_CHARACTER_SHEET_W
    out_h = GOD_CHARACTER_SHEET_H
    canvas = [[(0, 0, 0, 0)] * out_w for _ in range(out_h)]

    for god_row in range(GRID_ROWS):
        out_row = GOD_ROW_TO_OUT[god_row]
        for col in range(GRID_COLS):
            frame = [
                [raw[god_row * FRAME_H + y][col * FRAME_W + x] for x in range(FRAME_W)]
                for y in range(FRAME_H)
            ]
            scaled = _halve_width(frame)  # 32x32 → 16x32
            base_x = col * OUT_FRAME_W  # 2026-10-12 修复：三列各写各的区间
            # （修前写死 0——col2 覆盖 col0、col1 全透明，「有头没身」同族几何 bug）
            base_y = out_row * OUT_FRAME_H
            for y in range(OUT_FRAME_H):
                for x in range(OUT_FRAME_W):
                    canvas[base_y + y][base_x + x] = scaled[y][x]

    write_png_rgba(dst, out_w, out_h, canvas)
    return dst


def _halve_width(
    frame: list[list[tuple[int, int, int, int]]],
) -> list[list[tuple[int, int, int, int]]]:
    """单帧水平缩半（32→16）：每两列取左列（最近邻取偶列，保轮廓左缘）。"""
    out: list[list[tuple[int, int, int, int]]] = []
    for y in range(FRAME_H):
        row = frame[y]
        out.append([row[x * 2] for x in range(OUT_FRAME_W)])
    return out


def build_all(out_dir: Path) -> list[Path]:
    """全量构建：扫描原件区 → 逐角色产物。返回产物路径列表。"""
    outs: list[Path] = []
    for display, src in god_pack_characters():
        dst = out_dir / god_character_out_name(display)
        slice_and_scale_sheet(src, dst)
        outs.append(dst)
    return outs


if __name__ == "__main__":
    out_root = Path("client/public/assets/sprites")
    products = build_all(out_root)
    print(f"构建 {len(products)} 张角色 sheet → {out_root}")
    for p in products:
        print(f"  {p.name} ({GOD_CHARACTER_SHEET_W}x{GOD_CHARACTER_SHEET_H})")
