"""M5-K11 出站权力字段闸（契约稿 `docs/api/m5-power-api.md`）。

**为什么有这个模块**：D-10 已裁「权力完全不可见」（纯 Agent 内部，协议面零改动），
codex 红线 A/B 把这条裁定的**可证伪形态**钉在「闭合枚举 + 递归禁键扫描」。但扫描是
**测试面**——它只在有人跑测试时说「这里漏了」。生产出站路径上真正需要的是一道
**机械闸**：任何出站体在离开进程前递归剥除禁键，并把剥除事实**留痕**（静默丢字段
等于制造新的不可见 bug——牙齿的表达会无声消失，且没人知道）。

**接在哪**：WS 侧 `ConnectionManager._send_to`（`sim/api/ws.py`）——那是**全部** WS
出站帧的唯一咽喉（广播 / 定向 / 订阅者投递三面共用）。HTTP 侧不另装中间件：全部
`/api` 路由都声明了 `response_model`，FastAPI 按其序列化 ⇒ 未声明字段不可能出现
（结构性密封，钉子见 `sim/tests/test_m5_power_api.py::TestHttpSurfaceSeal`）。

**键集纪律**：本模块有**两层禁键**，**同一递归一起扫**（不分两套扫描——两套扫描意味着
「只扫了其中一层」的漏洞，正是 F-1 那类缺口的成因）：

| 层 | 常量 | 判层一句话 |
|---|---|---|
| 权力 | `AUTHORITY_FORBIDDEN_KEYS` | D-10 权力不可见，结构层不许有该键 |
| 随机流 | `RANDOM_STATE_FORBIDDEN_KEYS` | seed/熵材料/抽签进度零出网关（W-C1） |

- 权力层依据：codex 红线 B 键级资产**同源**（`m5-authority-criteria-preplan.md` §3）。
- 随机流层依据：**以 `rng_state.py` / `rng.py` / 0009 迁移的真源字段为准**（S11 F-1）。

两层都**只增不减**；权力层改动须与 codex 同 CR（钉 `test_key_set_matches_codex_redline_b`），
随机流层改动须与真源字段对拍（钉 `test_random_state_keys_trace_to_source_of_truth`）——
**任何一层都不得自造一套不在真源里的键**（防第二套）。

**异常纪律**：`OutboundAuthorityLeak` 是**开发期自检**异常，**不得**注册为 HTTP 机器码
或 WS 错误码——那会让「权力/随机流存在」本身变成一个对外可观测信号（反向违反 D-10 与 W-C1）。
"""

from __future__ import annotations

from typing import Any

import structlog

logger = structlog.get_logger(__name__)

#: 键级禁键集（codex 红线 B 同源资产；只增不减，改动须同 CR）。
#: 判层说明：键名是**结构层**的场（§19.3 词面管不到），D-10 裁不可见 ⇒ 键都不该存在。
AUTHORITY_FORBIDDEN_KEYS: frozenset[str] = frozenset(
    {
        "authority",
        "power",
        "rank",
        "authority_level",
        "power_level",
        "dominance",
        "prestige",
        "influence",
        "authority_score",
    }
)

#: 随机流状态键（**真源派生**，S11 F-1；钉 `test_random_state_keys_trace_to_source_of_truth`
#: 逐键回溯到真源文件，防第二套）。逐键出处：
#: - `rng_state` —— `0009_branches_rng_state.py:34` 的 `branches.rng_state` 列名
#:   （也是 `capture_rng_state` 产物这个概念在代码里的键名）；
#: - `rng_state_persisted` —— `fork.py::ForkResult` 的布尔字段（**存在性**元信息：
#:   回它等于告诉玩家「系统维护着随机流状态」，不漏数值但仍是元信息）；
#: - `world_seed` —— `rng.py:32` `RngRegistry.world_seed`；
#: - `materials` —— `rng.py:34` `RngRegistry.materials`（熵材料，W-C1 明列零出站）；
#: - `bit_generator` / `has_uint32` / `uinteger` —— numpy PCG64 `bit_generator.state`
#:   的顶层键（**实测** `numpy.random.default_rng().bit_generator.state`），抽签进度段。
#:
#: **刻意排除的真源键（防误伤，理由写死）**：状态包里的通用容器/短键
#: `v` / `registry` / `streams` / `key` / `state` / `inc` —— 它们在协议语境里可能是合法字段
#: （剥掉叫 `state` 的合法字段 = 静默丢数据，比漏扫更坏）；而它们的内容已被上面那些
#: **特异叶子键**兜住（`rng_state` 段里必有 `world_seed`/`bit_generator`）。
RANDOM_STATE_FORBIDDEN_KEYS: frozenset[str] = frozenset(
    {
        "rng_state",
        "rng_state_persisted",
        "world_seed",
        "materials",
        "bit_generator",
        "has_uint32",
        "uinteger",
    }
)

#: 红线别名（W-C1「seed/熵值零出站」的**简称**形式）。它们**不是**真源字段名，
#: 但同属同一泄漏面（有人把 `seed`/`rng` 直接塞进帧就是漏），故一并纳入；
#: 钉子会把「真源派生」与「红线别名」分开断言，防止别名层无限膨胀（见测试模块说明）。
RANDOM_STATE_ALIAS_KEYS: frozenset[str] = frozenset({"seed", "rng", "entropy", "entropy_state"})

#: 单一扫描集 = 两层并集（**同一递归**用它；不要为某层另写一趟扫描）。
OUTBOUND_FORBIDDEN_KEYS: frozenset[str] = (
    AUTHORITY_FORBIDDEN_KEYS | RANDOM_STATE_FORBIDDEN_KEYS | RANDOM_STATE_ALIAS_KEYS
)

