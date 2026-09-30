# M5-S4 复核：F-6 双钉落地 + 权力判据对照 CRUD + P6 接线评估（docs/security/m5-s4-f6-review-and-p6-wiring.md）
> 维护：Codex（安全/合规/风险域）· 依据：M5-S4 派单（2026-09-30）、main `12dbbb1`（M5-CRUD：
> F-6 注册侧 `_assert_name_clean` + 出站纵深 `fork_notice` 终扫）、S2b RED 钉转正指示
> （`test_m5_notice_outbound.py` 钉内注释）、m5-authority-criteria-preplan.md（S3 权力判据三红线）、
> m5-fork-evidence-preplan.md §4（F-6 契约四条）、t4-corpus.md §5（预算闸）· 日期：2026-09-30
> · 树：ZX466/codex
> 状态：**复核 + 评估（只读 + 文档）**；零生产语义改动、零词表扩散；CRITICAL/HIGH 结论见 §5。
## 0. 结论速览
| # | 任务项 | 结论 |
|---|---|---|
| 1 | F-6 双钉安规复核 | ✅ **三契约点全部闭合**（词表零扩散 / 422 结构化形 / 退化不静默——§1 逐条实测） |
| 2 | 权力判据对照 CRUD 面 | ✅ **三红线仍闭合**：anchors CRUD 五键白名单未变、ProblemDetail 422 体零权力键、递归禁键扫通过（§2）；1 条 LOW 登记项 |
| 3 | P6 接线评估 | ✅ **就绪**：52 语料 ≤ 60 闸，零新增接线位；1 条 MEDIUM 提案（预算语义的抖动余量，§3.3——不在 S4 擅改） |
| 4 | 环境缝（复核中发现） | ⚠ **LOW**：本树残留旧 schema `world.db` 致 CRUD teardown 报错——已处置 + 已登记防复发（§4） |
## 1. F-6 双钉安规复核（只读实测，逐条对契约）
### 1.1 契约点①：词表零扩散 ✅
`BANNED_WORDS_META`(21) + `BANNED_WORDS_PERSIST`(7) = **28**，与 S2b 时点一致（git diff 零行）。
`_assert_name_clean`（`anchors.py:83-94`）与 `fork_notice` 终扫（`ws.py:913-923`）均**只消费**现行
`scan()`，无新增词面/白名单/例外——与 S2b §4.2 表态 4 及裁 22-C⑤ 完全一致。
### 1.2 契约点②：422 结构化形 ✅
本机实测（复现，非引述）：
```
_assert_name_clean("AI")        → HTTPException 422 detail="/errors/anchor-name-rejected|'AI' 含不可用词汇：AI"
_assert_name_clean("我的存档")  → HTTPException 422 detail="/errors/anchor-name-rejected|..."
```
- 机器码 `type` 与 `detail` 以 `|` 分段（同 ProblemDetail 体例，`12dbbb1` S-1 全局换形兜底）；
- 调用点 **POST**（`anchors.py:337`）与 **PATCH**（`anchors.py:350`）**双双在位**——
  S2b 契约点 1（「POST/PATCH 双扫」）完整兑现；
- `scan` 经模块顶 import（`anchors.py:33`）——S2b 白盒钉
  `test_contract_requires_scan_on_name_fields` 已按钉内指示**自动转绿**（skip 条件解除）。
