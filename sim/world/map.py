"""瓦片地图 — chunk 化 + 碰撞（m0-core.md §6）。

M0 地图是静态资产（Tiled JSON → 构建期转内部格式），不进世界状态快照；
chunk 结构为 M3 可变底座预留（tile_changed → chunk.dirty → 寻路缓存失效）。
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

CHUNK_SIZE = 16  # 瓦片/chunk，边长


class Chunk(BaseModel):
    """16×16 瓦片块。ground/collision 均为扁平行主序数组。"""

    model_config = ConfigDict(frozen=True)

    cx: int
    cy: int
    ground: tuple[int, ...]
    collision: tuple[bool, ...]

    def is_walkable(self, lx: int, ly: int) -> bool:
        """chunk 内局部坐标可通行性。越界 = 不可通行。"""
        if not (0 <= lx < CHUNK_SIZE and 0 <= ly < CHUNK_SIZE):
            return False
        return self.collision[ly * CHUNK_SIZE + lx]


class TileMap(BaseModel):
    """整图。M0 单张小镇图。"""

    model_config = ConfigDict(frozen=True)

    width: int
    height: int
    tile_size: int = 16
    chunks: dict[tuple[int, int], Chunk] = Field(default_factory=dict)

    @property
    def chunks_x(self) -> int:
        return (self.width + CHUNK_SIZE - 1) // CHUNK_SIZE

    @property
    def chunks_y(self) -> int:
        return (self.height + CHUNK_SIZE - 1) // CHUNK_SIZE

    def chunk_of(self, x: int, y: int) -> tuple[int, int]:
        return (x // CHUNK_SIZE, y // CHUNK_SIZE)

    def in_bounds(self, x: int, y: int) -> bool:
        return 0 <= x < self.width and 0 <= y < self.height

    def is_walkable(self, x: int, y: int) -> bool:
        """全局坐标可通行性。越界或碰撞 = False。"""
        if not self.in_bounds(x, y):
            return False
        chunk = self.chunks.get(self.chunk_of(x, y))
        if chunk is None:
            return False
        return chunk.is_walkable(x % CHUNK_SIZE, y % CHUNK_SIZE)

    def dirty_chunks(self) -> list[tuple[int, int]]:
        """M3 预留接口占位：M0 chunk frozen 无 dirty 标记，恒空。"""
        return []

    @classmethod
    def from_json_file(cls, path: Path) -> TileMap:
        """加载内部格式 JSON（Tiled → 内部格式由构建期脚本转换，见 sim/content）。"""
        data = json.loads(path.read_text(encoding="utf-8"))
        chunks = {
            (int(cx), int(cy)): Chunk(
                cx=int(cx),
                cy=int(cy),
                ground=tuple(c["ground"]),
                collision=tuple(bool(b) for b in c["collision"]),
            )
            for (cx, cy), c in data["chunks"].items()
        }
        return cls(
            width=int(data["width"]),
            height=int(data["height"]),
            tile_size=int(data.get("tile_size", 16)),
            chunks=chunks,
        )