#: 剥除留痕（进程内环形无关的追加列表，测试与排障读它；生产只当观测信号）。
_LEAK_EVENTS: list[str] = []


class OutboundAuthorityLeak(RuntimeError):
    """出站体含禁键——**自检面**用异常（`assert_outbound_clean`）。

    ⚠ 不得注册进 `_TYPE_TITLE` / WS 错误码词表：权力/随机流不可见 ⇒ 连「泄漏了」这个
    错误码都不该出现在对外面（钉子 `test_no_authority_exception_leaks_into_http_errors`）。
    """


def layer_of(key: str) -> str:
    """禁键所属层（`authority` / `random_state` / `authority+random_state`）——留痕用。"""
    lowered = key.lower()
    layers = []
    if lowered in AUTHORITY_FORBIDDEN_KEYS:
        layers.append("authority")
    if lowered in RANDOM_STATE_FORBIDDEN_KEYS | RANDOM_STATE_ALIAS_KEYS:
        layers.append("random_state")
    return "+".join(layers) or "unknown"


def _is_forbidden(key: Any) -> bool:
    return isinstance(key, str) and key.lower() in OUTBOUND_FORBIDDEN_KEYS


def find_forbidden_keys(obj: Any) -> list[str]:
    """递归收集出站体里的**两层**禁键名（去重、排序）。大小写不敏感。

    这是**唯一**的键名扫描入口（两层共用一趟递归——见模块 docstring「键集纪律」）。
    """
    found: set[str] = set()

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if _is_forbidden(key):
                    found.add(str(key).lower())
                walk(value)
        elif isinstance(node, (list, tuple)):
            for item in node:
                walk(item)

    walk(obj)
    return sorted(found)


def find_authority_keys(obj: Any) -> list[str]:
    """只报**权力层**命中（K11 接口保留；出站闸实际用的是两层合并的 `find_forbidden_keys`）。"""
    return sorted(k for k in find_forbidden_keys(obj) if layer_of(k) == "authority")


def find_random_state_keys(obj: Any) -> list[str]:
    """只报**随机流层**命中（S11 F-1 新增，供钉子与排障按层取证）。"""
    return sorted(k for k in find_forbidden_keys(obj) if "random_state" in layer_of(k))


def find_forbidden_paths(obj: Any) -> list[str]:
    """递归收集禁键的**路径**（`$.actors[0].authority`），用于日志与异常信息。"""
    paths: list[str] = []

    def walk(node: Any, prefix: str) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                here = f"{prefix}.{key}"
                if _is_forbidden(key):
                    paths.append(here)
                walk(value, here)
        elif isinstance(node, (list, tuple)):
            for index, item in enumerate(node):
                walk(item, f"{prefix}[{index}]")

    walk(obj, "$")
    return paths


def find_authority_paths(obj: Any) -> list[str]:
    """K11 接口保留（同 `find_authority_keys`：两层扫描，但函数名沿用旧称）。"""
    return find_forbidden_paths(obj)


def strip_outbound_forbidden(obj: Any) -> tuple[Any, list[str]]:
    """递归剥除**两层**禁键，返回 ``(净化后的体, 被剥路径)``。

    **纯函数**：不就地改入参（出站构造点常复用同一份 dict，就地掏空会把调用方的世界
    状态一起改没）；不可变标量与同层非禁键字段原样保留。
    """
    stripped: list[str] = []

    def walk(node: Any, prefix: str) -> Any:
        if isinstance(node, dict):
            clean: dict[Any, Any] = {}
            for key, value in node.items():
                here = f"{prefix}.{key}"
                if _is_forbidden(key):
                    stripped.append(here)
                    continue
                clean[key] = walk(value, here)
            return clean
        if isinstance(node, list):
            return [walk(item, f"{prefix}[{index}]") for index, item in enumerate(node)]
        if isinstance(node, tuple):
            return tuple(walk(item, f"{prefix}[{index}]") for index, item in enumerate(node))
        return node

    return walk(obj, "$"), stripped


def strip_authority_fields(obj: Any) -> tuple[Any, list[str]]:
    """K11 接口保留（现在**含随机流层**，S11 F-1）——新代码用 `strip_outbound_forbidden`。"""
    return strip_outbound_forbidden(obj)


def assert_outbound_clean(obj: Any) -> None:
    """自检面：出站体含禁键即抛 `OutboundAuthorityLeak`（含命中路径与层）。"""
    paths = find_forbidden_paths(obj)
    if paths:
        layers = sorted({layer_of(path.rsplit(".", 1)[-1]) for path in paths})
        raise OutboundAuthorityLeak(f"出站体含禁键（D-10/W-C1 不可见面，层={layers}）：{paths}")


def record_outbound_leak(paths: list[str]) -> None:
    """记录一次剥除事实（出站咽喉调用）。

    **留痕而非静默**：出站面出现禁键本身就是缺陷（谁放的），剥除只是止血；没有记录
    就等于把「牙齿表达被无声吞掉」变成新的不可见 bug。
    """
    _LEAK_EVENTS.extend(paths)
    layers = sorted({layer_of(path.rsplit(".", 1)[-1]) for path in paths})
    logger.warning(
        "outbound.forbidden_fields_stripped", paths=paths, count=len(paths), layers=layers
    )


def leak_events() -> list[str]:
    """已记录的剥除路径（副本）。"""
    return list(_LEAK_EVENTS)


def reset_leak_events() -> None:
    """清空剥除记录（测试隔离用）。"""
    _LEAK_EVENTS.clear()
