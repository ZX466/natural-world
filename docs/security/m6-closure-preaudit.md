# M6 收官安规预审骨架（docs/security/m6-closure-preaudit.md）

> 维护：Codex（安全/合规/风险域）· 依据：M6-S5 派单（2026-10-04）·
> 基线：main `0d5db41` · 日期：2026-10-05 · 树：ZX466/codex
> 性质：**预审骨架**——锁定证据、复验命令与判红条件；范围与放行判断归主树。
> 约束：零代码零 schema；不扩词表；不越权改其他树文件。

## 0. 结论速览

| 门 | 状态 | 说明 |
|---|---|---|
| M6 已落安规钉 | ✅ 静态绿 | 定向实跑 33 passed / 10 skipped；skip 全部是内容面四 kind 未登记的既有 `skip-locked` |
| S4 复验单 | ⏳ | §2 预置，等 `ECOLOGY_/FAUNA_/SPEECH_/FOG_` kind 落地后逐项执行 |
| W-A 四钉 | ⏳ BLOCKED | `sim/world/authority/` 仍不存在，不把未落对象报成通过 |
| POWER 定标证据 | ✅ 可引用 | `POWER_MAX_BIAS=0.18`，同 seed=42 夹具 flip=0.240 ≤ 0.25；定标轮步骤 0 未过，CHAOS/FIRE 不翻 |
| 词表 | ✅ | `META_SHELL` 仍为空；S1 终扫兜底回归在位 |
| 协议面 | ✅ 现状 | 协议 1.2；内容事件不进帧/快照的守卫钉已预置 |

## 1. 现状证据链

| 证据 | 命令/出处 | 本机结果 |
| --- | --- | --- |
| M6 定向钉 | `uv run pytest sim/tests/test_m6_content_events.py sim/tests/test_m6_power_utility.py sim/tests/test_m6_fire_mechanics.py sim/tests/test_m5_session_state.py -q` | `33 passed, 10 skipped in 3.79s` |
| skip 性质 | `sim/tests/test_m6_content_events.py` | 10 个 skip 均因内容面四 kind 未登记，属既有 `skip-locked`，非缺陷 |
| POWER 旋钮 | `sim/npc/utility.py` | `POWER_MAX_BIAS: Final[float] = 0.18` |
| POWER 钉 | `sim/tests/test_m6_power_utility.py::TestPowerBiasWiring::test_flip_bounded_by_bias_constant` | 断言 `ratio <= 0.25` 且 `POWER_MAX_BIAS == 0.18`；注释记录 seed=42 实测 0.240 |
| 定标口径 | `docs/perf/m6-calibration-execution.md` | 步骤 0 未过，暂不收口 CHAOS/FIRE；0.18 是确定性裁值 |
| 协议版本 | `sim/api/ws.py::_PROTOCOL_VERSION` | `1.2` |
| 终扫兜底 | `sim/tests/test_m5_session_state.py` | S1 终扫、退化、warning 与防摘钉在位 |

**POWER 证据链提示（本稿引用口径）**：定标结论 = `0.18` + flip `0.240 ≤ 0.25`
（pi P5 同 seed 扫参）；`flip ≤ 0.25` 由 advisory 翻正式。**熵守卫另建基线**
（L1 bench 真实分布），本稿不把夹具熵读数跨口径当成安规熵断言。

## 2. S4 内容面复验单（等四 kind 落地即跑，不重写判据）

锁信号：`EventKind` 出现 `ECOLOGY_`、`FAUNA_`、`SPEECH_`、`FOG_` 前缀成员。
`sim/tests/test_m6_content_events.py` 的 10 个 skip 会自动解锁；解锁后按本单逐项
复核，不重建测试。

