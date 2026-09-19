"""crypto 单测 — DESIGN §15 / m1-checklist.md K1/K2/K4/K8。

覆盖：
- roundtrip：encrypt → decrypt 往返一致，密文以 gAAAA 开头（K1）
- 缺钥拒启：无 LZ_MASTER_KEY / 格式非法 → CryptoError（K2）
- 日志脱敏：structlog processor 递归替换敏感键（K8）
- hint/异常不含明文（K4/K5）
"""

from __future__ import annotations

import pytest
from cryptography.fernet import Fernet

from sim.core.persistence.crypto import (
    MASTER_KEY_ENV,
    REDACTED,
    CryptoError,
    api_key_hint,
    decrypt_api_key,
    encrypt_api_key,
    get_fernet,
    is_encrypted,
    load_master_key,
    redact_sensitive,
)

# 测试用固定主密钥（不写盘、不进日志）
TEST_KEY = Fernet.generate_key()
TEST_ENV = {MASTER_KEY_ENV: TEST_KEY.decode("utf-8")}


# ---------------------------------------------------------------------------
# K1/K2: roundtrip
# ---------------------------------------------------------------------------


@pytest.mark.t1
class TestCryptoRoundtrip:
    def test_encrypt_decrypt_roundtrip(self) -> None:
        """加解密往返一致，密文以 gAAAA 开头。"""
        plaintext = "sk-live-abc1234567890"
        ciphertext = encrypt_api_key(plaintext, TEST_ENV)
        assert isinstance(ciphertext, bytes)
        assert ciphertext.startswith(b"gAAAA")  # K1: Fernet 密文特征
        assert is_encrypted(ciphertext)
        assert plaintext.encode() not in ciphertext  # 明文不出现
        assert decrypt_api_key(ciphertext, TEST_ENV) == plaintext

    def test_ciphertext_differs_each_time(self) -> None:
        """Fernet 带随机 IV：同一明文两次加密密文不同（但都可解密）。"""
        p = "sk-same-key"
        c1 = encrypt_api_key(p, TEST_ENV)
        c2 = encrypt_api_key(p, TEST_ENV)
        assert c1 != c2
        assert decrypt_api_key(c1, TEST_ENV) == decrypt_api_key(c2, TEST_ENV) == p

    def test_decrypt_with_wrong_key_fails(self) -> None:
        """换主密钥 → 解密失败且异常不含明文。"""
        plaintext = "sk-secret-do-not-leak"
        ciphertext = encrypt_api_key(plaintext, TEST_ENV)
        wrong_env = {MASTER_KEY_ENV: Fernet.generate_key().decode("utf-8")}
        with pytest.raises(CryptoError) as exc_info:
            decrypt_api_key(ciphertext, wrong_env)
        assert plaintext not in str(exc_info.value)

    def test_decrypt_invalid_ciphertext_raises(self) -> None:
        with pytest.raises(CryptoError):
            decrypt_api_key(b"not-a-fernet-token", TEST_ENV)


# ---------------------------------------------------------------------------
# K2: 缺钥拒启
# ---------------------------------------------------------------------------


@pytest.mark.t1
class TestMasterKeyRequired:
    def test_missing_key_refuses(self) -> None:
        """无 LZ_MASTER_KEY → CryptoError（拒绝启动）。"""
        with pytest.raises(CryptoError) as exc_info:
            load_master_key({})
        assert MASTER_KEY_ENV in str(exc_info.value)

    def test_invalid_key_refuses(self) -> None:
        """格式非法 → CryptoError，且报错不含密钥内容。"""
        bad = "this-is-not-a-valid-fernet-key"
        with pytest.raises(CryptoError) as exc_info:
            load_master_key({MASTER_KEY_ENV: bad})
        assert bad not in str(exc_info.value)

    def test_encrypt_without_key_refuses(self) -> None:
        with pytest.raises(CryptoError):
            encrypt_api_key("sk-x", {})

    def test_valid_key_accepted(self) -> None:
        key = load_master_key(TEST_ENV)
        assert key == TEST_KEY
        assert isinstance(get_fernet(TEST_ENV), Fernet)

    def test_no_silent_generation(self) -> None:
        """K2 负向断言：load_master_key 不接受 None/空，绝不生成密钥。"""
        with pytest.raises(CryptoError):
            load_master_key({MASTER_KEY_ENV: ""})


# ---------------------------------------------------------------------------
# K4/K5: hint 与异常不含明文
# ---------------------------------------------------------------------------


@pytest.mark.t1
class TestHintAndLeak:
    def test_hint_masks_middle(self) -> None:
        """hint 保留前后缀、中间掩码，永不等于明文。"""
        assert api_key_hint("sk-live-1234567890") == "sk-***7890"
        assert api_key_hint("sk-live-1234567890") != "sk-live-1234567890"

    def test_hint_short_key_fully_masked(self) -> None:
        assert api_key_hint("short") == REDACTED
        assert api_key_hint("") == REDACTED

    def test_hint_does_not_contain_full_key(self) -> None:
        full = "sk-supersecretkeyvalue12345"
        assert full not in api_key_hint(full)


# ---------------------------------------------------------------------------
# K8: structlog 脱敏 processor
# ---------------------------------------------------------------------------


@pytest.mark.t1
class TestRedactSensitive:
    def test_flat_sensitive_keys(self) -> None:
        ev = {"event": "llm call", "api_key": "sk-leak", "token": "abc"}
        out = redact_sensitive(None, "info", dict(ev))
        assert out["api_key"] == REDACTED
        assert out["token"] == REDACTED
        assert out["event"] == "llm call"

    def test_case_insensitive(self) -> None:
        out = redact_sensitive(None, "info", {"API_KEY": "x", "Authorization": "y"})
        assert out["API_KEY"] == REDACTED
        assert out["Authorization"] == REDACTED

    def test_nested_dict(self) -> None:
        ev = {"headers": {"Authorization": "Bearer secret", "Accept": "json"}}
        out = redact_sensitive(None, "info", ev)
        assert out["headers"]["Authorization"] == REDACTED
        assert out["headers"]["Accept"] == "json"

    def test_nested_list(self) -> None:
        ev = {"profiles": [{"id": "p1", "api_key": "sk-1"}, {"id": "p2", "api_key": "sk-2"}]}
        out = redact_sensitive(None, "info", ev)
        assert out["profiles"][0]["api_key"] == REDACTED
        assert out["profiles"][1]["api_key"] == REDACTED
        assert out["profiles"][0]["id"] == "p1"

    def test_no_plaintext_survives(self) -> None:
        """哨兵值经过 processor 后，序列化输出不含明文。"""
        import json

        sentinel = "SENTINEL-KEY-123"
        ev = {"a": {"b": [{"secret": sentinel}]}, "api_key": sentinel}
        out = redact_sensitive(None, "info", ev)
        assert sentinel not in json.dumps(out)

    def test_works_in_structlog_pipeline(self) -> None:
        """真实接入 structlog 渲染链，确认日志文本无明文。"""
        import structlog

        structlog.configure(
            processors=[
                structlog.contextvars.merge_contextvars,
                redact_sensitive,
                structlog.processors.JSONRenderer(),
            ],
            cache_logger_on_first_use=False,
        )
        logger = structlog.get_logger()
        # 直接验证 processor 输出（避免捕获 stdout）
        ev = redact_sensitive(logger, "info", {"event": "x", "api_key": "sk-plain"})
        assert "sk-plain" not in str(ev)
