"""分流 RNG — 可逐位重放的随机源（m0-core.md §2）。

- 每子系统独立流，流间互不影响；新增调用点不会改变其他流的抽签序列。
- 基础流材料是 (world_seed, stream_name) 的纯函数 → 不落快照也天然可重建。
- 重定种子（熵注入）后的材料进快照/由事件重放重建（C5）。
- 业务代码禁 `import random`（ruff banned-api 强制）。
"""

from __future__ import annotations

import hashlib

import numpy as np
from pydantic import BaseModel, ConfigDict

_SEED_BYTES = 16  # PCG64 用 128bit 种子


def _sha256_int(data: bytes) -> int:
    return int.from_bytes(hashlib.sha256(data).digest()[:_SEED_BYTES], "big")


def _base_material(world_seed: int, name: str) -> bytes:
    return hashlib.sha256(f"{world_seed}:{name}".encode()).digest()


class RngRegistry(BaseModel):
    """分流 RNG 注册表。frozen：reseed 返回新实例（不可变模式）。"""

    model_config = ConfigDict(frozen=True)

    world_seed: int
    # name → hex(重定种子后的材料)。仅记录被熵注入过的流；未注入流按纯函数重建。
    materials: dict[str, str] = {}

    def _material(self, name: str) -> bytes:
        stored = self.materials.get(name)
        if stored is not None:
            return bytes.fromhex(stored)
        return _base_material(self.world_seed, name)

    def reseed(self, name: str, entropy: bytes) -> RngRegistry:
        """熵注入：材料哈希链推进。重放时以同一熵重跑同一调用即逐位一致。"""
        new_material = hashlib.sha256(self._material(name) + entropy).digest()
        return self.model_copy(update={"materials": {**self.materials, name: new_material.hex()}})

    def draw_key(self, name: str) -> str:
        """流的当前材料指纹 — 作为抽签状态缓存的键（缓存归 TickContext，不入快照）。"""
        return hashlib.sha256(self._material(name)).hexdigest()

    def generator(self, name: str, cache: dict[str, np.random.Generator]) -> np.random.Generator:
        """取流生成器。cache 由调用方持有并跨 tick 复用（保存抽签进度）。"""
        key = self.draw_key(name)
        gen = cache.get(key)
        if gen is None:
            gen = np.random.Generator(np.random.PCG64(_sha256_int(self._material(name))))
            cache[key] = gen
        return gen
