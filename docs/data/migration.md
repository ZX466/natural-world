# Alembic 迁移策略（docs/data/migration.md）

> 技术栈：Alembic + SQLAlchemy 2.0 async + aiosqlite（DESIGN.md §4）。
> **真源声明**：表结构以 `sim/core/persistence/models.py` 与
> `sim/core/persistence/alembic/versions/` 为准，本文不复制任何模型或迁移代码。
> 表语义与列约束见 [`schema.md`](schema.md)。

---

## 1. 迁移策略原则

- **版本化**：每个 schema 变更对应一个迁移脚本，可追溯、可回滚。
- **幂等**：迁移脚本可在任意顺序执行后达到一致状态（Alembic 管理顺序）。
- **前向兼容**：新表/新列用 `nullable=True` 或 `server_default` 渐进引入。
- **零停机**：SQLite 单文件数据库，迁移期间世界暂停（tick 暂停）。

---

## 2. 目录结构（现状）

```
alembic.ini                              # 仓库根，script_location 指向下方
sim/core/persistence/
├─ models.py                             # ORM 模型（唯一表结构真源）
├─ database.py                           # async engine + session factory
└─ alembic/
   ├─ env.py                             # 异步 env（WORLD_DB_URL，默认 sqlite+aiosqlite:///world.db）
   └─ versions/
      ├─ 0001_m0_initial.py
      ├─ 0002_m3_reserved.py
      ├─ 0003_memory_write.py
      ├─ 0004_m2_npc_attributes.py
      ├─ 0005_m3_knowledge_governance.py
      ├─ 0006_m4_structures.py
      ├─ 0007_m4_material_balances.py
      ├─ 0008_m5_fork_identity.py
      ├─ 0009_branches_rng_state.py
      ├─ 0010_protected_backfill.py
      ├─ 0011_anchor_packages.py
      ├─ 0012_branches_current.py
      ├─ 0013_power_state.py
      └─ 0014_fires.py
```

新增迁移时在 `versions/` 追加编号文件，并在下节登记一行；不要回头改已合入的迁移。

---

## 3. 迁移登记表

| revision | 文件 | 内容 |
|---|---|---|
| 0001 | `0001_m0_initial.py` | events / branches / snapshots / player_anchors / llm_profiles / entropy_log |
| 0002 | `0002_m3_reserved.py` | M3 预留空表：npc_memories / relationships / knowledge |
| 0003 | `0003_memory_write.py` | 记忆写入路径所需列 |
| 0004 | `0004_m2_npc_attributes.py` | npc_profiles / npc_health 属性宽表 |
| 0005 | `0005_m3_knowledge_governance.py` | knowledge 治理列 |
| 0006 | `0006_m4_structures.py` | structures（建筑/结构物） |
| 0007 | `0007_m4_material_balances.py` | matter_state 材料/耐久列 |
| 0008 | `0008_m5_fork_identity.py` | 分支身份（fork identity） |
| 0009 | `0009_branches_rng_state.py` | `branches.rng_state` |
| 0010 | `0010_protected_backfill.py` | `player_anchors.protected` 回填 |
| 0011 | `0011_anchor_packages.py` | anchor_packages（存档包物化） |
| 0012 | `0012_branches_current.py` | `branches.is_current` 当前线指针 |
| 0013 | `0013_power_state.py` | npc_power（第 4 张不可重建表） |
| 0014 | `0014_fires.py` | fires（火场生命周期） |

---

## 4. 常用命令

在仓库根目录执行：

```powershell
uv run alembic upgrade head        # 升到最新
uv run alembic current             # 当前版本
uv run alembic downgrade -1        # 回滚一步
uv run alembic history             # 迁移历史
uv run alembic revision --autogenerate -m "msg"   # 自动检测模型变更
uv run alembic upgrade head --sql                 # 生成离线 SQL
```

`env.py` 读 `WORLD_DB_URL`；未设时用 `sqlite+aiosqlite:///world.db`。

---

## 5. 注意事项

- **autogenerate 只是草稿**：SQLite 的 ALTER 能力有限，涉及列改名/删除/加约束时必须手写
  `batch_alter_table`，并补 `downgrade()`。
- **不可重建表**（events / snapshots / npc_power / fires）的迁移不得丢列或改语义；
  重建能力本身是 `schema.md` 的契约，迁移只是载体。
- **不要在迁移里读写业务数据**：`0010_protected_backfill.py` 这类回填是例外，
  需在文件头说明「为什么必须在迁移期做，而不是启动期做」。
- **迁移期间停 tick**：单文件 SQLite 下长事务会阻塞写入，迁移脚本保持短小。
- **测试库独立**：API 测试用临时 sqlite（`LZ_MASTER_KEY` + tmp path），不碰开发库。
