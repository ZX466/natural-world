# M7 渲染美术面实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把前端从「色块占位」升级为星露谷调性像素画面：真实小镇瓦片地图 + 主角四向行走动画 + 服务端权威昼夜时钟。

**Architecture:** 协议 1.2→1.3 加法（`MapChunk.ground_b64` + 快照/增量/`session_state` 的 `time` 块）；sim 从 `sim/content/linhe-town.json` 加载 48×48 小镇图替换占位图；前端新增 BootScene 预载 Sprout Lands 素材 → 瓦片层渲染 + 位移推断行走动画 + phase 色罩。地面调色板单一真相源在 client，sim 构建脚本读它取 tile id。

**Tech Stack:** Python 3.12 + FastAPI + pydantic（sim）；Phaser 3.87 + Vite + vitest（client）；Sprout Lands 素材包（Cup Nooble，免费版=非商用许可，本项目私有非商用可用）。

**Spec:** `docs/arch/m7-render-art.md`（本计划逐条兑现其 §2.3 裁决 R1-R8 与 §3-§7）

## Global Constraints

- 包管理只用 uv（Python）/ npm（前端）；Windows 不装 uvloop。
- 事件是唯一写路径（C4）；确定性红线（C5）；`extra="forbid"` 封闭集纪律。
- 协议改动三同步：`sim/api/openapi_ext.py`（或 main.py 模型）与 `shared/openapi.json` **逐字段一致** + `npm run gen:protocol` 再生 `shared/protocol.ts` 同 commit。
- 版本双落点同 commit：`sim/api/ws.py::_PROTOCOL_VERSION` + `client/src/net/ws.ts::PROTOCOL_VERSION`；`sim/tests/test_protocol_version.py::EXPECTED_VERSION` 随升。
- 出戏边界：tick/seq/branch_id/内部 entity_id/rng_state 零出站；`time` 块只含 day/hour/minute/phase/is_market_day（戏内事实）。
- 键白名单测试（`test_ws_gateway.py::test_snapshot_key_whitelist` 等）是封闭集——加字段必须同测试更新。
- git 身份 ZX666X；Conventional Commits；提交尾 `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>`。
- itch.io 需代理 `127.0.0.1:7897`（脚本已验证可达）。

## Review Focus

1. **调色板漂移**（sim 地图用了调色板不存在的 tile id → 前端渲染错图块）：Task 3 的钉测试断言 `linhe-town.json` 的 ground id ⊆ 调色板值域。
2. **ground_b64 字节序错位**（u16 LE 若两端不一致 → 地图错乱不可读）：Task 2 与 Task 6 用同一定义（u16 小端、行主序、chunk 内 16×16=512 字节）两端测试互钉。
3. **出站扫描误伤 `time` 块**（键名含 `time`/`phase` 若撞禁键集 → 静默剥除）：Task 2 的出站干净测试断言 `time` 键存活且含全部五键。
4. **白名单测试遗漏**（`test_snapshot_key_whitelist` 封闭集断言会红，但可能被顺手「改断言」而漏安全评审）：Task 2 明确步骤要求三处白名单断言同步更新并逐键列出。
5. **浏览器旧代码**（Phaser 场景模块 HMR 不彻底 → 修完看不到效果，历史上已发生三次）：Task 8 的验收步骤明确「硬刷新 Ctrl+Shift+R」，且 Vite 重启兜底命令写死。

---

### Task 1: 素材包落库与调色板构建

**Files:**
- Create: `client/public/assets/tilesets/sprout-palette.json`
- Create: `sim/content/README.md`（重写：素材清单登记）
- Create: `sim/content/assets/sprout-lands/LICENSE.md`（许可登记）
- Create: `tools/build-palette.ts`（从素材包提取调色板的 Node 脚本）

**Interfaces:**
- Produces: `sprout-palette.json`，形状 `{ "tileset": "sprout_lands_v1", "image": "sprout-tileset.png", "image_size": [w,h], "tile_size": 16, "ground": { "<name>": <int id>, ... } }`——Task 3（sim 构建脚本）读 `ground`，Task 6（前端 tilemap）读全文件。

- [ ] **Step 1: 用户手动下载素材包（唯一人工步骤）**

请求用户：浏览器打开 `https://cupnooble.itch.io/sprout-lands-asset-pack`（代理已配），下载**免费版** zip，放到 `E:\zxdevelop\project7\_incoming\`（新建目录，gitignore）。

若用户不便：提示也可换 Kenney CC0 包（kenney.nl，直链可脚本化），告知后等待用户选择——素材是整个计划的输入，此处不得跳过。

- [ ] **Step 2: 解包素材到规范位置**

```bash
cd E:/zxdevelop/project7
mkdir -p sim/content/assets/sprout-lands client/public/assets/tilesets client/public/assets/actors
# 解包（PowerShell Expand-Archive；路径按实际 zip 名）
powershell -NoProfile -Command "Expand-Archive -Path '_incoming/*.zip' -DestinationPath 'sim/content/assets/sprout-lands/pkg' -Force"
ls sim/content/assets/sprout-lands/pkg
```

记录解包结果：确认包含 ` Sprout Lands/Basic Tiles/`（或类似路径）下的 tileset png 与 `Characters/` 下角色四向行走 png。**把实际路径写进下一步的脚本**。

- [ ] **Step 3: 写调色板构建脚本 `tools/build-palette.ts`**

脚本职责：读取素材包 tileset png → 按 16×16 网格切分 → 输出 tile index → 复制 png 到 `client/public/assets/tilesets/` → 生成 `sprout-palette.json`。ground 命名映射**人工维护**在脚本顶部常量（草地/路/水/农田等按图集实际内容命名，初版只登记本项目用到的行）：

```typescript
/**
 * tools/build-palette.ts — 从 Sprout Lands 图集生成调色板 JSON。
 * 运行：node tools/build-palette.ts（需 Node ≥24，纯内置模块）
 * ground 映射人工维护：TILE_NAMES 的下标 = 图集内 tile 的行主序 index。
 */
const fs = require('node:fs');
const path = require('node:path');

const SRC = 'sim/content/assets/sprout-lands/pkg/<实际 tileset png 相对路径>';
const OUT_DIR = 'client/public/assets/tilesets';
const TILE = 16;

// ⚠ 执行时按解包结果填写：每个名字对应图集里一个 16×16 块的行主序下标。
// 只登记本项目用的 tile（YAGNI）；新增地形时回来补。
const TILE_NAMES: Record<string, number> = {
  grass_1: 0, grass_2: 1, grass_3: 2,
  path_dirt: 10, path_dirt_edge: 11,
  water: 20, water_edge: 21,
  farm_soil: 30, farm_soil_wet: 31,
  tree_trunk: 40, tree_leaves: 41,
  house_wall: 50, house_roof: 51, house_door: 52, house_window: 53,
  fence: 60,
};

