# M6 收官安规预审骨架（docs/security/m6-closure-preaudit.md）

> 维护：Codex（安全/合规/风险域）· 依据：M6-S6 派单（2026-10-05）·
> 基线：main `25b0815` · 日期：2026-10-05 · 树：ZX466/codex
> 性质：**收官预审终版·当前可判定段**——主树三件施工（内容四模块、
> npc_health 对称删除、legacy 旁路收口）合入后按 §8 补终审段。
> 约束：零代码零 schema；不扩词表；不越权改其他树文件。

## 0. 结论速览

| 门 | 状态 | 说明 |
|---|---|---|
| M6 已落安规钉 | ✅ 静态绿 | 扩展定向实跑 70 passed / 15 skipped；15 个 skip 全部是既有 `skip-locked`（内容四 kind 10 + npc_health 5），非缺陷 |
| S4 复验单 | ⏳ | §2 预置，等 `ECOLOGY_/FAUNA_/SPEECH_/FOG_` kind 落地后逐项执行 |
| W-A 四钉 | ⏳ BLOCKED | `sim/world/authority/` 仍不存在，不把未落对象报成通过 |
| POWER 定标证据 | ✅ 可引用 | `POWER_MAX_BIAS=0.18`，同 seed=42 夹具 flip=0.240 ≤ 0.25；定标轮步骤 0 未过，CHAOS/FIRE 不翻 |
| 词表 | ✅ | `META_SHELL` 仍为空；S1 终扫兜底回归在位 |
| 协议面 | ✅ 现状 | 协议 1.2；M6 后 shared/ 零变更；内容事件与火灾事件均不进帧/快照 |

**当前结论态**：**可放行的前提是「主树三件合入后按 §8 补终审」**。当前无
CRITICAL/HIGH 发现；两项 MEDIUM 与三项 LOW 见 §7。当前不是最终放行态。

## 1. 现状证据链

| 证据 | 命令/出处 | 本机结果 |
| --- | --- | --- |
| M6 扩展定向钉 | `uv run pytest sim/tests/test_m6_content_events.py sim/tests/test_m6_power_utility.py sim/tests/test_m6_fire_mechanics.py sim/tests/test_m5_session_state.py sim/tests/test_m6_death_profiles_contract.py sim/tests/test_m6_death_path_data.py sim/tests/test_meta_shell_lexicon.py -q` | `70 passed, 15 skipped in 7.63s` |
| skip 性质 | 内容与死亡契约钉 | 内容四 kind 10 例 + npc_health 对称删除 5 例，均为既有 `skip-locked` |
| 火灾出站面 | `uv run pytest sim/tests/test_m5_fire_outbound.py sim/tests/test_m5_materialization_package.py -q` | `85 passed` |
| 协议与权力红线 | `uv run pytest sim/tests/test_protocol_version.py sim/tests/test_m5_authority_surface.py sim/tests/test_m6_content_events.py::TestThroatGateInherited -q` | `21 passed` |
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

## 7. 发现分级与安规门结论（当前段）

| 级 | 发现 | 判据/证据 | 处置 |
| --- | --- | --- | --- |
| CRITICAL | 无 | 当前定向面无阻断性泄漏或写路径旁路 | — |
| HIGH | 无 | 当前定向面无 D-10 直接破口 | — |
| MEDIUM | npc_health 死亡残留会让 `materialize_hidden` 仍装配死者 | `TestHealthResidueToday` 已锁现状；锁信号为 `_project_npc_death` 出现 `NpcHealth` | 主树 npc_health 对称删除施工后 §8 复核 |
| MEDIUM | legacy `ws_endpoint` 3 处 `.send_json(` 直发绕咽喉闸 | K5 防旁路钉把豁免显式登记并报主树 | 主树收口后 §8 复核；收口钉须同步 |
| LOW | 内容四 kind 未登记，S4 语义钉暂跳 | 10 例 skip-locked | 内容施工合入后 §2 复验 |
| LOW | W-A 对象未落 | authority/ 不存在 | 机制落盘后 §3.1 复验 |
| LOW | 定标步骤 0 未过 | 六读数无连续三次 ≤1.8 | 重派定标轮后 §3.2 复核；不影响当前可判定段 |

**安规门三态结论（当前段）**：**带条件放行**——条件是主树三件施工合入且
§8 终审全部转绿；不满足则维持不放行。当前无 CRITICAL/HIGH，不构成立即阻断。

## 8. 终审段（主树三件合入后补齐；本段暂留占位）

