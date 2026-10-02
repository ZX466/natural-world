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

**键集纪律**：`AUTHORITY_FORBIDDEN_KEYS` 与 codex 红线 B 的键级资产
（`docs/security/m5-authority-criteria-preplan.md` §3）**同源**，只增不减；两侧任一
改动必须同 CR（钉子 `test_key_set_matches_codex_redline_b` 会在漂移时报红）。
键级判层 ≠ 词级判层（`BANNED_WORDS` 管叙事文本），两者互补不重复。

**异常纪律**：`OutboundAuthorityLeak` 是**开发期自检**异常，**不得**注册为 HTTP 机器码
或 WS 错误码——那会让「权力存在」本身变成一个对外可观测信号（反向违反 D-10）。
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

#: 剥除留痕（进程内环形无关的追加列表，测试与排障读它；生产只当观测信号）。
_LEAK_EVENTS: list[str] = []


class OutboundAuthorityLeak(RuntimeError):
    """出站体含禁键——**自检面**用异常（`assert_outbound_clean`）。

    ⚠ 不得注册进 `_TYPE_TITLE` / WS 错误码词表：权力不可见 ⇒ 连「权力泄漏」这个
    错误码都不该出现在对外面（钉子 `test_no_authority_exception_leaks_into_http_errors`）。
    """


def _is_forbidden(key: Any) -> bool:
    return isinstance(key, str) and key.lower() in AUTHORITY_FORBIDDEN_KEYS


def find_authority_keys(obj: Any) -> list[str]:
    """递归收集出站体里的禁键名（去重、排序）。大小写不敏感。"""
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


def find_authority_paths(obj: Any) -> list[str]:
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


def strip_authority_fields(obj: Any) -> tuple[Any, list[str]]:
    """递归剥除禁键，返回 ``(净化后的体, 被剥路径)``。

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


def assert_outbound_clean(obj: Any) -> None:
    """自检面：出站体含禁键即抛 `OutboundAuthorityLeak`（含命中路径）。"""
    paths = find_authority_paths(obj)
    if paths:
        raise OutboundAuthorityLeak(f"出站体含权力禁键（D-10 不可见面）：{paths}")


def record_outbound_leak(paths: list[str]) -> None:
    """记录一次剥除事实（出站咽喉调用）。

    **留痕而非静默**：出站面出现禁键本身就是缺陷（谁放的），剥除只是止血；没有记录
    就等于把「牙齿表达被无声吞掉」变成新的不可见 bug。
    """
    _LEAK_EVENTS.extend(paths)
    logger.warning("outbound.authority_fields_stripped", paths=paths, count=len(paths))


def leak_events() -> list[str]:
    """已记录的剥除路径（副本）。"""
    return list(_LEAK_EVENTS)


def reset_leak_events() -> None:
    """清空剥除记录（测试隔离用）。"""
    _LEAK_EVENTS.clear()