### 1.3 契约点③：退化不静默 ✅
`fork_notice` 终扫（`ws.py:920-922`）本机实测：
```
"AI"           → "你回到了先前的那段日子"（兜底行）+ logger.warning("ws.fork_notice_degraded")
"角色扮演乐园"  → 同上
"初到临河"      → "你回到了「初到临河」那段日子"（正常档名不误伤）
```
warning 事件 `ws.fork_notice_degraded`（reason=banned_name_outbound）在位——**观测面不缺**。
S2b RED 指纹钉 `test_banned_anchor_names_currently_pass_through` 已按钉内指示**转正**为
`test_banned_anchor_names_degrade_at_outbound`（退化不原样出站 + 正常行
`clean_names_keep_named_notice` 不误伤）——**转正语义与钉内预设完全一致**。
**复核结论**：F-6 双钉（注册侧 fail-closed + 出站纵深）**安规面闭合**，无 CRITICAL/HIGH。
## 2. 权力判据对照 CRUD 落地面（三红线适配性复核）
S3 判据（m5-authority-criteria-preplan.md）在 CRUD 落地后的适用性逐条复核：
| 红线 | CRUD 面对照 | 结论 |
|---|---|---|
| **A 协议零新增** | POST/PATCH/DELETE 响应 schema 仍为 `AnchorListItem` 五键白名单（id/name/story_label/created_at/protected）；`PAYLOAD_MODELS` 与 `EventKind` 数量对拍钉（`test_event_kinds_closed`）在位 | ✅ 闭合——CRUD 未顺带加任何权力字段（K4 §2.2 D 类候选面保持全否） |
| **B 出站递归禁键** | `test_anchors_payload_recursive_clean` 对 `AnchorListItem.model_dump()` 递归扫零命中；新增的 **ProblemDetail 422 体**（type/title/status/detail/instance）亦零命中（本复核补测） | ✅ 闭合 |
| **C 操纵感零豁免** | 权力语境尚无出站文本源（机制未施工）；`manipulation` 码判据（`judge_hard` 复用）与 CRUD 面无耦合——机制施工时仍零改判据 | ✅ 闭合（N/A 项成立） |
**1 条 LOW 登记（不阻塞）**：`AnchorListItem.protected` 键不在禁键集——它是**玩家档语义**
（末梢游标保护，K4 D-14），不是权力键；禁键集维持 9 键不动。若未来 protected 语义被
机制挪用（如「权位保护」），须在 preplan §3 走 CR 重估——本行仅为预登记，非缝。
## 3. P6 探针接线评估（零烧钱，不真跑）
### 3.1 探针集挂载点（结论：**无新增接线位**）
P6 六条已在 CORPUS（52），消费方与 P1-P5 完全同构：
- **CI 门禁**（零烧钱）：`test_t4_probes.py` 无 marker 用例（完整性/文档同步/判定码自检/
  期望卫生/预算闸自证）随 `-m "not bench"` 跑——**已生效**，P6 六条自动纳入
  `TestExpectedHygiene`（193→195 通过数即含 P6 期望卫生参数化）；
- **真模型探针**：`TestLiveProbes` 按 `CORPUS` 参数化——P6 自动随 52 条全量入参，
  **无 P6 专属 runner**；
- **nightly**：`t4-nightly.yml` 存照形态不动（M4-C6 改约：本地跑一轮 = 等效验收）；
- **报告**：`t4-results/t4-report.json` 按 `category_counts` 驱动，P6 分类自动出现。
### 3.2 入参表（报告对账用）
| 面 | 入参 | 值 |
|---|---|---|
| model / base_url | `T4_MODEL` / `T4_MODEL_BASE_URL` | 缺省 `Deepseek-v4-flash` @ `https://chatapi.weixin.qq.com/openai/v1` |
| 凭据 | `T4_MODEL_API_KEY` | 运行时环境变量（缺 → 52 条全 skip，零烧钱） |
| 显式选择 | `T4_RUN` | `=1` 才触发（key 存在但未选中时绝不调用） |
| 温度/长度 | — | 0.7 / 1024（§5 锁） |
| 重试 | `llm_client.MAX_ATTEMPTS` | 运行期压 1（零重试；抖动记 inconclusive 不红） |
| 预算闸 | `T4_CALL_BUDGET` | 缺省 60（**只可收紧**，`min(value, 60)` 硬上限） |
| 挂载命令 | — | `uv run pytest sim/tests/test_t4_probes.py -m t4 -v` |
### 3.3 预算闸 60≥52 复核 + **1 条 MEDIUM 提案**
- 全量 52 调用 ≤ 60 闸，余量 **8** ✅；
- **预算语义现状（实测代码序）**：`_spent.calls += 1` 在 `try` **之前**——**抖动（timeout/
  connection/5xx）也计入预算**。S9 终判轮实测抖动 23/46 ≈ 50%；若本轮端点抖动 > 8 条，
  后续题面将被预算闸 skip（报告 inconclusive 可见，但**漏测**）；
