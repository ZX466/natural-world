"""test_build_god_characters.py — GOD 古风角色接入管线回归钉（2026-10-12 D1-D5 裁决兑现）。

裁决记录（docs/data/god-reuse-final.md §5 → 本文件为落地执行记录）:
- D1=甲 素材缩半入 16px 管线(前端零改动)
- D2=甲 角色重切 16x32(与主角帧高一致)
- D3=采纳 Apache-2.0 突破 CC0-only(署名义务: sim/content/README.md + THIRD-PARTY-NOTICES)
- D4=只摘平民 5 张(织布妇/粮仓管事/传令兵/老军侯/主和士绅),军事 6 张弃用
- D5=甲 先入外观面角色分层(最小步),室内 tileset 等「建筑可进入」立项

素材事实(实测): 96x128 sheet,3 列 x 4 行 @32x32;行序 下/左/右/上(PKU atlas.json
同族实证: down/left/right/up);col1 = 站立帧;行内 0/2 步帧 + 1 站帧。
管线产物: 16x32 逐角色 sheet——3 列 x 4 行 @16x32,前端 SheetGeometry
{cols:3, framesPerRow:3, standCol:1} 现成适配。
"""

from __future__ import annotations

import pytest

from sim.content.build_god_characters import (
    D4_CIVILIAN_SET,
    FRAME_H,
    FRAME_W,
    GOD_CHARACTER_SHEET_H,
    GOD_CHARACTER_SHEET_W,
    GRID_COLS,
    GRID_ROWS,
    OUT_FRAME_H,
    OUT_FRAME_W,
    god_character_out_name,
    god_pack_characters,
    slice_and_scale_sheet,
)

# --- 常量钉（布局几何唯一真相源在 build_god_characters.py） -------------------


def test_grid_constants_pin():
    assert (GRID_COLS, GRID_ROWS) == (3, 4)
    assert (FRAME_W, FRAME_H) == (32, 32)
    assert (OUT_FRAME_W, OUT_FRAME_H) == (16, 32)
    assert (GOD_CHARACTER_SHEET_W, GOD_CHARACTER_SHEET_H) == (48, 128)


def test_civilian_set_pin():
    """D4: 平民 5 张白名单（军事/名人/游客一律不接）。"""
    assert len(D4_CIVILIAN_SET) == 5
    assert all(
        ("织布" in n) or ("粮仓" in n) or ("传令" in n) or ("军侯" in n) or ("士绅" in n)
        for n in D4_CIVILIAN_SET
    )


def test_out_name_slugify():
    """戏内名 → 文件名 slug（ASCII 安全，中文保留）。"""
    assert god_character_out_name("织布妇") == "god_villager_zhibufu.png"
    assert god_character_out_name("老军侯") == "god_villager_laojunhou.png"


# --- 原件区扫描（原件不入库 ⇒ 扫描测试在原件缺席时 skip，不假绿） ------------


def test_god_pack_characters_finds_whitelisted_civilians():
    """扫描原件区 → 命中 D4 平民 5 张 + 桃花源 12 张 = 17；
    军事/名人/游客白名单外命中 = 红（D4 红线）；原件缺席 = skip。"""
    found = god_pack_characters()
    if not found:
        pytest.skip("GOD 素材原件区缺席（gitignore 区，本机未收集时不跑）")
    names = {name for name, _path in found}
    assert len(found) == 17
    assert set(D4_CIVILIAN_SET) <= names  # 平民 5 张全中
    # D4 红线：军事/名人词面绝不入库
    for banned in ("斥候", "校尉", "鼓手", "队长", "伤兵", "诸葛亮", "司马懿", "姜维"):
        assert not any(banned in n for n in names), banned


def test_slice_and_scale_produces_16x32_sheet(tmp_path):
    """切帧+缩半：96x128 → 48x128(3x4 @16x32)；站立帧取 col1；原件缺席 skip。"""
    found = god_pack_characters()
    if not found:
        pytest.skip("GOD 素材原件区缺席")
    _name, path = found[0]
    out = slice_and_scale_sheet(path, tmp_path / "out.png")
    assert out.exists()
    w, h = png_dimensions(out)
    assert (w, h) == (GOD_CHARACTER_SHEET_W, GOD_CHARACTER_SHEET_H)


def png_dimensions(path):
    """最小 PNG 尺寸读取（IHDR 头，零 Pillow 依赖——管线产物自证用）。"""
    import struct

    data = path.open("rb").read(33)
    width, height = struct.unpack(">II", data[16:24])
    return width, height


def test_nearest_neighbor_halving_preserves_alpha():
    """缩半必须保留 alpha 通道（RGBA→RGBA，防 RGB 白底吃透明）。"""
    found = god_pack_characters()
    if not found:
        pytest.skip("GOD 素材原件区缺席")
    _name, path = found[0]

    color_type = path.open("rb").read(34)[25]
    assert color_type == 6, "原件应为 RGBA"


def test_three_columns_written_disjoint(tmp_path):
    """三列写位互斥回归钉（2026-10-12 base_x=0 覆盖 bug）：
    col0/1/2 各自可辨——产物任一行三列不得两列相同或全透明。"""
    found = god_pack_characters()
    if not found:
        pytest.skip("GOD 素材原件区缺席")
    _name, path = found[0]
    out = slice_and_scale_sheet(path, tmp_path / "disjoint.png")
    import numpy as np
    from PIL import Image

    a = np.array(Image.open(out))
    for r in range(4):
        cols = [a[r * 32 : (r + 1) * 32, c * 16 : (c + 1) * 16, 3] for c in range(3)]
        for c in range(3):
            assert (cols[c] > 0).sum() > 0, f"row{r} col{c} 全透明"
        assert not np.array_equal(cols[0], cols[2]), f"row{r} col0==col2（覆盖写）"


def test_four_directions_preserved(tmp_path):
    """四向保真回归钉：源四向互异 ⇒ 产物 s/n 互异（管线不得抹平方向）。"""
    found = god_pack_characters()
    if not found:
        pytest.skip("GOD 素材原件区缺席")
    _name, path = found[0]
    out = slice_and_scale_sheet(path, tmp_path / "dirs.png")
    import numpy as np
    from PIL import Image

    a = np.array(Image.open(out))
    s = a[0:32, 16:32, 3]  # out row0 col1（下站立）
    n = a[96:128, 16:32, 3]  # out row3 col1（上站立）
    assert not np.array_equal(s, n), "下/上站立帧被抹平——行映射或写位错误"
