"""sqlite-vec 向量索引（npc_memory_vec）— schema.md §6。

设计说明：
- ``npc_memory_vec`` 是 sqlite-vec 的 **vec0 虚拟表**，维度在 M3 embedding model
  选定后才锁定（见 schema.md §6 注：384 或 768）。docs/data/migration.md 明确
  虚拟表 DDL 在 Alembic 范围之外（需先 ``LOAD EXTENSION``）——故本模块提供
  显式初始化函数，由 M3 接线时调用，不放进 0002 迁移。
- 维度通过参数/常量传入；本 M1 阶段只提供脚手架 + 建表能力与测试。
"""

from __future__ import annotations

import sqlite3
from typing import Final

# embedding model 锁定后改这里（schema.md §6：384 或 768）
DEFAULT_EMBEDDING_DIM: Final[int] = 384

VEC_TABLE: Final[str] = "npc_memory_vec"


def load_sqlite_vec(conn: sqlite3.Connection) -> None:
    """在同步 sqlite3 连接上加载 sqlite-vec 扩展。

    需要连接允许扩展加载（``enable_load_extension(True)``）。
    """
    import sqlite_vec

    conn.enable_load_extension(True)
    try:
        sqlite_vec.load(conn)
    finally:
        conn.enable_load_extension(False)


def create_memory_vec_table(conn: sqlite3.Connection, dim: int = DEFAULT_EMBEDDING_DIM) -> None:
    """创建 ``npc_memory_vec`` vec0 虚拟表（幂等：IF NOT EXISTS）。

    Args:
        conn: 已加载 sqlite-vec 扩展的同步连接。
        dim: embedding 维度（固定，sqlite-vec 要求）。
    """
    conn.enable_load_extension(True)
    try:
        import sqlite_vec

        sqlite_vec.load(conn)
        conn.execute(
            f"CREATE VIRTUAL TABLE IF NOT EXISTS {VEC_TABLE} USING vec0("
            f"embedding FLOAT32[{dim}]"
            f")"
        )
        conn.commit()
    finally:
        conn.enable_load_extension(False)


def memory_vec_exists(conn: sqlite3.Connection) -> bool:
    """检查 npc_memory_vec 虚拟表是否已存在。"""
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (VEC_TABLE,),
    ).fetchone()
    return row is not None
