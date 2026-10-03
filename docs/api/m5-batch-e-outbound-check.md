# M5 批次 E · 出站面核对单（docs/api/m5-batch-e-outbound-check.md）

> 能力域：接口 / 兼容性（kilo） | M5-K14 | **零代码核对单**（只出结论，不施工）
> 核对对象：opencode 批次 E 施工物（`70ceaa7` 物化数据面 `anchor_package.py` + `0015` +
> `fork` kind 参数化）与 codex S10 断线安规三条（`docs/security/m5-batch-e-security-preplan.md`）。
> 核对时点：main `04e4220`（= 本树 HEAD，已并入 R-4 施工 `04e4220` 与批次 E 物化 `70ceaa7`）。
> 方法：全部结论**读生产码得出**，每条附文件与行号；不采信「文档说已就绪」。
> 所有权：本单只出结论。**本轮唯一代码面是协议升 1.1**（`ws.py` 版本号一行 + 前端常量 + 断言钉）。

## 0. 两问两答（速览）

| 问                                     | 答                             | 依据                                                                                                                                                                |
| -------------------------------------- | ------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 物化错误机器码要不要进 `_TYPE_TITLE`？ | **不进**（三论证，§1）         | `sim/api/*.py` 对物化**零引用**；常量是裸 slug 非 `/errors/*` URI 形；生产路径上它被 `main.py:133` 的 `except Exception` 降级，根本到不了 HTTP 错误处理器           |
| 断线演练告知帧在出站面的落点？         | **载体已有、落点缺一行**（§2） | `session_state.notice` 字段与 `fork_notice()` 的 fail-closed 兜底先例都在；但 `_handle_sync_request`（`ws.py:569`）**只回 `full_snapshot`**，离线回归没有告知帧落点 |

## 1. 物化错误（`AnchorMaterializationError` 族）· 出站形状核对

### 1.1 事实链（逐跳实测）

1. **异常定义**：`sim/core/persistence/anchor_package.py:140` `AnchorMaterializationError(RuntimeError)`，
   `reason` 取固定集 `MATERIALIZATION_REASONS`（`:110-116`：���`no_package`/`rng_unavailable`/
   `snapshot_missing`/`event_gap`/`corpus_mismatch`），出站面「只允许回这些码」（`:109` 注释）。
2. **机器码常量**：`anchor_package.py:121`
   `ANCHOR_MATERIALIZATION_MACHINE_CODE = "anchor-materialization-unavailable"`，
   且 `:118-120` 明写「**唯一真源在本层**；⚠️ **出站登记在 `sim/api/` 侧（kilo 域）**：本单只提供码，
   不动错误表/协议快照（红线：`shared/protocol.ts` 零 diff，gen-protocol 必须 EXIT 0）」。
   ⇒ **本单就是那个「出站登记」的落点**，本节给结论。
3. **生产触发链**：`ws.py::_handle_load_anchor` → `_ANCHOR_LOAD_HOOK` = `main.py:113`
   `_production_load_hook`（**只登记** `pending_loads`，同步返回 `True`）→ driver 每帧
   `main.py:119 _drain_loads` → `orchestrate_load_anchor(...)`，**整段包在
   `main.py:133 except Exception`**（`:134 logger.warning("fork.load_failed", …)`，
   `:137 load_outcomes.append((anchor_id, False))`）。
4. **HTTP 面零触点**：`sim/api/*.py` 中 `materializ|anchor_package|Materialization` **零命中**
   （读档与分叉都只走 WS 的 `load_anchor` action；`_TYPE_TITLE` 的 6 个键全服务 HTTP 路由）。
5. **WS 面现状**：物化失败**当前不产生任何出站帧**——`load_outcomes` 只被
   `main.py` 追加、被 `sim/tests/test_m5_anchors_crud.py:294` 读，**无生产消费者**；
   而 `_handle_load_anchor` 在 hook 返回 `True` 时**已经**把 `session_state` + `full_snapshot`
   发了（`ws.py:880-888`）。玩家侧此刻是「先看到读档成功，随后世界没变」的沉默。