按当前派单，主树三件是 M6 收官最后施工：

1. 内容面四模块 + 四 kind 登记；
2. npc_health 对称删除；
3. legacy `ws_endpoint` 旁路收口。

终审段必须补齐：

| 序 | 复核项 | 命令/判据 | 状态 |
| --- | --- | --- | --- |
| 8-1 | 内容四 kind | §2 S4-1..S4-7 全绿，零 skip | ⏳ 等合入 |
| 8-2 | npc_health 对称删除 | `sim/tests/test_m6_death_profiles_contract.py` 原 skip 全转绿；fork 不克隆死者健康行 | ⏳ 等合入 |
| 8-3 | legacy 旁路收口 | `TestThroatGateInherited::test_no_bypass_send_path_in_sim_api` 判据更新为无 legacy 豁免后仍绿；`sim/api` 旁路数=0（咽喉本体除外） | ⏳ 等合入 |
| 8-4 | D-10 证据链复测 | §1 全部现测；POWER 定标读数现测不引用历史 | ⏳ 收官前 |
| 8-5 | 全量与协议门 | §4 全门现跑；`gen-protocol --check` EXIT 0 | ⏳ 收官前 |

终审结论三态在此节回填；只有本节完成才可把 §7 的「带条件放行」改为
「可放行」或「不放行」。

## 9. 三硬边界复核（M6 段）

| 边界 | M6 复核证据 | 当前判定 |
| --- | --- | --- |
| rng_state 不出网关 | `OUTBOUND_FORBIDDEN_KEYS` 20 键，含 `seed/rng/rng_state/entropy/bit_generator/uinteger/world_seed` 等；`RANDOM_STATE_FORBIDDEN_KEYS` 7 键；内容四 kind 预置钉断言 payload 字段与其零交集；协议快照实际含 `seed`/`tick` 是既有描述文本，字段面由出站禁键与封闭模型守卫 | ✅ 两层禁键在位；未发现新增出站口 |
| 分叉可见性隔离不开启 | 读档=分叉；`session_state` 只暴露 `name/story_label`，测试显式丢弃供数侧 `tick`；`fork` 克隆不携带 `WorldState.entities`，父子世界线各自推进；29 个 fork 编排/克隆钉全绿 | ✅ 不开启；M6 无开放跨线可见面的证据 |
| rate_change 只留预留名 | WS 判别器 mapping 恰 15 项，`rate_change` 不在其中；`shared/openapi.json` 全文不出现 `rate_change` 字符串 | ✅ 仍仅预留，未启用 |

## 10. 钉号总账（M6 段零悬空）

| 钉 | 文件/落点 | 当前状态 | 复验入口 |
| --- | --- | --- | --- |
| FG-1..FG-4 | `m6-content-security-pins.md` | 预置判据，等四 kind 施工 | §2 S4-7 |
| EN-1..EN-5 | `m6-content-security-pins.md` | 预置判据，等生态/动物施工 | §2 S4-7 |
| M-1..M-3 | `m6-materialization-security-pins.md` | M-1 判据由 K1/K2 落进路由面钉；M-2/M-3 仍待 hooks/产物面施工 | §1 定向门 |
| K4 C1..C5 | `docs/api/m6-content-outbound-prestudy.md` + `test_m6_content_events.py` | C5 咽喉闸即绿；C1..C4 随四 kind 解锁 | §2 S4-1..S4-6 |
| K5 四组 | `test_m6_content_events.py` | 7 即绿 / 10 skip-locked | §2 S4-1 |
| A5 health 钉 | `test_m6_death_profiles_contract.py` | 5 绿 / 5 skip-locked；§24.4 登记 | §8-2 |
| LC-1..LC-3 | `m6-content-security-pins.md` | 预置判据，语域施工后执行 | §2 S4-7 |
| S1/S2 终扫钉 | `test_m5_session_state.py` | 全绿；S2 防摘钉在位 | §1 定向门 |
| W-A1-1..W-A2-2 | `m5-power-threatmodel.md` | BLOCKED：authority/ 不存在 | §3.1 |
| POWER bias/flip | `utility.py` + `test_m6_power_utility.py` | 0.18 已钉；flip≤0.25 正式 | §3.2 |

悬空核对口径：本表只列 M6 预审引用过的钉；每个入口都有可执行命令或明确锁
信号。S11 的脚本手法在主树三件合入后对 `FG/EN/LC/K4/K5/A5` 组重跑一次。