function main(): void {
  fs.mkdirSync(OUT_DIR, { recursive: true });
  const srcPath = path.resolve(SRC);
  const stat = fs.statSync(srcPath);
  // PNG 尺寸解析：读 IHDR（字节 16-23）
  const buf = fs.readFileSync(srcPath);
  const w = buf.readUInt32BE(16);
  const h = buf.readUInt32BE(20);
  if (w % TILE !== 0 || h % TILE !== 0) throw new Error(`图集尺寸 ${w}x${h} 非 ${TILE} 倍数`);
  const maxIndex = (w / TILE) * (h / TILE) - 1;
  for (const [name, idx] of Object.entries(TILE_NAMES)) {
    if (idx > maxIndex) throw new Error(`tile ${name}=${idx} 越界（图集最大 ${maxIndex}）`);
  }
  const dest = path.join(OUT_DIR, 'sprout-tileset.png');
  fs.copyFileSync(srcPath, dest);
  const palette = {
    tileset: 'sprout_lands_v1',
    image: 'sprout-tileset.png',
    image_size: [w, h],
    tile_size: TILE,
    ground: TILE_NAMES,
  };
  fs.writeFileSync(path.join(OUT_DIR, 'sprout-palette.json'), JSON.stringify(palette, null, 2) + '\n');
  console.log('palette written:', Object.keys(TILE_NAMES).length, 'ground tiles');
}
main();
```

- [ ] **Step 4: 运行脚本生成调色板**

```bash
node tools/build-palette.ts
cat client/public/assets/tilesets/sprout-palette.json
```

Expected: JSON 生成，`image_size` 与 png 实际一致。

- [ ] **Step 5: 许可登记 + 素材清单**

`sim/content/assets/sprout-lands/LICENSE.md`：

```markdown
# Sprout Lands 素材包 — 来源与许可

- 包名：Sprout Lands (Asset Pack)
- 作者：Cup Nooble
- 来源：https://cupnooble.itch.io/sprout-lands-asset-pack
- 许可：免费版 — 仅限非商用项目、可修改、需署名（Credit）；不可转售/再分发。
  （付费 $3.99 版解锁商用——本项目若转商用须升级购买并替换本登记。）
- 本项目使用性质：私有非商用 → 免费版许可覆盖。
- 署名落点：游戏内「关于」面板（MVP 后清单）+ 本文件存档。
- 落库日期：2026-10-05
- 版本：免费版（下载日快照）
```

`sim/content/README.md` 重写：保留原「登记不放素材」改为「已登记」清单表（包名/落点/许可文件/运行时副本位置 `client/public/assets/`），并注明「运行时副本由 tools/build-palette.ts 同步，勿手改」。

- [ ] **Step 6: gitignore `_incoming` + 提交**

`.gitignore` 追加一行 `_incoming/`。素材包原件 `pkg/` **不入库**（许可禁止再分发）——gitignore 追加 `sim/content/assets/sprout-lands/pkg/`；LICENSE.md 与调色板 JSON、tileset png（运行时副本）入库。

```bash
git add .gitignore sim/content/ client/public/assets/tilesets/ tools/build-palette.ts
git commit -m "feat(m7-t1): Sprout Lands 素材落库+调色板构建（许可登记/运行时副本/ground 命名映射）"
```

---

### Task 2: 协议 1.3 — `ground_b64` + `time` 块（sim 侧）

**Files:**
- Modify: `sim/api/openapi_ext.py`（`MapChunk` 加 `ground_b64`；新增 `TimeInfo`；`FullSnapshotMessage`/`StateDeltaMessage`/`SessionStateMessage` 加可选 `time`）
- Modify: `shared/openapi.json`（与 openapi_ext 逐字段同步的手工快照）
- Modify: `sim/api/ws.py`（`map_static_payload` 加 ground_b64；`snapshot_payload`/`delta_payload`/`session_state_payload` 加 `time`；`_PROTOCOL_VERSION = "1.3"`；新增 `_time_payload`）
- Modify: `sim/api/main.py`（`WorldMapResponse`/`MapChunk` pydantic 模型加字段）
- Test: `sim/tests/test_m7_time_block.py`（新文件）；更新 `sim/tests/test_ws_gateway.py` 三处白名单、`sim/tests/test_m2_openapi_rework.py` 两处 WorldMapResponse 断言

**Interfaces:**
- Consumes: `sim.core.calendar.game_time/phase_of_day/is_market_day`、`TickLoop.state.tick`。
- Produces:
  - `map_static_payload(tile_map)` 返回的每 chunk dict 多 `ground_b64: str`（**u16 小端、行主序**，每 chunk 16×16×2=512 字节 base64）。
  - `_time_payload(tick) -> dict`：`{"day": int, "hour": int, "minute": int, "phase": "dawn"|"day"|"dusk"|"night", "is_market_day": bool}`。
  - `snapshot_payload`/`delta_payload`/`session_state_payload` 顶层多可选键 `time`（snapshot/delta 必带；session_state 可选）。

- [ ] **Step 1: 写失败测试（时间块 + 出站干净 + 白名单扩键）**

新文件 `sim/tests/test_m7_time_block.py`：

```python
"""M7 协议 1.3：time 块与 ground_b64。

设计：docs/arch/m7-render-art.md §2.2（R1 地面走 HTTP / R3 时钟权威帧）。
出戏边界：time 只含戏内事实五键；禁键（tick/seed/branch）照旧零出站。
"""

import base64
import json

import pytest

from sim.api.ws import (
    _PROTOCOL_VERSION,
    delta_payload,
    map_static_payload,
    session_state_payload,
    snapshot_payload,
)
from sim.core.calendar import TICKS_PER_GAME_HOUR, TICKS_PER_GAME_DAY  # noqa: F401
from sim.world.map import CHUNK_SIZE, Chunk, TileMap

pytestmark = pytest.mark.t1


@pytest.fixture()
def tile_map() -> TileMap:
    chunks = {
        (0, 0): Chunk(cx=0, cy=0, ground=tuple(range(CHUNK_SIZE * CHUNK_SIZE)),
                      collision=(True,) * (CHUNK_SIZE * CHUNK_SIZE)),
    }
    return TileMap(width=CHUNK_SIZE, height=CHUNK_SIZE, chunks=chunks)


@pytest.fixture()
def loop():
    from sim.api.main import _make_clock
    from sim.core.tick import TickLoop
    from sim.core.world import WorldState, build_default_bus
    from sim.core.events import world_create_event

    lp = TickLoop(clock=_make_clock(), bus=build_default_bus(), state=WorldState(world_seed=42))
    lp.enqueue(world_create_event(tick=0, seed=42, entity_ids=("chenmo",)))
    lp.drain_events()
    return lp


class TestTimePayload:
    def test_time_payload_shape(self):
        from sim.api.ws import _time_payload
        # tick = 6h30m = 6*3600 + 30*60 = 23400 → day 1, 06:30, dawn
        t = _time_payload(23_400)
        assert t == {"day": 1, "hour": 6, "minute": 30,
                     "phase": "dawn", "is_market_day": True}

    def test_time_phases(self):
        from sim.api.ws import _time_payload
        assert _time_payload(7 * 3600)["phase"] == "day"
        assert _time_payload(17 * 3600)["phase"] == "dusk"
        assert _time_payload(23 * 3600)["phase"] == "night"
        assert _time_payload(0)["phase"] == "night"

    def test_market_day_interval(self):
        from sim.api.ws import _time_payload
        # day = floor(tick/86400)+1；集市日 (day-1)%5==0 → day1/6/11
        assert _time_payload(0)["is_market_day"] is True        # day 1
        assert _time_payload(86_400)["is_market_day"] is False  # day 2
        assert _time_payload(5 * 86_400)["is_market_day"] is True  # day 6