| 序 | 复验项 | 命令 | 预期 | 判红条件 |
| --- | --- | --- | --- | --- |
| S4-1 | 红线恒等式与登记面 | `uv run pytest sim/tests/test_m6_content_events.py -q` | 0 failed；原 skip 全部转绿 | 任一 skip 未解锁、`PAYLOAD_MODELS` 与 `EventKind` 数不等 |
| S4-2 | 内容 payload 归因禁键 | 同上 | `ATTRIBUTION_FORBIDDEN_KEYS` 递归零命中 | `actor`/`culprit`/`attribution` 等键出现在 ecology/fauna/speech/fog payload |
| S4-3 | speech 零社会分层数值 | 同上 | 只允许布尔/可达性枚举；字段注解零 `int`/`float` | tier/level/rank/literacy/ratio 等键或数值字段出现 |
| S4-4 | 内容面零出站键 | 同上 | `OUTBOUND_FORBIDDEN_KEYS` 零命中 | 权力键或随机流状态键进内容 payload |
| S4-5 | 零帧面 | 同上 + `uv run pytest sim/tests/test_protocol_version.py -q` | 四 kind 不进 WS 判别器/快照/生成物；协议版本与登记一致 | `ecology.`/`fauna.`/`speech.`/`fog.` 出现在 `shared/protocol.ts` |
| S4-6 | 咽喉闸无旁路 | `uv run pytest sim/tests/test_m6_content_events.py::TestThroatGateInherited -q` | `_send_to` 接剥离闸；`sim/api` 无未登记 `.send_json(` 直发 | 出现新旁路；legacy `ws_endpoint` 豁免被收口后须同步改钉 |
| S4-7 | S4 语义钉与本稿对拍 | 逐钉核对 LC/FG/EN 判据 | 与 `docs/security/m6-content-security-pins.md` 无冲突 | 实现绕开 LC-1 或把 quantity 默认升为玩家叙事 |

## 3. W-A 与 POWER 复验单

### 3.1 W-A 四钉（BLOCKED）

| 钉 | 复验动作 | 预期 | 当前状态 |
| --- | --- | --- | --- |
| W-A1-1 | 白盒扫 `sim/world/authority/*.py` 零内建词面过滤 | 零命中 | ⏳ 对象不存在 |
| W-A1-2 | 核 `banned_words.py` diff 与词面用例同步 | 零新增词面或走完整 CR | ⏳ 等机制 diff |
| W-A2-1 | 白盒扫 authority 对 `UtilityDecision`/`Intent` 的直改/import | 零命中 | ⏳ 对象不存在 |
| W-A2-2 | 同输入换权力档，`willingness_conflict` band 变化 | band 随档变化 | ⏳ 等接线；power 已接 utility，但 authority 机制未落 |

### 3.2 POWER 定标与安规口径

1. `POWER_MAX_BIAS == 0.18` 是常数钉，只能随定标轮同 CR 改。
2. `flip ≤ 0.25` 翻正式；同 seed=42 记录值 `0.240`。复验时必须现测，不引用他人读数。
3. 熵守卫不得跨口径引用：夹具体熵 0.68–0.88 与 P10 合成面不同；M6 收官如需熵断言，
   先在 L1 bench 真实分布建基线。
4. 步骤 0 复跑判据：连续 3 次 `throttle_probe` ≤ 1.8，且跑前/跑后双探针均不进临界带。
   在此前提下才允许 CHAOS/FIRE 翻正式。

## 4. 收官动态门（放行前执行）

| 门 | 命令 | 预期 |
| --- | --- | --- |
| 全量功能门 | `uv run pytest -m "not bench" -q` | 主树基线 2368 passed / 132 skipped 或更新后的全绿 |
| 静态门 | `uv run ruff check . && uv run pyright sim/` | 双 0 |
| 协议门 | 从 `client/` 跑 `npx tsx ../tools/gen-protocol.ts --check` | EXIT 0 |
| 定向内容门 | §2 S4-1..S4-6 | 全绿且零未解锁 skip |
| 权力门 | `uv run pytest sim/tests/test_m6_power_utility.py sim/tests/test_m5_authority_surface.py -q` | 全绿；W-A 仍未落则如实 BLOCKED |

## 5. 责任与触发

| 项 | 归属 | 触发 |
| --- | --- | --- |
| S4 复验 | codex | 内容四 kind 登记合入后 |
| W-A 复验 | codex | authority/ 落盘并接线后 |
| POWER 复验 | codex 复核 / pi 跑分 | 重派定标轮满足步骤 0 后 |
| 内容施工 | Claude | 主树按 S4/K4/P4 预算单派发 |
| 放行裁决 | 主树 | 本骨架所有适用门转绿后 |

## 6. 变更纪律

- 本稿只预置骨架与复验单，不替主树放行。
- 所有引用读数须注明口径；复验必须现测。
- 任何词表、协议、禁键集或常数改动走 CR；本稿不提前放宽任何边界。