6. **前端不消费 error 帧**：`client/src/net/ws.ts:86-102` 的 `dispatch` 只处理
   `full_snapshot`/`state_delta`，其余（含 `error`）走 `default` **静默忽略**。

### 1.2 结论：**不进 `_TYPE_TITLE`**

| 论证               | 内容                                                                                                                                                                                                                                                   |
| ------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| ① **无 HTTP 触点** | `_TYPE_TITLE` 的键是 HTTP 机器码（`errors.py:31`），而物化只发生在 WS `load_anchor` 的异步 drain 里（§1.1-4）。把一个到不了 HTTP 错误处理器的异常登记进 HTTP 表 = 死条目，且会让人误以为「玩家会看到这个 code」                                        |
| ② **形态不符**     | 表内 6 键皆 `/errors/<slug>` URI 形；该常量是裸 slug `anchor-materialization-unavailable`（无前导斜杠、无 `/errors/`）。要进表得**先改常量形态**——那是改 opencode 的产物，超出本单所有权，且会诱使协议面新增机器码（与批次 E 的「零 schema」红线冲突） |
| ③ **被降级吃掉**   | 生产路径上它先撞 `main.py:133` 的 `except Exception` ⇒ 变成一条日志 + 死账本，**根本到不了** `install_error_handlers` 的三个 handler                                                                                                                   |

**登记形态（写死，供将来施工单直接引用）**：若将来要让「该档不可回退」这类语义**机器码可辨**，
正确形态是 **WS 错误码扩码**（`_ERROR_*` 现为 11 项闭合集，扩码须：同 CR + 快照 WS 侧零变更

- 前端 `dispatch` 增加消费分支），**不是** HTTP `_TYPE_TITLE`。若只需玩家能读懂，
  则沿用既有 `load_failed`，把 `reason` 映射成**戏内第一人称文案 + 日志字段**（不新增码）。

### 1.3 登记的**真缺口**（不在本单施工，建议另立施工单）

**异步物化结果没有出站通道**：`load_outcomes` 是死账本（§1.1-5）。这与本核对单第 ① 问无关
（问题不是「进不进 HTTP 表」，而是「玩家收不到失败」），但它才是批次 E 出站面真正的缺口。
建议施工单要点（Claude/kilo 域，**本轮约束「版本升=唯一代码面」故不施工**）：

1. `_drain_loads` 失败时经既有 `error` 帧通道回帧（code 沿用 `load_failed`，
   `detail` 用戏内口语，禁把 `reason`/`no_package` 等工程词或量值写进玩家可见文本）；
2. `reason` 落 **日志字段**（`fork.load_failed` 已存在，加 `reason=` 即可），不落出站；
3. **诚实态问题**（需主树裁）：`load_anchor` 目前是「先受理、先发成功帧、后异步执行」，
   失败时已经发过的成功帧收不回 ⇒ 要么改受理语义（受理帧改文案），要么接受「静默失败 +
   仅日志」。**这不是接口面能单方面裁的**，登记在此。

## 2. 断线演练告知帧 · S10 三条落点核对

### 2.1 S10 三条（原文口径见 codex 预研 §1-2）

1. **只讲过去、不承诺未来**；
2. **零元信息/量值**（禁「你错过了 X 场火」「世界按 X 速度推进」「你断了 3600 秒」）；
3. **离线不是豁免期**（离线期产出的叙事文本仍受既有终扫，非免检区）。

### 2.2 逐条核对

