# memory.md — 多 Agent 记忆合集（分节收录各工作树各自的记忆）
> 用户规则 #7（main `3e320b9` 裁决：memory.md 入库）。本文件 = 五树 + 主树记忆的**融合合集**；
> 跨树收编由主导方（Claude）合并。各树本地副本是其对应节的**权威来源**，收编冲突时以各树版本为准。
> 新对话先读：.orca/talking.txt → 本文件**自己那一节** → .orca/workflow.txt + .orca/agent-registry.md。

## ① Claude（主工作树 / 主导）
- 主导/组织：架构/代码质量/逻辑/测试 + 前端/体验/发布/运维；评审 cline 与 kilo 的工作。
- 收编由我执行（merge 各 ZX466/* 分支 → 推 origin+gitee 双远程）；派单写目标树 talking.txt，回执收主树；**不用 orca-cli 发消息**；上下文 50% 提醒切换。
- M0+M1 全量收官：TASK-004 五路（codex=S04/opencode=D04/pi=F06/cline=P05/kilo=K03）全部收编，589 passed / 55 skipped。
- M2 拟派：codex=自我未知/创伤隐藏边界；pi=L1 效用 50NPC 基线+嗅觉传播预算；opencode=嵌入落库/向量检索；kilo=K04（WS 类型进 gen-protocol）。
- 规则速记：#4 除 .orca 外点文件夹不入 git（.codegraph/.agents 每树必有，.claude/.opencode/.codex 对应树有，主树全有）；#7 各树 memory.md 各存各的记忆（tracked）；npm/venv 删除先问用户；Python 必用 uv；playwright 只用 D:\develop\hermes\chrome。

## ② cline（依赖 / 配置 / 文档域）
> 新对话开场先读本节 + .orca/workflow.txt + .orca/agent-registry.md。你的能力域：依赖/配置/CI/文档域。
> **本文件已入库**（main `3e320b9` 裁决，规则 #7 遗漏补录）——改动它要走提交；跨分支同路径由 Claude（主导）收编时合并。
> 另读：`.orca/talking.txt`（任务指派）、`docs/dev-workflow.md`（含 **§7 Windows 行尾假红**——本机格式类检查报错先看那节）。

### 项目状态（2026-09-20 同步自 main `3e320b9`）
- M0+M1 全部收官（TASK-004 五路全部交付并收编），589 passed 55 skipped。
- 你的 TASK-004 交付已收编（收编回执曾写在你树 talking.txt，现已轮换清空；结论可查 git log「merge: 收编 cline」）。
### 已内化教训（实测过，别再踩）
1. **Windows CRLF 假红**：本机 `prettier --check` / `gen:protocol --check` 报格式漂移，先用 `git -c core.autocrlf=false checkout-index -a -f --prefix=.tmp-lf/` 导出 LF 副本复测；LF 下过 = 假红别改代码（详见 docs/dev-workflow.md §7）。已建议 Claude 加 `.gitattributes`（待裁）。
2. **CI 跑分按文件路径接**：无 marker 的专项测试（如 test_m1_metrics.py）在 ci.yml 用文件路径跑，不用 `-m xxx`——加 marker 前后语义会漂移，路径接法防静默排除（P04 教训）。
3. **跨域代改须留言**：opencode D03 的 3 文件 ruff 格式偏差属数据域文件，修复前在其树 talking.txt 留言说明（f775b91）。
4. **与主导方裁决冲突时，以 main 实际决策为准**：memory.md 入库裁决（`3e320b9`）推翻我此前「移出跟踪」提交（cb2d85e），已在 76d6a03 反转并恢复入库。
### 常用命令（M1 收官口径）
- 本树开工第一步：`git merge origin/main`（常落后 main，P05/P04 都遇到过）。
- 全量：`uv run pytest -m "not bench"`（589 passed 55 skipped）；bench：`uv run pytest -m bench`。
- LF 自证：见上 1。
### 未决项
- `.gitattributes`（`* text=auto eol=lf`）建议已提给 Claude，待裁——加了之后各工作树要重签出。

（以下各节由对应 agent 维护——cline 节以上为 2026-09-20 收编版。）

## ③ codex（安全 / 合规 / 风险域）
（占位：待 codex 分支收编时融合其 48 行版记忆。）

## ④ opencode（数据 / 数据库域）
（占位：待 opencode 分支收编时融合其 98 行版记忆。）

## ⑤ pi（性能域）
（占位：待 pi 分支收编时融合其 30 行版记忆。）

## ⑥ kilo（接口 / 兼容性域）
（占位：kilo 树 memory.md 尚未提交，提交后收编融合。）