class TestSnapshotTime:
    def test_snapshot_has_time(self, loop, tile_map):
        payload = snapshot_payload(loop, tile_map)
        assert payload["time"] == {"day": 1, "hour": 0, "minute": 0,
                                   "phase": "night", "is_market_day": True}

    def test_delta_has_time(self, loop):
        loop.issue_move("chenmo", [(1, 0), (2, 0)])
        loop.advance_frame(1.0)
        payload = delta_payload(loop, loop.drain_delta())
        assert set(payload["time"].keys()) == {"day", "hour", "minute", "phase", "is_market_day"}

    def test_session_state_has_time(self):
        payload = session_state_payload(speed=1, paused=False)
        assert set(payload["time"].keys()) == {"day", "hour", "minute", "phase", "is_market_day"}


class TestOutboundClean:
    """time 块不触禁键；禁键照旧零出现（文本扫描）。"""

    def test_time_block_clean(self, loop, tile_map):
        text = json.dumps(snapshot_payload(loop, tile_map))
        assert "tick" not in text
        assert "seed" not in text
        assert "branch" not in text
        assert '"time"' in text  # 剥除闸没把 time 吃掉

    def test_version_is_13(self):
        assert _PROTOCOL_VERSION == "1.3"


class TestGroundB64:
    def test_ground_b64_u16le(self, tile_map):
        raw = map_static_payload(tile_map)
        chunk = raw["chunks"][0]
        data = base64.b64decode(chunk["ground_b64"])
        assert len(data) == CHUNK_SIZE * CHUNK_SIZE * 2  # u16
        # 行主序第 i 格 = struct.unpack('<H', data[2i:2i+2])
        import struct
        first = struct.unpack_from("<H", data, 0)[0]
        assert first == 0  # ground=tuple(range(...)) 首格
        second = struct.unpack_from("<H", data, 2)[0]
        assert second == 1

    def test_world_map_response_schema_has_ground(self):
        from sim.api.main import MapChunk, WorldMapResponse
        fields = MapChunk.model_fields
        assert "ground_b64" in fields
        assert "collision_b64" in fields
        assert "ground_b64" in WorldMapResponse.model_fields  # noqa: 通过模型引用存在性
```

- [ ] **Step 2: 运行确认失败**

```bash
uv run pytest sim/tests/test_m7_time_block.py -v
```

Expected: FAIL——`ImportError: cannot import name '_time_payload'`（或 `map_static_payload` 无 ground_b64 断言失败）。

- [ ] **Step 3: 实现 sim 侧**

`sim/api/ws.py`：

```python
# 新增（放 _rtoken 附近）：
def _time_payload(tick: int) -> dict[str, Any]:
    """戏内时间块（R3 时钟权威帧）。五键白名单，零 tick 原值。

    phase/is_market_day 派生自 sim.core.calendar（与 TopBar 展示同源，
    C3 出戏边界：这些是戏内事实，mock 时代前端就在同形展示）。
    """
    from sim.core.calendar import game_time, is_market_day, phase_of_day

    t = game_time(tick)
    return {
        "day": t.day,
        "hour": t.hour,
        "minute": t.minute,
        "phase": phase_of_day(tick).value,
        "is_market_day": is_market_day(tick),
    }
```

`map_static_payload` 每 chunk 增 ground_b64（与 collision_b64 同层）：

```python
import struct  # 文件头加

def map_static_payload(tile_map: TileMap) -> dict[str, Any]:
    """碰撞+地面层 HTTP 端点载荷（M7：ground_b64 = base64(u16 LE 行主序)）。"""
    chunks = []
    for (cx, cy), chunk in sorted(tile_map.chunks.items()):
        bits = bytes(1 if w else 0 for w in chunk.collision)
        ground = b"".join(struct.pack("<H", g) for g in chunk.ground)
        chunks.append({
            "cx": cx, "cy": cy,
            "collision_b64": base64.b64encode(bits).decode(),
            "ground_b64": base64.b64encode(ground).decode(),
        })
    return {"w": tile_map.width, "h": tile_map.height, "tileset": "grid", "chunks": chunks}
```

三个 payload 函数顶层各加 `"time": _time_payload(loop.state.tick)`（snapshot/delta 必带；`session_state_payload` 无 loop 参数——签名加 `tick: int | None = None`，调用点 `main.py` 传 `app.state.loop.state.tick`，None 时不带 time 键以兼容旧测试）。

`_PROTOCOL_VERSION = "1.3"`。

`sim/api/main.py`：`MapChunk` 模型加 `ground_b64: str` 字段；`SessionStateMessage` 若是 pydantic 模型加 `time: dict | None = None`（先 grep 确认——若 session_state 不走 response_model 则只改 openapi_ext）。`session_state_payload(...)` 调用点传 tick。

`sim/api/openapi_ext.py`：
- `MapChunk`（若在此登记）加 `ground_b64` string 属性并入 required；
- 新增：

```python
"TimeInfo": {
    "type": "object",
    "description": "戏内时间（服务端权威帧；day 从 1 起，phase 四枚举，集市日布尔）",
    "required": ["day", "hour", "minute", "phase", "is_market_day"],
    "properties": {
        "day": {"type": "integer", "minimum": 1},
        "hour": {"type": "integer", "minimum": 0, "maximum": 23},
        "minute": {"type": "integer", "minimum": 0, "maximum": 59},
        "phase": {"type": "string", "enum": ["dawn", "day", "dusk", "night"]},
        "is_market_day": {"type": "boolean"},
    },
    "additionalProperties": False,
},
```

- `FullSnapshotMessage`/`StateDeltaMessage` 的 props 加 `"time": {"$ref": "#/components/schemas/TimeInfo"}` 进 required；`SessionStateMessage` 加 `"time": _oneof_null({"$ref": "#/components/schemas/TimeInfo"})`（可选，不进 required）。

`shared/openapi.json`：与 openapi_ext 逐字段同步（MapChunk/TimeInfo/三消息）。**同步后必须核对逐字段一致**（钉子测试 test_openapi_ext 会做）。

- [ ] **Step 4: 更新白名单与既有断言（逐键列出，不做无评审的静默放行）**

`sim/tests/test_ws_gateway.py`：
- `test_snapshot_key_whitelist`：top_keys 集合加 `"time"`；加一行 `assert set(payload["time"].keys()) == {"day", "hour", "minute", "phase", "is_market_day"}`。
- `test_delta_key_whitelist`：键集加 `"time"`。
- `test_map_keys`（若有）：`payload["map"]` 不变（ground_b64 在 chunk 层）；对应 chunk 断言如有需加。

`sim/tests/test_m2_openapi_rework.py:119,321`：`wm["required"]`/`set(body)` 加 `"ground_b64"`（MapChunk required 集）。

`sim/tests/test_protocol_version.py`：`EXPECTED_VERSION = "1.3"`。

`client/src/net/ws.ts` 的 `PROTOCOL_VERSION = '1.3'`（双落点同 commit 纪律——本 task 一起改，client 侧功能 Task 6 才动）。

- [ ] **Step 5: 跑 sim 全量门禁**

```bash
uv run pytest -q           # 全量 not-bench，任何红都修
uv run ruff check .
uv run pyright
```

Expected: 全绿（2416+新测试 passed）。

- [ ] **Step 6: 再生协议 + 漂移检查**

```bash
cd client && npm run gen:protocol && npm run gen:protocol:check && npx tsc --noEmit && npm run test
```

Expected: `shared/protocol.ts` 再生含 `TimeInfo`/`ground_b64`；`gen:protocol:check` EXIT 0；前端 tsc/vitest 绿（protocol-types 测试自动覆盖新字段）。

- [ ] **Step 7: 提交（三同步一次落）**

```bash
git add sim/ shared/ client/src/ client/public 2>/dev/null; git add -A sim shared client/src client/vite.config.ts
git commit -m "feat(m7-t2): 协议 1.3——MapChunk.ground_b64（u16 LE）+ 快照/增量/session_state.time 权威帧

