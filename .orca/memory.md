# memory.md — cline 记忆

> 新对话开场先读本文件 + .orca/workflow.txt + .orca/agent-registry.md。你的能力域：依赖/配置/CI/文档域。
> **本文件已入库**（main `3e320b9` 裁决，规则 #7 遗漏补录）——改动它要走提交；跨分支同路径由 Claude（主导）收编时合并。
> 另读：`.orca/talking.txt`（任务指派）、`docs/dev-workflow.md`（含 **§7 Windows 行尾假红**——本机格式类检查报错先看那节）。

## 项目状态（2026-09-20 同步自 main `3e320b9`）

- M0+M1 全部收官（TASK-004 五路全部交付并收编），589 passed 55 skipped。
- 你的 TASK-004 交付已收编（收编回执曾写在你树 talking.txt，现已轮换清空；结论可查 git log「merge: 收编 cline」）。
- **cline 本树另有 4 个提交待收编**（P05 后续 + 规则 #4/#7 落地，见 git log「chore(config): 用户规则 #4/#7」起）。
- 已由用户规则确立：#4 agent 配置目录（`.agent/.agents/.claude/.codex/.kiro/.opencode/.codegraph`）不入 git 但本地须存在；#7 本记忆文件**入库**。
- **待主树裁**：加 `.gitattributes`（`* text=auto eol=lf`）让本机检查与 CI 一致（本机 prettier/gen-protocol 假红已让多位 agent 踩坑）。

## 你已完成的工作（最近一轮）

- CI 固化 M1 跑分+nightly 阈值单一真相源+protocol 版本统一 1.0+docs M1 终校（P05）
- 规则 #4/#7 落地 + dev-workflow §7 行尾陷阱 + README 终校随 S04/D04 更新（T3 69 条/78 断言、P3 收口）
- 顺手修复 opencode D03/D04 共 4 个文件的 `ruff format` 真红（均 LF 复现确认，纯格式）
- 更早累计：TASK-001~003 全链路参与（详见 git log 与 docs/）。

## 已内化教训（写文档/跑检查前先想一遍）

1. **假门禁**：`pytest -m <marker>` 前先确认文件真带 marker——无 marker 收集 0 用例（exit 5）+ 容错 = **常年假绿灯**。T3 对抗 / M1 指标两个命名门禁步骤一律**按文件路径**选（ci.yml 有注释）。
2. **假红 vs 真红必须自证**：本机 `prettier --check`（17 文件）/`gen:protocol --check`（漂移）= CRLF 假阳性；`ruff format --check` 的 opencode D03/D04 4 个文件 = 真红。**自证法**：`git -c core.autocrlf=false checkout-index -a -f --prefix=.tmp-lf/` 导出 LF 内容再跑检查——仍失败=真红（详见 dev-workflow §7）。
3. **跨域状态以 main 实际代码为准**：P05 时我判 P3 两项未落地（当时确实缺），S04 合入后已收口——逐条 `git grep` 确认，别凭留言或旧结论。
4. **文档数字必须实测**：任务书「prompt ~600 tok」实测 232–274 字符 ≈145–171 tok。改数字先跑 test/探针（探针用完即删）。
5. **收尾必清点**：临时文件必删、必 `git status` 多树复查（我曾误建脏文件、误删已跟踪文件）。

## 常用命令（详表见 dev-workflow §2/§3/§7）

- 后端全绿：`uv run ruff check && uv run ruff format --check && uv run pyright && uv run pytest -q -m "not bench"`
- 门禁单跑：`uv run pytest sim/tests/test_t3_gate.py`（T3）/ `uv run pytest sim/tests/test_m1_metrics.py`（M1 指标）
- 前端：`cd client && npx tsc --noEmit && npx eslint . && npx vitest run --passWithNoTests && npx prettier --check .`（prettier 在 Windows 会假红）

## M1 里程碑事实（写文档可直接引用，均实测）

- 差事 **20/20 = 100%**；链路 P95 **≈0.25ms**（假 LLM 下界，线上墙钟看 `docs/perf/llm-monitoring.md`）；prompt **232–274 字符 ≈145–171 tok**；出戏 **4/4**。
- T3 语料 **69 条** / `test_t3_gate.py` **78 断言**全绿；感知红线 `PERCEPTION_TICK_LIMIT_MS=3.6`（预算目标 3.00），口径 = 暖态中位 + warmup。
- protocol 版本 **1.0**：sim `_PROTOCOL_VERSION` 与前端 `PROTOCOL_VERSION` 已统一。
- **遗留（别人的活，勿代做）**：前端 `client/src/net/ws.ts` 尚未接 W6 token（需 `/api/ws-token` 下发端点）；kilo K04 会重写 ws.ts 消费生成类型。

## 当前任务

(空——等 Claude 派发 M2/TASK-005。收到任务后把要点写进「进行中」，完成后把结论追加到「已完成」并回执。)

## 进行中

(空)

## 留言板

(读 Claude 经 talking.txt 写来的任务指派)