| 项                               | 现状                                                                                                                                                                             | 判定                                                                            |
| -------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------- |
| **载体**：`session_state.notice` | 既有字段（D-6 先例：分叉告知一帧承载，`ws.py:891-917`；`notice` 是**既有可选/可空**字段）                                                                                        | **已有**（零 schema）                                                           |
| **兜底先例**：告知文案终扫       | `ws.py:920 fork_notice()` 对档名跑 `scan()`，命中禁词 ⇒ **退化为无档名兜底行 + `ws.fork_notice_degraded` warning**，**不静默放行、不扩词表**                                     | **已有**（照此体例即可，非新判梯）                                              |
| **重连落点**                     | `ws.py:569 _handle_sync_request` **只回 `full_snapshot`**（契约要求如此，`ws-protocol.md` §5）——**没有 `session_state`、没有 `notice`** ⇒ 离线回归**告知帧无落点**               | **需加**（一处：重连时先发 `session_state`（带 notice）再发全量；不改消息集合） |
| **客户端重连语义**               | `client/src/net/ws.ts:56-62` 重连首帧即 `sync_request{reason:"reconnect"}`；`:129 mirror.reset()`（codex 意见 9：全量重置防增量幻觉）；`onStatus('reconnecting')` 已暴露状态回调 | **已有**（前端不得显示任何量值——口径登记，不是我的施工面）                      |
| **结构性保证**                   | `ControlState` 是**连接级**、`unregister` 即丢（`ws.py:274-277`）⇒ 离线期**不存在**可落盘的玩家控制态 ⇒ 「离线不得写玩家档」在倍率/暂停/快进三项上**结构上已成立**               | **已有**（零新增）                                                              |
| **S10-① 只讲过去**               | 出站面只能给「回来后的现状」（A 类已发生的事），**不得**出现「你错过了…」「世界按…推进」                                                                                         | 落点 = 新增的那句 `notice` 文案（**未加前无载体，无从违反也无从兑现**）         |
| **S10-② 零元信息量值**           | 同上；且 `notice` 所在帧的其余字段（`speed`/`anchor`）已是叙事化（`speed ∈ {1,4,16}`、`anchor` 只 `name`+`story_label`），无 `tick/seq/branch_id`                                | **已有**（帧形状本身合规；新文案须续守）                                        |
| **S10-③ 离线不是豁免期**         | 这是**事件面**判据（离线期产的文本仍过 `assemble_prompt` 终扫），出站面只需保证告知句**不暗示豁免**（禁「这几天没人管你」）                                                      | 事件面归 Claude/codex；出站面文案层登记此禁例                                   |

### 2.3 结论：**载体已有、落点需加一行**（归 Claude 域施工，本单不施工）

- **已有**：`session_state.notice` 载体 + `fork_notice()` 的 fail-closed 终扫兜底 + 客户端重连
  首帧语义 + `ControlState` 连接级结构性保证。
- **需加**：**重连路径发 `session_state`（带离线回归 `notice`）**——落在 `_handle_sync_request`
  或其调用层，**零 schema 变更**（`notice` 与 `session_state` 都在既有快照里）。
- **文案口径**（给施工单直接抄）：只讲**已发生的现状**、零量值、零系统词、不承诺未来、不暗示豁免；
  必过 `scan()` 终扫，命中即退化为无细节兜底行 + warning（照 `fork_notice` 体例，**不扩词表**）。
- **登记的待裁**：`notice` 在重连首帧是否**必填**（我建议：断线重连必填、首次连接不填——
  首连没有「离线回归」这回事）。这属消息语义细节，随施工单一并裁。

## 3. 本核对单的边界

- **不含**物化器内部语义、语料切包、`0015` 迁移体例（opencode 域）；**不含**离线推进的事件级
  还原判据（codex/Claude 域，判据在 codex 预研的定标缺口条目）。
- **不含**前端 UI 文案与状态展示实现（cline 前端域）；本单只给「不得显示量值」的口径。
- 本单**不改任何生产码**；唯一代码面是同单的协议升 1.1（`ws.py` 一行 + `ws.ts` 一行 + 8 断言钉）。