- openapi_ext 与 shared/openapi.json 逐字段同步；gen:protocol 再生 protocol.ts
- _time_payload 五键白名单（day/hour/minute/phase/is_market_day），零禁键
- 白名单测试三处同步扩键（安全域评审随本 CR：time 块全为戏内事实键）
- 双落点版本 1.2→1.3 同 commit；EXPECTED_VERSION 钉更新"
```

---

### Task 3: 小镇地图构建（sim/content 管线）

**Files:**
- Create: `sim/content/build_town.py`（确定性构建脚本）
- Create: `sim/content/linhe-town.json`（产物，入库可 diff）
- Test: `sim/tests/test_m7_town_map.py`

**Interfaces:**
- Consumes: `client/public/assets/tilesets/sprout-palette.json` 的 `ground` 值域（R5 调色板单源）。
- Produces: `linhe-town.json` 为 `TileMap.from_json_file` 可加载格式（`width/height/tile_size/chunks{(cx,cy):{ground:[...],collision:[...]}}`）。

- [ ] **Step 1: 写失败测试**

```python
"""M7 小镇地图：调色板值域钉 + 可加载性 + 结构判据。"""

from pathlib import Path

import pytest

from sim.world.map import TileMap

pytestmark = pytest.mark.t1

REPO = Path(__file__).resolve().parents[2]
TOWN_JSON = REPO / "sim" / "content" / "linhe-town.json"
PALETTE = REPO / "client" / "public" / "assets" / "tilesets" / "sprout-palette.json"


@pytest.fixture()
def town() -> TileMap:
    return TileMap.from_json_file(TOWN_JSON)


@pytest.fixture()
def palette_ground_ids() -> set[int]:
    import json

    return set(json.loads(PALETTE.read_text(encoding="utf-8"))["ground"].values())


class TestTownMap:
    def test_dimensions_48(self, town: TileMap):
        assert town.width == 48 and town.height == 48

    def test_ground_ids_within_palette(self, town: TileMap, palette_ground_ids: set[int]):
        """R5 防漂移钉：地图引用的每个 tile id 必须在调色板值域内。"""
        used: set[int] = set()
        for chunk in town.chunks.values():
            used.update(chunk.ground)
        unknown = used - palette_ground_ids
        assert not unknown, f"地图使用了调色板外的 tile id: {sorted(unknown)}"

    def test_spawn_walkable(self, town: TileMap):
        """主角出生点 (8,8) 可通行（创世位置硬编码依赖）。"""
        assert town.is_walkable(8, 8)

    def test_border_impassable(self, town: TileMap):
        """四周树林墙：边界格不可走（防走出图）。"""
        for i in range(48):
            assert not town.is_walkable(i, 0)
            assert not town.is_walkable(i, 47)
            assert not town.is_walkable(0, i)
            assert not town.is_walkable(47, i)

    def test_has_variety(self, town: TileMap):
        """至少含水/路/农田三类（内容判据防「全草地」退化）。"""
        seen: set[int] = set()
        for chunk in town.chunks.values():
            seen.update(chunk.ground)
        assert len(seen) >= 6  # 草×n + 路 + 水 + 农田 + 建筑至少
```

- [ ] **Step 2: 跑测试确认失败**

```bash
uv run pytest sim/tests/test_m7_town_map.py -v
```

Expected: FAIL——`linhe-town.json` 不存在。

- [ ] **Step 3: 写构建脚本 `sim/content/build_town.py`**

确定性矩形布局（48×48；R6：脚本产物可 diff、可重跑；布局常量全部具名）：

```python
"""sim/content/build_town.py — 临河镇地图构建（确定性；R6）。

读调色板取 tile id（R5 单源：client/public/assets/tilesets/sprout-palette.json），
写内部格式 JSON（TileMap.from_json_file 可加载）。重跑幂等、产物可 diff。

布局（48×48，格坐标 x→右 y→下）：
- 边界 2 格树林墙（不可走）；
- 草地底；
- 十字土路：横向 y=23-24 全宽，纵向 x=23-24 全高；
- 药铺（主角家）：矩形 (6,8)-(14,14) 墙体不可走，含 door 格可走；
- 住宅×2：(30,6)-(38,12)、(30,32)-(38,38)；
- 农田：(8,30)-(18,40) 土壤；
- 水塘：(36,20)-(45,28) 水（不可走）。
"""
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SIZE = 48
SPAWN = (8, 8)

# 调色板名 → 布局角色（名字必须存在于 sprout-palette.json 的 ground）
PALETTE_NAMES = {
    "grass": "grass_1",
    "grass_alt": "grass_2",
    "path": "path_dirt",
    "water": "water",
    "farm": "farm_soil",
    "wall": "house_wall",
    "roof": "house_roof",
    "door": "house_door",
    "tree": "tree_trunk",
}


def load_palette() -> dict[str, int]:
    palette = json.loads(
        (REPO / "client" / "public" / "assets" / "tilesets" / "sprout-palette.json")
        .read_text(encoding="utf-8")
    )
    ids = {role: palette["ground"][name] for role, name in PALETTE_NAMES.items()}
    missing = set(PALETTE_NAMES.values()) - set(palette["ground"])
    if missing:
        raise KeyError(f"调色板缺 tile: {missing}——先补 tools/build-palette.ts 的 TILE_NAMES")
    return ids


