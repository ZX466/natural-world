"""LLM api_key 加密链路 — DESIGN §15 / docs/security/m1-checklist.md K1/K2/K4/K8。

主密钥来源：环境变量 ``LZ_MASTER_KEY``（32 字节 url-safe base64，Fernet 格式）。
缺失/格式非法时 **拒绝启动**（抛 CryptoError），禁止静默生成后写盘（K2）。

落库约定（K1）：
- ``LLMProfile.api_key_enc`` 只存 Fernet 密文（以 ``gAAAA`` 开头）。
- 明文 api_key 永不落盘、永不进日志/异常（K4）。

脱敏（K8）：提供 structlog processor ``redact_sensitive``，对
``api_key`` / ``authorization`` / ``token`` / ``secret`` 等键（大小写不敏感、
递归嵌套 dict/list）做 ``***`` 替换。
"""

from __future__ import annotations

import os
from collections.abc import MutableMapping
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

# 环境变量名（codex K2 已定）
MASTER_KEY_ENV = "LZ_MASTER_KEY"

# 敏感键名（小写匹配，K8）。命中即整体替换为 ***。
SENSITIVE_KEYS: frozenset[str] = frozenset(
    {
        "api_key",
        "apikey",
        "api-key",
        "authorization",
        "auth",
        "token",
        "access_token",
        "refresh_token",
        "secret",
        "password",
        "passwd",
        "credential",
        "credentials",
        "lz_master_key",
    }
)

REDACTED = "***"

# 掩码提示：保留前后缀便于用户辨认（如 sk-***3Xy），永不回传明文（K5）
_HINT_PREFIX_LEN = 3
_HINT_SUFFIX_LEN = 4


class CryptoError(RuntimeError):
    """加解密/主密钥错误。

    注意（K4）：异常消息不得包含密钥材料、明文 api_key 或其密文片段。
    """


def load_master_key(env: dict[str, str] | None = None) -> bytes:
    """从环境变量读取并校验主密钥。

    来源优先级：显式传入的 ``env`` > ``os.environ``。
    ``LZ_MASTER_KEY`` 必须存在且为合法 Fernet key（32 字节 url-safe base64）。

    Raises:
        CryptoError: 缺失或格式非法。错误信息不含密钥内容。
    """
    source = env if env is not None else os.environ
    raw = source.get(MASTER_KEY_ENV)
    if not raw:
        msg = (
            f"缺少主密钥环境变量 {MASTER_KEY_ENV}；拒绝启动。"
            "请用密钥初始化 CLI 生成（Fernet.generate_key），不要静默生成后写盘。"
        )
        raise CryptoError(msg)

    key = raw.encode("utf-8") if isinstance(raw, str) else raw
    try:
        # Fernet 构造时会校验 key 格式（32B url-safe base64）
        Fernet(key)
    except (ValueError, TypeError) as exc:
        # 不把 key 内容拼进异常（K4）
        msg = f"{MASTER_KEY_ENV} 格式非法：需为 32 字节 url-safe base64 的 Fernet key。"
        raise CryptoError(msg) from exc
    return key


def get_fernet(env: dict[str, str] | None = None) -> Fernet:
    """构造 Fernet 实例（每次调用重新读环境，便于测试注入）。"""
    return Fernet(load_master_key(env))


def encrypt_api_key(plaintext: str, env: dict[str, str] | None = None) -> bytes:
    """加密 api_key → Fernet 密文（bytes，落 LLMProfile.api_key_enc）。

    Raises:
        CryptoError: 主密钥缺失/非法，或 plaintext 非字符串。
    """
    if not isinstance(plaintext, str):
        msg = "api_key 明文必须是 str。"
        raise CryptoError(msg)
    return get_fernet(env).encrypt(plaintext.encode("utf-8"))


def decrypt_api_key(ciphertext: bytes, env: dict[str, str] | None = None) -> str:
    """解密 Fernet 密文 → api_key 明文（仅在 LLM 客户端发请求时调用，用完即丢，K3）。

    Raises:
        CryptoError: 主密钥缺失/非法，或密文无法解密（InvalidToken）。错误信息不含明文。
    """
    try:
        token = ciphertext.encode("utf-8") if isinstance(ciphertext, str) else ciphertext
        return get_fernet(env).decrypt(token).decode("utf-8")
    except InvalidToken as exc:
        msg = "api_key 解密失败：密文无效或主密钥不匹配。"
        raise CryptoError(msg) from exc


def api_key_hint(plaintext: str) -> str:
    """生成掩码提示（K5）：``sk-***last4``。永不回传明文。

    短于前缀+后缀的 key 直接返回全掩码。
    """
    if not isinstance(plaintext, str) or not plaintext:
        return REDACTED
    if len(plaintext) <= _HINT_PREFIX_LEN + _HINT_SUFFIX_LEN:
        return REDACTED
    prefix = plaintext[:_HINT_PREFIX_LEN]
    suffix = plaintext[-_HINT_SUFFIX_LEN:]
    return f"{prefix}{REDACTED}{suffix}"


def is_encrypted(ciphertext: bytes | str | None) -> bool:
    """判断是否为 Fernet 密文（以 ``gAAAA`` 开头，K1 断言辅助）。"""
    if ciphertext is None:
        return False
    if isinstance(ciphertext, bytes):
        ciphertext = ciphertext.decode("utf-8", errors="ignore")
    return ciphertext.startswith("gAAAA")


# ---------------------------------------------------------------------------
# structlog 脱敏 processor（K8）
# ---------------------------------------------------------------------------


def _redact_value(value: Any) -> Any:
    """递归脱敏：dict/list 深入；命中敏感键的值替换为 ***。"""
    if isinstance(value, dict):
        return {
            k: (REDACTED if _is_sensitive_key(k) else _redact_value(v))
            for k, v in value.items()
        }
    if isinstance(value, (list, tuple)):
        return type(value)(_redact_value(v) for v in value)
    return value


def _is_sensitive_key(key: Any) -> bool:
    if not isinstance(key, str):
        return False
    return key.strip().lower() in SENSITIVE_KEYS


def redact_sensitive(
    logger: Any,
    method_name: str,
    event_dict: MutableMapping[str, Any],
) -> MutableMapping[str, Any]:
    """structlog processor：对敏感键做 ``***`` 替换，键名大小写不敏感、含嵌套。

    键名命中（如 ``api_key``）时**整个值**替换；嵌套 dict/list 递归处理。

    用法::

        structlog.configure(processors=[..., redact_sensitive, structlog.dev.ConsoleRenderer()])
    """
    del logger, method_name  # 未用（协议要求）
    for key in list(event_dict.keys()):
        if _is_sensitive_key(key):
            event_dict[key] = REDACTED
        else:
            event_dict[key] = _redact_value(event_dict[key])
    return event_dict
