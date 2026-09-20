# memory.md — Claude（主工作树 / 主导）
> 用户规则 #7：本文件保存 Claude 自己的记忆，供新对话继续任务。**已入库**（main `3e320b9` 裁决）。
> 新对话先读：.orca/talking.txt → 本文件 → .orca/workflow.txt + .orca/agent-registry.md → docs/dev-workflow.md。

## 我是谁 / 在哪
- 主导/组织：架构/代码质量/逻辑/测试 + 前端/体验/发布/运维；评审 cline 与 kilo 的工作。
- 主工作树 E:/zxdevelop/project7 @ main；收编由我执行（merge 各 ZX466/* 分支 → 推 origin+gitee 双远程）。
- 沟通：派单写目标树 .orca/talking.txt，回执收主树 talking.txt；**不用 orca-cli 发消息**。
- 上下文 50% 提醒用户切换新对话。

## 项目状态（2026-09-20）
- 临河镇 2D 像素 LLM 模拟世界，设计基线 DESIGN.md v2.1 冻结。
- M0+M1 全量收官：TASK-004 五路（codex=S04/opencode=D04/pi=F06/cline=P05/kilo=K03）全部收编，main `3e320b9`，589 passed / 55 skipped。
- 双远程同步（origin=github ZX466，gitee=ZX666X）；GitHub 走 127.0.0.1:7897 代理（按域名全局配置）。

## 进行中
- **待收编 4 分支**：cline×5（规则#4/#7 落地+README 终校+D04 格式修复+memory.md 终态 `76d6a03`）、codex×1（.gitignore 兜底 `.*/` `987a44a`）、opencode×1（memory.md `3309c0f`）、pi×1（memory.md `50b0ebb`）。
- kilo 树 memory.md 未提交 → 已留言 kilo 补提交，五树齐后一起收编。
- 收编方法：五树同路径 memory.md 冲突 → 融合为分节合集（每 agent 一节，节内容 = 各树各自版本）。
- **M2 拟派**（尚未派）：codex=自我未知/创伤隐藏边界；pi=L1 效用 50NPC 基线+嗅觉传播预算；opencode=嵌入落库/向量检索；kilo=K04（WS 类型进 gen-protocol，前置已备）。

## 规则速记（用户裁决，不得擅改）
- #4：除 .orca 外点文件夹不入 git；本地 .codegraph/.agents 每树必有，.claude/.opencode/.codex 对应树有，主树全有（2026-09-20 已调整到位并验证）。
- #7：各树 .orca/memory.md 各存各的记忆（tracked）；talking.txt 不入库。
- npm 包/venv 删除先问用户；Python 必用 uv；playwright 只用 D:\develop\hermes\chrome。
