"""structlog 全局装配 — redact_sensitive 第二道防线（K8，C06-④ 顺手项）。

K4/K8：任何日志链路的最后一步都是脱敏。测试里 structlog.configure 已有
局部用法；生产入口（api/main lifespan）必须调用 setup_logging() 一次。
"""

from __future__ import annotations

import structlog

from sim.core.persistence.crypto import redact_sensitive


def setup_logging() -> None:
    """挂脱敏 processor 进全局链（幂等：重复调用只覆盖同一配置）。"""
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            redact_sensitive,  # K8：敏感键值 → ***（明文密钥/兜底防线）
            structlog.processors.StackInfoRenderer(),
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(20),  # INFO+
        cache_logger_on_first_use=True,
    )
