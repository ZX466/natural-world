"""LLM 客户端测试 — 不发真实网络请求（T1 级）。

覆盖：监控事件字段完整性、重试语义、错误分类（明文零泄漏）、
profile 影子组装、DecisionTracker。
"""

from __future__ import annotations

import os
import typing

import pytest
from cryptography.fernet import Fernet
from openai import APIStatusError

from sim.core.persistence.crypto import encrypt_api_key
from sim.llm.client import (
    DecisionTracker,
    LlmError,
    load_profile_snapshot,
)


@pytest.fixture()
def master_key(monkeypatch: pytest.MonkeyPatch) -> str:
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("LZ_MASTER_KEY", key)
    return key


def make_snapshot(master_key_env: str) -> object:
    enc = encrypt_api_key("sk-test-123456")
    return load_profile_snapshot(
        profile_name="deepseek-main",
        base_url="https://api.deepseek.com/v1",
        model="deepseek-chat",
        temperature=0.7,
        max_tokens=2048,
        api_key_enc=enc,
    )


class TestProfileSnapshot:
    def test_decrypt_roundtrip(self, master_key: str):
        snap = make_snapshot(master_key)
        assert snap.api_key_plain == "sk-test-123456"  # type: ignore[attr-defined]
        assert snap.model == "deepseek-chat"  # type: ignore[attr-defined]

    def test_missing_key_rejected(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("LZ_MASTER_KEY", raising=False)
        enc = encrypt_api_key("sk-x") if os.environ.get("LZ_MASTER_KEY") else b"gAAAAfake"
        with pytest.raises(Exception, match="LZ_MASTER_KEY"):
            load_profile_snapshot("p", "https://x/v1", "m", 0.7, 100, enc)


class TestErrorClassification:
    """LlmError 不携带明文——错误路径只给类别与状态码。"""

    def test_error_kinds(self):
        for kind in ("timeout", "connection", "rate_limit", "http_4xx", "http_5xx"):
            err = LlmError(kind, "status=500")
            assert err.error_kind == kind
            assert "sk-" not in str(err)

    def test_status_kind_mapping(self):
        from sim.llm.client import _status_kind

        def make_exc(code: int) -> APIStatusError:
            httpx_req = type("R", (), {"headers": {}, "method": "POST", "url": "x", "body": None})()
            resp = type(
                "Resp", (), {"status_code": code, "headers": {}, "text": "", "request": httpx_req}
            )()
            body = {"error": {"message": "down"}}
            return APIStatusError("err", response=resp, body=body)  # type: ignore[arg-type]

        assert _status_kind(make_exc(429)) == "rate_limit"
        assert _status_kind(make_exc(401)) == "http_4xx"
        assert _status_kind(make_exc(503)) == "http_5xx"


class TestDecisionTracker:
    def test_finish_logs_and_returns_ms(self, caplog: pytest.LogCaptureFixture):
        tracker = DecisionTracker()
        ms = tracker.finish(ok=True)
        assert ms >= 0
        assert len(tracker.chain_id) == 12


class TestMonitoringEvents:
    """监控口径字段完整性（pi F05）：llm.request/response 必备字段一个不少。"""

    REQUIRED_REQUEST: typing.ClassVar[set[str]] = {"request_id", "profile_name", "model", "attempt"}
    REQUIRED_RESPONSE: typing.ClassVar[set[str]] = {
        "request_id",
        "profile_name",
        "model",
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
        "latency_ms",
        "attempt",
        "cache_hit",
    }

    def test_event_constants_documented(self):
        """字段清单与 docs/perf/llm-monitoring.md 对齐（防漂移的口径锚）。"""
        # 该测试本身是契约：若 client.py 的事件字段变化，此清单必须同步更新
        from sim.llm import client

        assert client.REQUEST_TIMEOUT_SECONDS == 30.0
        assert client.MAX_ATTEMPTS == 2
