"""长跑预压测辅助（性能域，pi）— M2-P2。

用途：驱动 TickLoop 跑「50 NPC × 万级~60 万 tick」采样段，分窗口统计
耗时/内存/GC 对象/句柄/Caches 尺寸，暴露 O(n) 累积与泄漏。

与 harness.py 的分工：harness 是单次/短基准（clock/rng/apply/perception），
本模块是**长跑采样 harness**（窗口化，只看稳态与漂移，不引入 pytest-benchmark——
长跑用真实墙钟窗口，benchmark 的 min_time 校准会与 7 日量纲冲突）。

确定性：不使用 stdlib random；mock 动作喂给器按 tick 序号确定性生成（C5）。
跨平台：内存/句柄探测按平台分支（Windows → psapi/GetProcessHandleCount；
Linux → resource）。探测失败返回 -1（不因探测不可用而误红）。
"""

from __future__ import annotations

import ctypes
import gc
import logging
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from sim.core.tick import TickLoop

DEFAULT_FRAME_S = 1.0 / 60.0
TICKS_PER_GAME_DAY = 86_400  # 与 sim/core/calendar.py 一致（1 tick = 1 游戏秒）
M2_ACCEPTANCE_TICKS = 7 * TICKS_PER_GAME_DAY  # 604,800：50 NPC × 7 游戏日


# ---------------------------------------------------------------------------
# 进程探针（内存 / 句柄）— 失败返回 -1，不误红
# ---------------------------------------------------------------------------


def _rss_linux() -> float:
    pages = int(Path("/proc/self/statm").read_text(encoding="ascii").split()[1])
    return pages * 4096 / 1048576.0  # page size 4KB（CI runner 标准）


def _rss_windows() -> float:
    from ctypes import wintypes

    class _PMC(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD),
            ("PageFaultCount", wintypes.DWORD),
            ("PeakWorkingSetSize", ctypes.c_size_t),
            ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t),
            ("PeakPagefileUsage", ctypes.c_size_t),
        ]

    k = ctypes.WinDLL("kernel32", use_last_error=True)
    ps = ctypes.WinDLL("psapi", use_last_error=True)
    k.GetCurrentProcess.restype = wintypes.HANDLE
    ps.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(_PMC), wintypes.DWORD]
    ps.GetProcessMemoryInfo.restype = wintypes.BOOL
    info = _PMC()
    info.cb = ctypes.sizeof(_PMC)
    if not ps.GetProcessMemoryInfo(k.GetCurrentProcess(), ctypes.byref(info), info.cb):
        return -1.0
    return float(info.WorkingSetSize) / 1048576.0


def is_windows() -> bool:
    return sys.platform == "win32"


def rss_mb() -> float:
    """进程常驻内存（MB）。探测不可用返回 -1。"""
    try:
        return _rss_windows() if is_windows() else _rss_linux()
    except Exception:
        return -1.0


def handle_count() -> int:
    """进程句柄数（Windows）；其他平台返回 -1（Linux 无稳定等价量）。"""
    if not is_windows():
        return -1
    try:
        from ctypes import wintypes

        k = ctypes.WinDLL("kernel32", use_last_error=True)
        k.GetCurrentProcess.restype = wintypes.HANDLE
        k.GetProcessHandleCount.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        k.GetProcessHandleCount.restype = wintypes.BOOL
        cnt = wintypes.DWORD(0)
        if not k.GetProcessHandleCount(k.GetCurrentProcess(), ctypes.byref(cnt)):
            return -1
        return int(cnt.value)
    except Exception:
        return -1


@dataclass(frozen=True)
class ProcSample:
    """一次进程采样：内存 / 句柄 / GC 对象数。"""

    rss_mb: float
    handles: int
    gc_objects: int


def sample_proc() -> ProcSample:
    return ProcSample(rss_mb=rss_mb(), handles=handle_count(), gc_objects=len(gc.get_objects()))


# ---------------------------------------------------------------------------
# 动作喂给器：mock（实现未落地的替身） / l1（真实 NpcRuntime.tick 接线）
# ---------------------------------------------------------------------------


