"""瓦片地图 — chunk 化 + 碰撞（m0-core.md §6）。

M0 地图是静态资产（Tiled JSON → 构建期转内部格式），不进世界状态快照；
chunk 结构为 M3 可变底座预留（tile_changed → chunk.dirty → 寻路缓存失效）。
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr

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
    #: M3 脏 chunk 集（tile_changed/matter 定位事件标脏 → 寻路缓存失效）。
    #: PrivateAttr：frozen 几何不可变，脏标记是瞬时失效状态、不进世界态快照。
    _dirty: set[tuple[int, int]] = PrivateAttr(default_factory=set)

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
        """当前脏 chunk 列表（字典序排序，确定性；空 = 无待失效）。"""
        return sorted(self._dirty)

    def mark_tile_dirty(self, x: int, y: int) -> tuple[int, int]:
        """标记全局坐标所在 chunk 脏。返回 chunk 坐标（界外不标，返回哨兵）。"""
        if not self.in_bounds(x, y):
            return (-1, -1)
        chunk = self.chunk_of(x, y)
        self._dirty.add(chunk)
        return chunk

    def mark_chunk_dirty(self, chunk: tuple[int, int]) -> None:
        """直接标记 chunk 脏。"""
        self._dirty.add(chunk)

    def drain_dirty(self) -> list[tuple[int, int]]:
        """取出并清空脏集（寻路失效消费后调用）。返回排序列表。"""
        out = sorted(self._dirty)
        self._dirty.clear()
        return out

    def with_collision(self, x: int, y: int, walkable: bool) -> TileMap:
        """不可变更新单格碰撞，新实例携带该 chunk 脏标记（M3 可变底座）。

        model_copy 会共享 PrivateAttr 集合——新实例换独立集再标脏，
        避免新旧图脏标记串扰。
        """
        if not self.in_bounds(x, y):
            msg = f"坐标越界: ({x}, {y})"
            raise ValueError(msg)
        key = self.chunk_of(x, y)
        chunk = self.chunks[key]
        lx, ly = x % CHUNK_SIZE, y % CHUNK_SIZE
        col = list(chunk.collision)
        col[ly * CHUNK_SIZE + lx] = walkable
        new_chunk = chunk.model_copy(update={"collision": tuple(col)})
        new = self.model_copy(update={"chunks": {**self.chunks, key: new_chunk}})
        object.__setattr__(new, "_dirty", {key})
        return new

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