def build() -> None:
    ids = load_palette()
    ground = [[ids["grass"] + ((x * 7 + y * 13) % 5 == 0) for x in range(SIZE)] for y in range(SIZE)]
    # ↑ 伪随机草地变体：确定性算式（不用 random，保持产物 diff 稳定）
    # 修正上面生成式的意图：交替 grass/grass_alt
    for y in range(SIZE):
        for x in range(SIZE):
            ground[y][x] = ids["grass_alt"] if (x * 7 + y * 13) % 11 == 0 else ids["grass"]

    collision = [[True] * SIZE for _ in range(SIZE)]

    def fill(x0: int, y0: int, x1: int, y1: int, role: str, *, walkable: bool | None = None) -> None:
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                ground[y][x] = ids[role]
                if walkable is not None:
                    collision[y][x] = walkable

    # 边界树林墙（外 2 格）
    fill(0, 0, SIZE - 1, 1, "tree", walkable=False)
    fill(0, SIZE - 2, SIZE - 1, SIZE - 1, "tree", walkable=False)
    fill(0, 0, 1, SIZE - 1, "tree", walkable=False)
    fill(SIZE - 2, 0, SIZE - 1, SIZE - 1, "tree", walkable=False)

    # 十字路
    fill(2, 23, SIZE - 3, 24, "path")
    fill(23, 2, 24, SIZE - 3, "path")

    # 药铺（含屋顶行/墙行/门）
    fill(6, 8, 14, 10, "roof", walkable=False)
    fill(6, 11, 14, 14, "wall", walkable=False)
    ground[14][10] = ids["door"]
    collision[14][10] = True  # 门格可走

    # 住宅 ×2
    fill(30, 6, 38, 8, "roof", walkable=False)
    fill(30, 9, 38, 12, "wall", walkable=False)
    ground[12][34] = ids["door"]
    collision[12][34] = True
    fill(30, 32, 38, 34, "roof", walkable=False)
    fill(30, 35, 38, 38, "wall", walkable=False)
    ground[38][34] = ids["door"]
    collision[38][34] = True

    # 农田与水塘
    fill(8, 30, 18, 40, "farm")
    fill(36, 20, 45, 28, "water", walkable=False)

    # 出生点保证可走
    ground[SPAWN[1]][SPAWN[0]] = ids["grass"]
    collision[SPAWN[1]][SPAWN[0]] = True

    # 切 chunk（16×16）写 JSON
    chunks = {}
    for cy in range(SIZE // 16):
        for cx in range(SIZE // 16):
            g, c = [], []
            for ly in range(16):
                for lx in range(16):
                    g.append(ground[cy * 16 + ly][cx * 16 + lx])
                    c.append(collision[cy * 16 + ly][cx * 16 + lx])
            chunks[f"({cx}, {cy})"] = {"ground": g, "collision": c}

    out = {"width": SIZE, "height": SIZE, "tile_size": 16, "chunks": chunks}
    path = REPO / "sim" / "content" / "linhe-town.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"written {path} ({len(chunks)} chunks)")


if __name__ == "__main__":
    build()
```

注意：`from_json_file` 的 chunk 键解析是 `(int(cx), int(cy))`（字符串键 `"(0, 0)"` 经 `int("(0, 0)")` 会炸——**执行时先跑一把验证**；若炸则把键格式改为 `"{cx},{cy}"` 无括号空格并同步改构建脚本）。以 `int()` 能解析为准。

- [ ] **Step 4: 生成地图并跑测试**

```bash
uv run python sim/content/build_town.py
uv run pytest sim/tests/test_m7_town_map.py -v
```

Expected: 全 PASS。若有「调色板缺 tile」→ 回 Task 1 脚本补 TILE_NAMES 再重跑两步。

- [ ] **Step 5: 提交**

```bash
git add sim/content/build_town.py sim/content/linhe-town.json sim/tests/test_m7_town_map.py
git commit -m "feat(m7-t3): 48×48 临河镇地图构建（调色板单源/确定性脚本/防漂移钉）"
```

---

### Task 4: sim 加载真实地图 + 创世村民（R7）

**Files:**
- Modify: `sim/api/main.py`（`_default_map` → 优先加载 linhe-town.json；`entity_ids` 加 3 村民）
- Test: `sim/tests/test_m7_world_bootstrap.py`

**Interfaces:**
- Consumes: `sim/content/linhe-town.json`（Task 3）、`TileMap.from_json_file`。
- Produces: `app.state.tile_map` 为 48×48 真实图；世界创世 4 实体（`chenmo`/`villager_1..3`，pos 全 (8,8) 同格出生——R7 静止实体，无 AI，tick 不动它们）。

- [ ] **Step 1: 写失败测试**

```python
"""M7 世界引导：真实地图加载（fail-safe 回退）+ 创世 4 实体。"""

import pytest

pytestmark = pytest.mark.t1


class TestDefaultMap:
    def test_loads_town_map(self):
        from sim.api.main import _default_map

        m = _default_map()
        assert m.width == 48 and m.height == 48
        assert m.is_walkable(8, 8)
        assert not m.is_walkable(0, 0)  # 树林墙

    def test_fallback_on_missing_file(self, monkeypatch, tmp_path):
        """文件缺失回退 32×32 占位（fail-safe：启动不炸）。"""
        import sim.api.main as main_mod

        orig = main_mod.Path
        monkeypatch.setattr(
            main_mod, "TOWN_MAP_PATH", tmp_path / "nonexistent.json"
        )
        m = main_mod._default_map()
        assert m.width == 32  # 占位图


class TestGenesis:
    def test_genesis_four_entities(self):
        from sim.api.main import build_loop

        async def run():
            loop, _store = await build_loop()
            return loop

        import asyncio

        loop = asyncio.run(run())
        assert set(loop.state.entities.keys()) == {"chenmo", "villager_1", "villager_2", "villager_3"}
```

- [ ] **Step 2: 确认失败**

```bash
uv run pytest sim/tests/test_m7_world_bootstrap.py -v
```

Expected: FAIL（map 32×32；entities 只有 chenmo；`TOWN_MAP_PATH` 不存在）。

- [ ] **Step 3: 实现**

`sim/api/main.py`：

```python
# 模块级常量（_default_map 之前）：
TOWN_MAP_PATH = Path(__file__).resolve().parents[1] / "content" / "linhe-town.json"

GENESIS_ENTITIES: tuple[str, ...] = ("chenmo", "villager_1", "villager_2", "villager_3")
SPAWN_TILE = (8, 8)  # build_town.py 的 SPAWN；村民同格出生（R7 静止）


def _default_map() -> TileMap:
    """M7：优先 sim/content 真实图；缺失/损坏回退 32×32 占位（fail-safe）。"""
    from sim.world.map import CHUNK_SIZE, Chunk

    if TOWN_MAP_PATH.exists():
        try:
            return TileMap.from_json_file(TOWN_MAP_PATH)
        except Exception as exc:  # noqa: BLE001 — 启动健壮性优先，任何损坏都回退
            logger.warning("map.town_load_failed", reason=str(exc))
    chunks = {}
    for cy in range(2):
        for cx in range(2):
            chunks[(cx, cy)] = Chunk(
                cx=cx, cy=cy,
                ground=(1,) * (CHUNK_SIZE * CHUNK_SIZE),
                collision=(True,) * (CHUNK_SIZE * CHUNK_SIZE),
            )
    return TileMap(width=32, height=32, chunks=chunks)
```

`build_loop` 里 `entity_ids=("chenmo",)` 改 `entity_ids=GENESIS_ENTITIES`；创世后实体 pos 全 (0,0)（`world.py:116` 的 `pos=(0,0)` 默认）——**移动出生点到 (8,8)**：查 `world.py` 的 world_create apply 逻辑，若 pos 硬编码 (0,0) 则在本 task 顺手加一个创世后 `move` 不行（必须事件化）——正确做法：`WorldCreatePayload` 不含 pos，最小改动=给 `build_loop` 创世后逐实体 enqueue `move_event(tick=1, actor_id=eid, start=(0,0), goal=SPAWN_TILE, path=((0,0),SPAWN_TILE))`——但 4 实体同 tick 同起点 move 合法（不同 actor）。**执行时先读 `sim/core/world.py:110-120` 与 `move_event` 工厂确认 start/goal 校验规则再落**；若 move_event 拒绝单格路径则改用两格路径 `((0,0),(8,8))` 直线（寻路器外的事件直入需路径自洽——`issue_move` 便捷入口不走寻路，直接 enqueue 工厂事件即可）。

（如实测复杂，备选：村民出生 (0,0) 也无碍——静止实体的位置不构成游戏性依赖，出生点钉测试只对 chenmo 要求 (8,8)？→ 不，Task 3 的 spawn 测试是地图层面的 (8,8) 可走性，与实体位置解耦。**实体初始位置若搬不动就接受 (0,0)**，地图 (0,0) 是树林墙不可走会卡 move——则用上面 move_event 方案或把 SPAWN 直接画在 (0,0) 邻近。执行时以「实体最终落在可走格」为准绳，测试断言改对齐实现。）

- [ ] **Step 4: 全量门禁**

```bash
uv run pytest -q && uv run ruff check . && uv run pyright
```

- [ ] **Step 5: 提交**

```bash
git add sim/api/main.py sim/tests/test_m7_world_bootstrap.py
git commit -m "feat(m7-t4): sim 加载临河镇真实图（fail-safe 回退）+ 创世村民四实体（R7）"
```

---

### Task 5: 前端时钟与地图数据接线（R3 权威帧）

**Files:**
- Create: `client/src/game/clock.ts`（本地时钟推进器）
- Modify: `client/src/net/ws.ts`（dispatch `time` → store；`full_snapshot` 时登记 MapInfo 尺寸）
- Modify: `client/src/store/uiStore.ts`（无改动预期——`setGameClock` 已有；若 phase 枚举需对齐则小改）
- Test: `client/src/game/__tests__/clock.test.ts`

**Interfaces:**
- Consumes: `TimeInfo`（Task 2 生成物 `shared/protocol.ts`）；`useUiStore.setGameClock`。
- Produces: `createClock()` 返回 `{ apply(t: TimeInfo): void; start(): void; stop(): void }`——权威帧重同步 + 每真实秒推 60 游戏秒（1x 60tps 对齐 sim）+ paused 停走。Task 7 的 WorldScene 色罩读 `uiStore.gameClock.phase`。

- [ ] **Step 1: 写失败测试**

```typescript
/**
 * client/src/game/__tests__/clock.test.ts — R3 时钟推进器回归钉。
 * 权威帧重同步 / 按速推进 / 暂停停走 / 速度切换。
 */
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { createClock } from '../clock';
import { useUiStore } from '../../store/uiStore';

describe('createClock', () => {
  beforeEach(() => {
    useUiStore.getState().setPaused(false);
    useUiStore.getState().setSpeed(1);
    vi.useFakeTimers();
  });
  afterEach(() => vi.useRealTimers());

  it('apply 权威帧立即重同步 store', () => {
    const clock = createClock();
    clock.apply({ day: 3, hour: 14, minute: 25, phase: 'day', is_market_day: false });
    const t = useUiStore.getState().gameClock;
    expect(t?.day).toBe(3);
    expect(t?.hour).toBe(14);
    expect(t?.minute).toBe(25);
    clock.stop();
  });

  it('1x 下每真实秒推进 60 游戏秒', () => {
    const clock = createClock();
    clock.apply({ day: 1, hour: 0, minute: 0, phase: 'night', is_market_day: true });
    clock.start();
    vi.advanceTimersByTime(60_000); // 60 真实秒
    const t = useUiStore.getState().gameClock;
    expect(t?.hour).toBe(60); // 0 + 60 游戏分×60s？——不对：60tps=每真实秒 60 游戏秒=1 游戏分
    // 60 真实秒 = 60 游戏分 = 1 游戏小时
    expect(t?.hour).toBe(1);
    clock.stop();
  });

  it('paused 时钟停走', () => {
    const clock = createClock();
    clock.apply({ day: 1, hour: 5, minute: 0, phase: 'dawn', is_market_day: true });
    clock.start();
    useUiStore.getState().setPaused(true);
    const before = useUiStore.getState().gameClock;
    vi.advanceTimersByTime(30_000);
    expect(useUiStore.getState().gameClock).toEqual(before);
    clock.stop();
  });

  it('16x 加速', () => {
    const clock = createClock();
    clock.apply({ day: 1, hour: 0, minute: 0, phase: 'night', is_market_day: true });
    clock.start();
    useUiStore.getState().setSpeed(16);
    vi.advanceTimersByTime(15_000); // 15 真实秒 × 16 × 60 游戏秒 = 14400 游戏秒 = 4h
    expect(useUiStore.getState().gameClock?.hour).toBe(4);
    clock.stop();
  });
});
```

（预期值执行时校准：60tps × speed 的换算写进实现与测试同一常量。）

- [ ] **Step 2: 确认失败** —— `Cannot find module '../clock'`。

- [ ] **Step 3: 实现 `client/src/game/clock.ts`**

```typescript
/**
 * client/src/game/clock.ts — 戏内时钟（R3：服务端权威帧 + 客户端平滑推进）。
 *
 * 权威帧（full_snapshot/state_delta/session_state 的 time 块）到达即整体重同步；
 * 两帧之间按 speed × 60游戏秒/真实秒 本地推进（与 sim 60tps 对齐）。
 * 世界暂停/倍速/读档最坏漂移一帧间隔，任何帧到达即纠正。
 */
import { useUiStore, type InGameTime } from '../store/uiStore';
import type { TimeInfo } from '../net/protocol';

const GAME_SECONDS_PER_REAL_SECOND = 60; // sim 1x = 60tps（DESIGN §10）

const PHASES: Record<string, InGameTime['phase']> = {
  dawn: 'dawn', day: 'day', dusk: 'dusk', night: 'night',
};

export interface WorldClock {
  apply: (t: TimeInfo) => void;
  start: () => void;
  stop: () => void;
}

export function createClock(): WorldClock {
  let gameSecondOfDay = 0; // 当日已过游戏秒（0..86399）
  let day = 1;
  let isMarketDay = true;
  let timer: ReturnType<typeof setInterval> | null = null;
  let lastTick: number | null = null;

  function publish(): void {
    const hour = Math.floor(gameSecondOfDay / 3600);
    const minute = Math.floor((gameSecondOfDay % 3600) / 60);
    const phase = hour < 5 ? 'night' : hour < 7 ? 'dawn' : hour < 17 ? 'day' : hour < 19 ? 'dusk' : 'night';
    useUiStore.getState().setGameClock({ day, hour, minute, phase, isMarketDay });
  }

  return {
    apply(t: TimeInfo): void {
      day = t.day;
      isMarketDay = t.is_market_day;
      gameSecondOfDay = t.hour * 3600 + t.minute * 60;
      publish();
    },
    start(): void {
      if (timer !== null) return;
      lastTick = Date.now();
      timer = setInterval(() => {
        const store = useUiStore.getState();
        if (store.paused) { lastTick = Date.now(); return; }
        const now = Date.now();
        const dt = (now - (lastTick ?? now)) / 1000;
        lastTick = now;
        gameSecondOfDay += dt * GAME_SECONDS_PER_REAL_SECOND * store.speed;
        while (gameSecondOfDay >= 86_400) {
          gameSecondOfDay -= 86_400;
          day += 1;
          isMarketDay = (day - 1) % 5 === 0; // MARKET_DAY_INTERVAL 镜像（sim calendar.py:15）
        }
        publish();
      }, 250);
    },
    stop(): void {
      if (timer !== null) { clearInterval(timer); timer = null; }
    },
  };
}

export type { TimeInfo };
```

（`PHASES` 未用则删；phase 推进逻辑与 `sim/core/calendar.py:47` 对齐。）

- [ ] **Step 4: ws.ts dispatch 接线**

`ws.ts` 的 `dispatch` 三个 case 各加 `time` 处理（模块级单例 clock，导出供 runtime start/stop）：

```typescript
// ws.ts 顶部
import { worldClock } from '../game/clockSingleton'; // 或直接在本文件建单例导出

case 'full_snapshot':
  this.mirror.applySnapshot(msg.actors, msg.lights);
  if (msg.time) worldClock.apply(msg.time);
  ...
case 'state_delta':
  ...
  if (msg.time) worldClock.apply(msg.time);
case 'session_state':  // 现在走 default 静默——加显式 case
  if (msg.time) worldClock.apply(msg.time);
  break;
```

clock 单例与 start/stop 挂到 `runtime.start()`（`clock.start()`）——本 task 先建 `clock.ts` + dispatch 接线，runtime 集成在 Task 7。

- [ ] **Step 5: 前端门禁**

```bash
cd client && npm run test && npx tsc --noEmit && npm run lint
```

- [ ] **Step 6: 提交**

```bash
git add client/src/game/clock.ts client/src/game/__tests__/clock.test.ts client/src/net/ws.ts
git commit -m "feat(m7-t5): 戏内时钟权威帧接线（R3 重同步+平滑推进+暂停停走）"
```

---

### Task 6: 前端瓦片地图渲染（ground_b64 → Phaser 层）

**Files:**
- Create: `client/src/game/render/tilemap.ts`（组装纯函数）
- Modify: `client/src/net/worldApi.ts`（`assembleGround` 与 collision 同型；`MapStatic` 扩展 ground）
- Modify: `client/src/game/world-mirror.ts`（`MapStatic` 加 `ground: Uint16Array`）
- Modify: `client/src/game/scenes/WorldScene.ts`（`redrawMap` 优先 tileset 图集渲染，`grid` 回退色块）
- Modify: `client/src/game/main.ts`（BootScene 注册——本 task 只加 preload 逻辑，或并入 WorldScene.preload，执行时按 Phaser 场景生命周期最小改动）
- Test: `client/src/game/__tests__/tilemap.test.ts` + 扩 `worldApi.test.ts`

**Interfaces:**
- Consumes: `WorldMapResponse.chunks[].ground_b64`（u16 LE，Task 2 定义）、`sprout-palette.json`（Task 1）。
- Produces: `WorldMirror.map.ground: Uint16Array`（整图 tile id，行主序）；WorldScene 用 Phaser blitter/tilemap 渲染。WorldScene 加载键名常量 `TILESET_KEY = 'sprout-tileset'` 供 Task 7 角色层复用。

- [ ] **Step 1: 扩 worldApi 测试（先红）**

`worldApi.test.ts` 追加：

```typescript
import { assembleGround, decodeGroundB64 } from '../worldApi';

describe('decodeGroundB64 / assembleGround', () => {
  it('u16 LE 解码', () => {
    // [id=1, id=258] → LE bytes 01 00 02 01 → base64
    const b64 = btoa(String.fromCharCode(1, 0, 2, 1));
    expect(Array.from(decodeGroundB64(b64))).toEqual([1, 258]);
  });
  it('chunk 组装偏移正确', () => {
    const twoTiles = btoa(String.fromCharCode(7, 0, 9, 0)); // ids 7,9（2 格的 chunk？不——需 512B）
    // 造一个 chunk 全 id=7：256 个 u16 全 7
    const bytes = new Uint8Array(512);
    for (let i = 0; i < 256; i++) bytes[i * 2] = 7;
    const full = btoa(String.fromCharCode(...bytes));
    const grid = assembleGround(32, 32, [{ cx: 1, cy: 0, ground_b64: full }]);
    expect(grid[16]).toBe(7); // chunk(1,0) 首格 = 全图 x=16
    expect(grid[15]).toBe(0);
  });
});
```

- [ ] **Step 2: 实现 worldApi 扩展**

```typescript
export function decodeGroundB64(b64: string): Uint16Array {
  const bin = atob(b64);
  const out = new Uint16Array(bin.length / 2);
  const view = new DataView(new ArrayBuffer(bin.length));
  for (let i = 0; i < bin.length; i += 1) view.setUint8(i, bin.charCodeAt(i));
  for (let i = 0; i < out.length; i += 1) out[i] = view.getUint16(i * 2, true); // LE
  return out;
}

export function assembleGround(
  w: number, h: number,
  chunks: readonly { cx: number; cy: number; ground_b64: string }[],
): Uint16Array {
  const grid = new Uint16Array(w * h);
  for (const c of chunks) {
    const ids = decodeGroundB64(c.ground_b64);
    const baseX = c.cx * 16, baseY = c.cy * 16;
    for (let ly = 0; ly < 16; ly += 1)
      for (let lx = 0; lx < 16; lx += 1) {
        const id = ids[ly * 16 + lx] ?? 0;
        const gx = baseX + lx, gy = baseY + ly;
        if (gx < w && gy < h) grid[gy * w + gx] = id;
      }
  }
  return grid;
}
```

`runtime.ts` 的 `loadWorldMap` 同步加 `ground: assembleGround(...)` 进 `setMap`。

- [ ] **Step 3: WorldScene tileset 渲染（tileset 名非 `grid` 时）**

`world-mirror.ts` 的 `MapStatic` 加 `ground?: Uint16Array`。`WorldScene.redrawMap` 分支：

```typescript
private redrawMap(): void {
  const g = this.mapLayer;
  const map = this.mirror.map;
  if (g === null) return;
  g.clear();
  if (map === null) { /* 现 32×32 兜底不变 */ return; }
  if (map.tileset !== 'grid' && map.ground) {
    this.renderTileset(map, g);
    return;
  }
  /* 现色块渲染不变（mock 模式回退） */
}

/** tileset 渲染：调色板 id → 图集帧，Graphics.drawImage 逐块贴。 */
private renderTileset(map: MapStatic, g: Phaser.GameObjects.Graphics): void {
  const img = this.textures.get('sprout-tileset').getSourceImage() as HTMLImageElement;
  const T = 16;
  for (let y = 0; y < map.h; y += 1)
    for (let x = 0; x < map.w; x += 1) {
      const id = map.ground![y * map.w + x];
      g.drawImage(img, (id % (img.width / T)) * T, Math.floor(id / (img.width / T)) * T, T, T, x * T, y * T);
    }
}
```

（preload 里 `this.load.image('sprout-tileset', '/assets/tilesets/sprout-tileset.png')`；48×48=2304 格一次性 draw，Graphics 层可接受；后续帧率有压力再换 blitter——MVP 后清单。）

- [ ] **Step 4: 前端门禁 + 视觉验证**

```bash
cd client && npm run test && npx tsc --noEmit
```

视觉：后端（无 --reload）+ 前端起着，硬刷新浏览器——48×48 小镇图应为草地底+十字路+房屋色块+农田+水塘（tile 名若与图集实际内容错位，视觉上立即暴露→回 Task 1 调 TILE_NAMES）。

- [ ] **Step 5: 提交**

```bash
git add client/src/net/worldApi.ts client/src/net/__tests__/worldApi.test.ts client/src/game/world-mirror.ts client/src/game/runtime.ts client/src/game/scenes/WorldScene.ts
git commit -m "feat(m7-t6): 瓦片地图渲染（ground_b64 u16LE 解码/组装/图集贴图，grid 回退保留）"
```

---

### Task 7: 角色行走动画 + 昼夜色罩接线

**Files:**
- Modify: `client/src/game/scenes/WorldScene.ts`（精灵池矩形→sprite；位移推断 facing/anim；syncOverlay 读真实 clock）
- Create: `client/src/game/render/actors.ts`（facing/anim 推断纯函数）
- Modify: `client/src/game/main.ts`（spritesheet 加载）
- Modify: `client/src/game/runtime.ts`（clock.start() 集成；确认 mock 分支不与真实 clock 冲突）
- Test: `client/src/game/__tests__/actors.test.ts`

**Interfaces:**
- Consumes: `WorldMirror.actors`（x/y 变化）、`useUiStore.gameClock.phase`（Task 5）、`client/public/assets/actors/` 角色表 png（Task 1 解包结果）。
- Produces: `inferFacing(dx, dy): 'n'|'e'|'s'|'w'` 与 `inferAnim(prev, cur): 'idle'|'walk'`——纯函数可测；场景层消费。

- [ ] **Step 1: 写失败测试**

```typescript
/**
 * client/src/game/__tests__/actors.test.ts — R2 位移推断回归钉。
 */
import { describe, expect, it } from 'vitest';
import { inferFacing, inferAnim } from '../render/actors';

describe('inferFacing', () => {
  it.each([
    [0, 0, 's'],    // 无位移保持/默认朝南
    [1, 0, 'e'], [-1, 0, 'w'], [0, -1, 'n'], [0, 1, 's'],
    [1, 1, 's'],    // 对角取主导轴（y 优先）
  ])('(%d,%d)→%s', (dx, dy, want) => {
    expect(inferFacing(dx, dy)).toBe(want);
  });
});

describe('inferAnim', () => {
  it('位置变化=walk，不变=idle', () => {
    expect(inferAnim({ x: 1, y: 1 }, { x: 2, y: 1 })).toBe('walk');
    expect(inferAnim({ x: 1, y: 1 }, { x: 1, y: 1 })).toBe('idle');
  });
});
```

- [ ] **Step 2: 实现 `render/actors.ts`**

```typescript
/**
 * client/src/game/render/actors.ts — R2：facing/anim 前端推断。
 * sim 侧 Actor.facing/anim 现硬编码（ws.py:360）——表现层推断是纯客户端职责；
 * sim 真供数日，switch 到协议字段的缝已留（mirror actor 的 facing/anim 键直接读）。
 */
import type { MirrorActor } from '../world-mirror';

export type Facing = 'n' | 'e' | 's' | 'w';
export type Anim = 'idle' | 'walk';

export function inferFacing(dx: number, dy: number): Facing {
  if (dx === 0 && dy === 0) return 's';
  if (Math.abs(dy) >= Math.abs(dx)) return dy > 0 ? 's' : 'n';
  return dx > 0 ? 'e' : 'w';
}

export function inferAnim(prev: { x: number; y: number }, cur: { x: number; y: number }): Anim {
  return prev.x === cur.x && prev.y === cur.y ? 'idle' : 'walk';
}
```

- [ ] **Step 3: 角色精灵表加载 + ActorView 改 sprite**

先确认 Task 1 解包结果里角色 png 的帧布局（通常一行=一个朝向 4 帧）。`main.ts` 的 scene config 加 `preload` 或 BootScene：

```typescript
// main.ts createGame 里 scene 数组前插入 BootScene 或给 WorldScene 加 preload：
scene: [new BootScene(mirror), new WorldScene(mirror)]
// BootScene.preload():
//   this.load.spritesheet('chenmo', '/assets/actors/chenmo.png', { frameWidth: 16, frameHeight: 16 });
//   BootScene.create 里 this.scene.start('world')
```

（角色 png 名与帧数执行时按解包结果定；`render/actors.ts` 的帧选择函数 `frameOf(facing, anim, tickFrame): number` 按 `frameWidth=16` 行序换算——四行×四帧布局下行=facing 序 n/e/s/w。）

`WorldScene.syncActorViews` 的 rectangle 池换 `this.add.sprite(...)`：

```typescript
const sprite = this.add.sprite(actor.x * TILE + TILE / 2, actor.y * TILE + TILE / 2, 'chenmo', 0);
// 每 update：
view.sprite.setFrame(frameOf(inferFacing(dx, dy), inferAnim(prev, cur), animClock));
// animClock += delta; walk 帧 4 帧 × 150ms 循环
```

（`prev` 存在 ActorView 里；主角 `startFollow` 保持。tint 字段不再用于填色——删除 `setFillStyle` 逻辑。）

- [ ] **Step 4: 昼夜色罩接真实时钟**

`syncOverlay` 已读 `gameClock.phase`（Task 5 起有真值）；确认 mock 路径 `mockStep.setGameClock` 与 clock 单例不双写（mock 模式 clock.start 不调用——`runtime.start` 里仅真实连接 open 后启动 clock；mock 分支保留自己的 setGameClock）。alpha 查表微调至 Sprout 调性：`{ day: 0, dawn: 0.10, dusk: 0.18, night: 0.35 }`。

- [ ] **Step 5: 前端门禁 + 全链视觉验收**

```bash
cd client && npm run test && npx tsc --noEmit && npm run lint
```

视觉验收（对应设计 §10）：后端无 --reload 跑着 + Vite 跑着 → 硬刷新：
1. 小镇瓦片图铺满（Task 6）；
2. 陈默精灵四向行走动画（点四个方向各验证一次朝向帧）；
3. 3 个村民静止可见（同色系精灵、无动画）；
4. TopBar 时钟走动（1x 每真实分钟 = 1 游戏小时——不对，60tps=每真实秒 1 游戏分，每真实分钟 1 游戏小时；观察分钟位跳动）；
5. 16x 按下时钟明显加速、暂停时钟停走；
6. 等到 dusk/night 相位（或 16x 快进）看色罩变暗。

- [ ] **Step 6: 提交**

```bash
git add client/src/game/
git commit -m "feat(m7-t7): 角色四向行走动画+昼夜色罩真实接线（R2 推断/村民可见/时钟集成）"
```

---

### Task 8: 门禁收口 + README 更新 + 视觉终验

**Files:**
- Modify: `README.md`（快速开始的「32×32」表述、协议徽章 1.2→1.3、mock 模式描述微调）
- Modify: `docs/arch/m7-render-art.md`（状态行：设计稿→已实施；§10 验收清单勾选）

- [ ] **Step 1: 全量门禁（sim+client 双侧）**

```bash
uv run pytest -q && uv run ruff check . && uv run pyright
cd client && npm run test && npm run typecheck && npm run lint && npm run gen:protocol:check
```

Expected: 全绿。数字记录进提交信息（如 `24xx passed`）。

- [ ] **Step 2: README/设计稿文档同步**

README：徽章 `protocol-1.3`；快速开始去掉「默认 32×32 地图」（真实图 48×48；无后端 mock 仍是 32×32 网格）；「无后端演示模式」段补「色块网格=mock、瓦片小镇=真实」判别句。设计稿头部状态行改「已实施（2026-10-05，提交链 T1-T8）」。

- [ ] **Step 3: 视觉终验（用户参与）**

请用户硬刷新浏览器按 Task 7 验收单过一遍；确认后：

- [ ] **Step 4: 收口提交**

```bash
git add README.md docs/arch/m7-render-art.md
git commit -m "docs(m7-t8): 渲染面收口——README 1.3/48×48 表述同步+设计稿实施状态"
```

（推远程由用户裁定时机——此前多轮有「主树推齐」惯例，单轮收口后可推。）