- **提案（不在 S4 擅改，留主树裁）**：
  - 首轮跑后按实测抖动率定夺：抖动 ≤ 8 → 维持 60；> 8 → 走 CR 把闸提至
    `52 + 实测抖动数 + 4`（建议 70 起评）；
  - 备选口径：抖动**不计预算**（`calls += 1` 挪进成功路径）——语义更准但改动触及
    test 文件，且「预算防烧钱」的原始意图是硬闸总量，保持现状 + 提闸更贴裁 14 原文；
  - **不采纳**：预算闸放宽到无上限（违反 §5 硬闸本意）。
### 3.4 判据
P6 接线 = **语料已就绪 + 挂载零新增 + 预算余量复核通过** → 就绪状态成立；
「接线完成」的最终判定仍以主树带 `T4_RUN=1` 真跑一轮 52 条出正式判读为准（零烧钱三把锁
在真跑时才消耗）。
## 4. 环境缝（复核中发现，LOW，已处置 + 登记）
**现象**：复核跑 CRUD 钉时 teardown 报 `table branches has no column named rng_state`。
**根因**：本树残留本地 `world.db`（`.gitignore` 已盖的运行时库，0008 前旧 schema，无
alembic_version）——`main.py` lifespan 对**同路径** `world.db` 跑 `Base.metadata.create_all`
（表存在即跳过，**不补列**）→ 旧 schema 库永不会被 create_all 修复；0009+ 的迁移只对
生产路径（`alembic upgrade head`）生效。
**处置（本复核内完成）**：本地残留库零生产数据 → 直接删除，TestClient 首跑按开发库快速
起步语义重建新 schema——CRUD 30 钉全绿复跑通过。
**防复发登记（给 opencode 数据域，随下次迁移单一行）**：`create_all` 快速起步库在迁移
落地后会静默落后——**本地开发起步建议统一走 `alembic upgrade head`**（main 树 world.db
已带 rng_state，未踩坑）；或 create_all 后对 `alembic_version` 缺失的库 stamp+upgrade。
**本项为环境运维缝，不是代码缝**（create_all 的「测试内存库 + 开发快速起步」定位在
docstring 明写），不改生产语义。
## 5. CRITICAL / HIGH 汇总
**无 CRITICAL / 无 HIGH。** 1 条 MEDIUM（§3.3 预算抖动余量提案，留主树裁）+ 1 条 LOW
（§4 环境缝，已处置并登记防复发）+ 1 条 LOW 预登记（§2 protected 语义重估条件）。
## 6. 施工归属表
| 件 | 归属 | 时点 |
|---|---|---|
| F-6 双钉（已落地） | Claude（`12dbbb1`） | ✅ 本复核确认闭合 |
| S2b RED 钉转正 | Claude（按钉内指示） | ✅ 转正语义与预设一致 |
| 预算抖动余量提案 | 主树裁 → codex CR（若提闸） | 首轮 T4 真跑后 |
| create_all 快速起步 vs alembic 防复发 | opencode（随下次迁移单） | 下一迁移单 |
| protected 语义重估条件 | codex（preplan §3 CR） | 仅当机制挪用该语义 |
| T4 P6 真跑 52 条判读 | 主树（三把锁齐全时） | M5 收官窗口 |
| 权力机制本体施工验收 | Claude，判据 = preplan 红线 A/B/C 8 钉 | 批次 C 开工单 |
## 7. 变更纪律
- 本稿为复核/评估记录，不设新红线；新红线（如预算语义变更）须回写
  m5-authority-criteria-preplan.md / t4-corpus.md 并走 CR。
- §4 防复发项落 opencode 迁移单时，本稿留痕即完成使命，不另立追踪。
