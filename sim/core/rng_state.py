"""RNG 状态包：捕获 / 承接（读档 = 分叉的随机连续性，预研稿 §6.3 断言 D）

**为什么需要它**：确定性混沌（DESIGN §11）要求「同一 seed + 同一事件序列 → 逐位一致」。
读档 = 分叉把世界线劈成两条，若子分支的随机流**从头开始**，接缝处就会出现行为跳变
（同一 tick 同一 NPC 做出不同选择），T2 的逐位一致当场破。所以分叉点两侧必须**承接
抽签进度**，而不只是承接 seed。

**本模块提供的**（纯函数，无 I/O、无 schema）：

- ``capture_rng_state(registry, cache, streams)`` → JSON 字符串：``RngRegistry`` 快照
  （含熵注入后的 ``materials``）+ 每个活跃流的 **PCG64 抽签状态**；
- ``restore_rng_state(blob, cache, streams)`` → 重建 ``RngRegistry`` 并把抽签状态装回
  ``cache``，使**后续抽签逐位一致**。

**为什么不能只存一个 seed**（裁 26 的 (a) 方案，实测证据）：``RngRegistry`` 只记
``world_seed`` 与熵材料，**抽签进度活在调用方持有的 ``np.random.Generator`` 里**
（``RngRegistry.generator(name, cache)``）。只承接 registry 而不承接进度，后续抽签
必然与父分支不同 ⇒ 接缝跳变。除非「重放父分支全部抽签」来推导进度——那要求抽签调用
顺序可离线复现，脆弱且 O(抽签数)。D3-c 钉子 ``test_D_seed_only_resume_diverges``
把这条钉成二阶守卫（防将来退化成 seed 语义）。

**落库形态待裁**（Claude 裁 26 的 (a)/(b)）：本模块只管「状态包 ↔ 字典」，
``fork_from_anchor(rng_state=...)`` 透明透传，**不落库**（``ForkResult.rng_state_persisted
恒为 False``）。建议 (b)：把本字符串写进 ``branches.rng_state``（一支 add_column 的
0009），在 fork 事务内原子落——实测体积 ≈**198 B/流**（5 流 991 B JSON），可忽略。
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any, Final

import numpy as np

from sim.core.rng import RngRegistry

#: 状态包版本。未知版本一律 fail-closed（对照 `advance_build` 的 UnknownBuildRuleError：
#: **绝不回落**到旧解析）。
RNG_STATE_VERSION: Final[int] = 1


class RngStateError(ValueError):
    """RNG 状态包不合法（坏 JSON / 未知版本 / 材料指纹不匹配）——fail-closed，不静默续跑。"""


def capture_rng_state(
    registry: RngRegistry,
    cache: Mapping[str, np.random.Generator],
    streams: Sequence[str],
) -> str:
    """捕获 RNG 状态包（JSON 字符串）。

    Args:
        registry: 当前 ``RngRegistry``（含熵注入后的 ``materials``）。
        cache: ``RngRegistry.generator(name, cache)`` 用的生成器缓存（键 = 材料指纹）。
        streams: 调用方**当前用到的流名**（缓存键是材料指纹，反推不出流名，故由调用方给）。
            从未抽过签的流直接跳过——恢复时它会按材料新建生成器，语义正确。

    Returns:
        ``{"v": 1, "registry": {...}, "streams": {name: {"key": 指纹, "state": {...}}}}``
    """
    payload: dict[str, Any] = {
        "v": RNG_STATE_VERSION,
        "registry": registry.model_dump(mode="json"),
        "streams": {},
    }
    for name in streams:
        key = registry.draw_key(name)
        gen = cache.get(key)
        if gen is None:
            continue
        payload["streams"][name] = {
            "key": key,
            "state": json.loads(json.dumps(gen.bit_generator.state)),
        }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def restore_rng_state(
    blob: str,
    cache: dict[str, np.random.Generator],
    streams: Sequence[str],
) -> RngRegistry:
    """从状态包恢复 ``RngRegistry`` 并把抽签状态装回 ``cache``（后续抽签逐位一致）。

    Args:
        blob: ``capture_rng_state`` 的输出。
        cache: 目标生成器缓存（**调用方持有**；函数会就地填充）。
        streams: 参与恢复的流名（与捕获时一致）。

    Raises:
        RngStateError: 坏 JSON / 未知版本 / 恢复出的 registry 与保存的材料指纹不匹配。
    """
    try:
        payload = json.loads(blob)
    except json.JSONDecodeError as exc:
        raise RngStateError(f"RNG 状态包不是合法 JSON: {exc}") from exc
    version = payload.get("v")
    if version != RNG_STATE_VERSION:
        raise RngStateError(f"RNG 状态包版本未知: {version!r}（当前 {RNG_STATE_VERSION}）")
    try:
        registry = RngRegistry(**payload["registry"])
    except (KeyError, TypeError) as exc:
        raise RngStateError(f"RNG 状态包 registry 段不合法: {exc}") from exc

    saved_streams = payload.get("streams") or {}
    for name in streams:
        entry = saved_streams.get(name)
        if not isinstance(entry, dict):
            continue
        expected_key = entry.get("key")
        actual_key = registry.draw_key(name)
        if expected_key != actual_key:
            raise RngStateError(
                f"流 {name!r} 材料指纹不匹配（状态包 {expected_key!r} ≠ 恢复后 {actual_key!r}）"
                "——registry 与抽签状态不是同一条线上的，拒绝续跑"
            )
        gen = registry.generator(name, cache)
        state = entry.get("state")
        if not isinstance(state, dict):
            raise RngStateError(f"流 {name!r} 抽签状态段不合法: {state!r}")
        gen.bit_generator.state = state
    return registry
