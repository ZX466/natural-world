# memory.md — opencode 记忆

> **新对话开场先读**：`.orca/workflow.txt` + `.orca/agent-registry.md` + 本文件 + `.orca/talking.txt`。
> 我的能力域：**数据/数据库**。上游派单：Claude；评审 Agent：Codex。
> 本文件（用户规则 #7）保存我自己的记忆，供新对话继续任务。**已入库**（`.orca/` 属规则 #4 的例外，
> `.orca/memory.md` tracked；仅 `.orca/talking.txt` 为 worktree-local 忽略）。

---

## 规则速记（用户规则 #4 / #7）

- **规则 #4**：除 `.orca/` 外，所有 `.` 开头文件夹（`.agents` `.claude` `.codex` `.opencode` `.codegraph` `.kiro` 等）
  **不入 git、不推送**。但本地必须存在：
  - `.codegraph`、`.agents` → **每个**工作树都要有；
  - `.claude` / `.opencode` / `.codex` → 在**对应**工作树要有；主工作树全有。
- **规则 #7**：各工作树 `.orca/memory.md` 分别保存各 agent 记忆（本文件）。除 agent 自带记忆外，不强制另造。
- `.gitignore` 已固化：`.orca/` 仅忽略 `talking.txt`；其余 dot-folder 全忽略。

---

## 项目状态（2026-09-20 同步自 main `3e320b9`）

- **M0 + M1 全部收官**，TASK-004 五路（opencode/codex/cline/pi/kilo）全部交付并收编。
- 全量测试：**589 passed, 55 skipped**（571 passed + bench 18 passed 分开跑；详见「验证」）。
- 我的 **D04 已收编进 main**（merge `f73bc04`）。本树 HEAD = `3e320b9`（与 main 齐），无未合并提交。
- 项目：`natural-world`，LLM 驱动 NPC 生活模拟；核心威胁=污染循环（LLM reason 不可信 → 闸门/记忆扫描拦截）。
- 技术栈：Python 3.12 / **uv** / pytest / ruff / pyright / SQLAlchemy 2.0 async + aiosqlite / Alembic / structlog。

## 我已完成的工作

- **TASK-004 / D04（记忆段数据落库）**：
  - `MemoryStore` Protocol 接口化 + `InMemoryStore`（默认，零破坏）+ `make_entry` 唯一构造工厂
    （`sim/llm/memory_scan.py`，S1 守卫保持）。
  - `SqlMemoryStore` 落 `npc_memories`（`sim/core/persistence/memory_store.py`，同步 sqlite3）。
  - 迁移 `0003_memory_write`：`entry_id`(unique)/`source`/`superseded_by`/`invalid_reason` + `idx_memories_visible`。
  - `entropy_log.event_seq` 回填：`flush.py`→`event_index`→`store.append` 同事务回填。
  - 测试 `sim/tests/test_memory_store.py`（10 项）。
- **更早**：TASK-001~003 数据域全链路参与（crypto、M3 预留表 0002 等，详见 `git log` 与 `docs/data/`）。

## 当前任务

(空 —— 等 Claude 经 `.orca/talking.txt` 派发下一单，预计 TASK-005 / M2 相关。)

## 进行中

(空)

## 留言板

- 读 Claude 经 `.orca/talking.txt` 写来的任务指派。
- 已挂账提醒：structlog 需挂 `redact_sensitive` processor（crypto 域，若尚未接线）。
- 潜在方向：M3 嵌入（锁 embedding model → 建 `npc_memory_vec` → 向量检索，关联语义已固化）；
  生产装配把 `MemoryWritePipeline(store=SqlMemoryStore(...))` 接到实际写入点。

---

## 数据域关键契约（速查）

- **MemoryEntry**：`id`(uuid hex,= `npc_memories.entry_id`) / `npc_id` / `content`(唯一受扫描保护) /
  `source∈{reason,dialogue,event,interoception}` / `event_seq`(NULL=推理转述) / `importance` /
  `emotion_tag` / `superseded_by` / `invalid_reason`。
- **写入唯一入口** `MemoryWritePipeline.write()` → `WriteResult(accepted, entry, action, hits, reason)`；
  拒写**不落库**（S4）。**S5**：supersede 只动治理列，永不改 content；iter_visible 过滤被取代；get 审计可见。
- **npc_memories**（0001? no，0002 + 0003）：见 `docs/data/schema.md`。
- **向量关联**：`npc_memory_vec` 是 vec0 虚拟表（alembic 外，需 `LOAD EXTENSION`）；
  业务键 `(event_seq, entry_id)`，rowid = `npc_memories.id`；`DEFAULT_EMBEDDING_DIM=384` 占位待 M3。
- **crypto**：`LZ_MASTER_KEY` 缺失/非法 → 拒绝启动；`encrypt/decrypt_api_key` + `redact_sensitive`。

## 踩坑记录

1. S1 守卫 grep：非 `memory_scan.py` 禁止出现 `MemoryEntry(` → store 必须走 `make_entry(...)`。
2. `MemoryEntry.id`(uuid hex) ≠ `npc_memories.id`(int 自增)；业务句柄统一用 `entry_id`。
3. `.orca/talking.txt` gitignored；`.orca/workflow.txt`、`.orca/agent-registry.md`、`.orca/memory.md` tracked。
4. PowerShell 显示 UTF-8 中文会花屏；用 Python `open(...,encoding='utf-8')` 或 .NET 读，别信控制台。
5. bench 是 wall-time 断言，全量并发跑会抖动偶失败 → **bench 单独跑**；功能套件用 `--ignore=sim/tests/bench`。
6. alembic autogenerate 校验：`upgrade head` → `revision --autogenerate` 看 upgrade() 是否只剩 `pass` → 删临时文件。
7. `WORLD_DB_URL` 控 alembic 目标库（测试用 tmp_path，别动 `world.db`）。
8. Git：提交归属 `ZX666X <zx19836980213@outlook.com>`；推 `origin` + `gitee`；未要求不提交。

## 验证命令

```powershell
uv run pytest -q --ignore=sim/tests/bench     # 571 passed, 55 skipped
uv run pytest sim/tests/bench -q              # 18 passed（单独跑）
uv run pytest sim/tests/test_memory_scan.py sim/tests/test_persistence_m3.py sim/tests/test_memory_store.py -q
uv run ruff check . --output-format=concise
uv run pyright sim/
```

## 已完成任务链

| 任务 | 内容 | 状态 |
|------|------|------|
| M0 | 事件溯源核心 + 0001 | ✅ 收编 |
| TASK-003/D03 | crypto + M3 预留表 + 0002 | ✅ 收编(`52967ed`) |
| TASK-004/D04 | MemoryStore 接口化 + SqlMemoryStore + 0003 + entropy 回填 | ✅ 收编(main `f73bc04`) |

> 每次完成后更新本文件「当前任务 / 进行中 / 已完成」；过时内容删掉。