def make_mock_feeder(
    grid_w: int = 64,
    grid_h: int = 64,
    path_len: int = 4,
    branch_id: str = "main",
) -> Callable[[TickLoop], int]:
    """构造确定性 mock 动作喂给器：让 50 NPC **持续走动**（贴近真实活跃负载）。

    返回 feeder(loop) -> 本次入队事件数。动作集对应 sim/npc/actions.py 的 `move`
    （真实路径段事件，走 apply 唯一写路径），M2 utility/runtime 落地后可替换为
    L1 决策喂给，本 harness 接口不变。

    负载保真：只给「路径耗尽」的实体补一段长 path_len 的短程路径，使任意时刻
    50 个 NPC 都在移动。若每 tick 才派一格路径，实体大部时间静止，感知的
    sound/moving 负载会远低于真实——那不是验收内核，是空转。
    路径按 (实体序号, tick) 确定性生成（C5：无 stdlib random）。
    """
    from sim.core.events import move_event

    def feeder(loop: TickLoop) -> int:
        queued = 0
        tick = loop.state.tick
        for i, entity in enumerate(loop.state.entities.values()):
            if entity.path:
                continue
            ex, ey = entity.pos
            dx = ((i + tick) % 3) - 1
            dy = ((tick // 3 + i) % 3) - 1
            if dx == 0 and dy == 0:
                dx = 1
            path = tuple(
                (
                    max(0, min(grid_w - 1, ex + round(dx * k))),
                    max(0, min(grid_h - 1, ey + round(dy * k))),
                )
                for k in range(path_len + 1)
            )
            loop.enqueue(
                move_event(
                    tick=tick + 1,
                    actor_id=entity.entity_id,
                    start=path[0],
                    goal=path[-1],
                    path=path,
                    branch_id=branch_id,
                )
            )
            queued += 1
        return queued

    return feeder


def make_l1_feeder(
    runtime,
    *,
    grid_w: int = 64,
    grid_h: int = 64,
    path_len: int = 4,
    branch_id: str = "main",
    translate: Callable[[str], bool] | None = None,
) -> Callable[[TickLoop], int]:
    """L1 决策喂给器（M2-P3）：`NpcRuntime.tick` 输出 → 内核事件。

    这是 `make_mock_feeder` 的升级版：mock 只产生「走」负载；本函数跑**真实 L1**
    （needs 推进 + 效用向量化 + 事件产出，`sim/npc/runtime.py`），把决策接线进内核。

    接线事实（M2-P3 对账）：`NpcRuntime.tick` 产出 NPC_ACT 事件，但当前
    `build_default_bus()` **未注册 `NPC_ACT` handler**（架构第三批接 tick 固定序时注册）。
    故本设计分两阶段：
    - **阶段 1（当前）**：只把内核已注册的可执行动作（`move`/`wander`）折成 MOVE 事件
      （唯一写路径 `issue_move`）；其余动作（`eat`/`rest`/`work`/`request_chat`）无 handler
      → 丢弃。**L1 的计算成本仍全量发生**（needs/效用/事件构造都跑），量到的就是真实负载。
    - **阶段 2（第三批接线）**：架构在 `TickLoop._tick_once` 预留挂载点调 `runtime.tick`
      并注册 `NPC_ACT` handler 后，本 feeder 退化为「全部入队」——把 `translate` 传
      `lambda _a: True` 即可，无需改 harness。

    契约：`runtime.profiles` 的 npc_id 必须与 `loop.state.entities` 的 id 同名（映射一致）；
    runtime 确定性、固定序（C5），本 feeder 不引入 stdlib random。
    """
    from sim.core.events import EventKind

    def feeder(loop: TickLoop) -> int:
        tick = loop.state.tick + 1
        events = runtime.tick(tick)
        enqueued = 0
        for ev in events:
            payload = ev.payload
            if ev.event_type is not EventKind.NPC_ACT:
                continue
            action = str(payload.get("action", ""))
            if action not in ("move", "wander"):
                continue  # 内核暂无该动作 handler；L1 计算已发生，不谎报事件
            npc_id = str(payload.get("npc_id", ""))
            entity = loop.state.entities.get(npc_id)
            if entity is None or entity.path:
                continue
            ex, ey = entity.pos
            # 确定性方向（仅分散落点，不涉随机语义）：由 npc_id 字符和 + tick 派生
            seed = (sum(ord(c) for c in npc_id) + tick * 7) & 0xFFFF
            dx = (seed % 3) - 1
            dy = ((seed // 3) % 3) - 1
            if dx == 0 and dy == 0:
                dx = 1
            path = tuple(
                (
                    max(0, min(grid_w - 1, ex + round(dx * k))),
                    max(0, min(grid_h - 1, ey + round(dy * k))),
                )
                for k in range(path_len + 1)
            )
            loop.issue_move(npc_id, list(path))
            enqueued += 1
        return enqueued

    return feeder


# ---------------------------------------------------------------------------
# 窗口化长跑
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class WindowStats:
    """一个采样窗口的统计（ticks 区间 + 耗时分布 + 进程量）。"""

    start_tick: int
    n_ticks: int
    mean_ms: float
    p99_ms: float
    max_ms: float
    end_rss_mb: float
    end_handles: int
    end_gc_objects: int


@dataclass
class SoakResult:
    """长跑结果：窗口序列 + 收尾状态。"""

    windows: list[WindowStats] = field(default_factory=list)
    total_ticks: int = 0
    entity_count_start: int = 0
    entity_count_end: int = 0
    pending_peak: int = 0
    cache_sizes: dict[str, int] = field(default_factory=dict)

    def means_ms(self) -> list[float]:
        return [w.mean_ms for w in self.windows]

    def p99s_ms(self) -> list[float]:
        return [w.p99_ms for w in self.windows]


def _pct(sorted_samples: list[float], q: float) -> float:
    if not sorted_samples:
        return 0.0
    idx = min(len(sorted_samples) - 1, int(len(sorted_samples) * q))
    return sorted_samples[idx]


def quiet_bench_logging() -> None:
    """压制内核对每事件打的 debug 日志（测量内核，不测 logger）。幂等。"""
    try:
        import structlog

        structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(logging.WARNING))
    except Exception:
        pass


def run_soak(
    loop: TickLoop,
    ticks: int,
    *,
    window_ticks: int = 10_000,
    feeder: Callable[[TickLoop], int] | None = None,
    frame_s: float = DEFAULT_FRAME_S,
    drain: bool = True,
    gc_collect_between_windows: bool = False,
) -> SoakResult:
    """跑 ticks 个 tick，按 window_ticks 分窗统计。

    - 每帧 `advance_frame(frame_s)` 推 1 tick（1x=60 tick/s）。
    - feeder(loop) 每帧调用（其内部按 tick 节拍决定是否入队）。
    - drain=True 时每帧 drain_events/drain_delta（模拟外层 flush，保持内存有界）。
    - gc_collect_between_windows：每窗末强制一次 gc.collect（诊断用；会略拉低下一窗耗时）。
    - 自动压制内核 debug 日志（否则 logger 开销淹没内核信号）。
    """
    quiet_bench_logging()
    result = SoakResult(entity_count_start=len(loop.state.entities))
    samples: list[float] = []
    win_start = loop.state.tick
    for _ in range(ticks):
        if feeder is not None:
            feeder(loop)
        t0 = time.perf_counter()
        loop.advance_frame(frame_s)
        samples.append(time.perf_counter() - t0)
        # 入队峰值在 drain 之前采样（drain 后恒为 0，测不到积压）
        result.pending_peak = max(result.pending_peak, len(loop.pending_events))
        if drain:
            loop.drain_events()
            loop.drain_delta()
        if loop.state.tick - win_start >= window_ticks:
            result.windows.append(_close_window(win_start, samples))
            samples = []
            win_start = loop.state.tick
            if gc_collect_between_windows:
                gc.collect()
    if samples:
        result.windows.append(_close_window(win_start, samples))
    result.total_ticks = loop.state.tick
    result.entity_count_end = len(loop.state.entities)
    return result


def _close_window(start_tick: int, samples: list[float]) -> WindowStats:
    ordered = sorted(samples)
    proc = sample_proc()
    return WindowStats(
        start_tick=start_tick,
        n_ticks=len(samples),
        mean_ms=(sum(samples) / len(samples) * 1000.0) if samples else 0.0,
        p99_ms=_pct(ordered, 0.99) * 1000.0,
        max_ms=(ordered[-1] * 1000.0) if ordered else 0.0,
        end_rss_mb=proc.rss_mb,
        end_handles=proc.handles,
        end_gc_objects=proc.gc_objects,
    )


def perception_cache_sizes() -> dict[str, int]:
    """当前感知引擎实例级缓存的尺寸（防无界累积；无引擎时返回空）。"""
    try:
        from sim.perception.senses import _RTOKEN_CACHE, _SHARED_ENGINES, _SOUND_DESC_CACHE
    except Exception:
        return {}
    sizes = {"rtoken": len(_RTOKEN_CACHE), "sound_desc": len(_SOUND_DESC_CACHE)}
    for idx, eng in enumerate(_SHARED_ENGINES.values()):
        sizes[f"los[{idx}]"] = len(eng._los_cache)
        sizes[f"walls[{idx}]"] = len(eng._walls_cache)
    return sizes
