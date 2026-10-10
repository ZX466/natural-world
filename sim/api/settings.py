"""Profile 设置页 API — M1（TASK-C06-②，kilo K02 契约落地）。

契约（kilo K02 已批）：响应白名单 8 字段（含 api_key_hint 掩码，无 api_key 明文）；
api_key 提交即 Fernet 加密落库；明文永不回传/记日志（K1/K5）。
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from sim.core.persistence.crypto import (
    CryptoError,
    api_key_hint,
    encrypt_api_key,
)
from sim.core.persistence.models import LLMProfile

router = APIRouter(prefix="/api/settings/profiles", tags=["settings"])


class ProfileCreate(BaseModel):
    """创建请求（kilo 契约：create 6 字段）。"""

    name: str = Field(min_length=1, max_length=64)
    base_url: str = Field(min_length=1)
    model: str = Field(min_length=1)
    api_key: str = Field(min_length=1)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=2048, ge=1, le=32768)


class ProfileUpdate(BaseModel):
    """更新请求（全可选；api_key 提供则重加密）。"""

    name: str | None = None
    base_url: str | None = None
    model: str | None = None
    api_key: str | None = None
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    max_tokens: int | None = Field(default=None, ge=1, le=32768)


class ProfileListItem(BaseModel):
    """响应模型（kilo 契约：8 字段白名单 + api_key_hint 掩码）。

    补进 OpenAPI schema（kilo K03 差异回写：路由此前返裸 dict，
    codegen 缺响应模型）。明文 api_key 永不进本模型（K5）。
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    base_url: str
    model: str
    temperature: float
    max_tokens: int
    active: bool
    api_key_hint: str


def _row_to_dict(p: LLMProfile) -> dict[str, Any]:
    """session 内快照为纯 dict（api_key_enc 原样 bytes），避免 DetachedInstance。"""
    return {
        "id": p.id,
        "name": p.name,
        "base_url": p.base_url,
        "model": p.model,
        "temperature": p.temperature,
        "max_tokens": p.max_tokens,
        "active": p.is_active,
        "_enc": p.api_key_enc,
    }


def _profile_to_item(row: dict[str, Any]) -> dict[str, Any]:
    """8 字段白名单序列化（K5：api_key_hint 掩码，无明文）。"""
    from sim.core.persistence.crypto import decrypt_api_key

    try:
        plain = decrypt_api_key(row["_enc"])
    except CryptoError:
        plain = "sk-?????"
    return {
        "id": row["id"],
        "name": row["name"],
        "base_url": row["base_url"],
        "model": row["model"],
        "temperature": row["temperature"],
        "max_tokens": row["max_tokens"],
        "active": row["active"],
        "api_key_hint": api_key_hint(plain),
    }


class ProfileStore:
    """LLMProfile 的 CRUD（同步 SQL 走 SQLite 文件库；aiosqlite 异步在 store 层）。

    M1 简化：设置页操作低频，直接用同步 session（sqlalchemy create_engine）。
    """

    def __init__(self, db_url: str = "sqlite:///world.db", create_tables: bool = True) -> None:
        from sqlalchemy import create_engine
        from sqlalchemy.orm import Session, sessionmaker

        self._engine = create_engine(db_url)
        if create_tables:
            # 开发库快速起步（生产走 alembic；设置页表在 0001 迁移内）
            from sim.core.persistence.models import Base

            Base.metadata.create_all(self._engine)
        self._session_local: sessionmaker[Session] = sessionmaker(self._engine)

    def list_profiles(self) -> list[dict[str, Any]]:
        with self._session_local() as s:
            rows = s.query(LLMProfile).order_by(LLMProfile.created_at).all()
            return [_row_to_dict(r) for r in rows]

    def get(self, profile_id: str) -> LLMProfile | None:
        with self._session_local() as s:
            return s.get(LLMProfile, profile_id)

    def create(self, data: ProfileCreate) -> dict[str, Any]:
        import uuid

        with self._session_local() as s:
            profile = LLMProfile(
                id=uuid.uuid4().hex[:12],
                name=data.name,
                base_url=_validated_base_url(data.base_url),
                model=data.model,
                api_key_enc=encrypt_api_key(data.api_key),
            )
            profile.temperature = data.temperature
            profile.max_tokens = data.max_tokens
            s.add(profile)
            s.commit()
            return _row_to_dict(profile)

    def update(self, profile_id: str, data: ProfileUpdate) -> dict[str, Any] | None:
        with self._session_local() as s:
            profile = s.get(LLMProfile, profile_id)
            if profile is None:
                return None
            if data.name is not None:
                profile.name = data.name
            if data.base_url is not None:
                profile.base_url = _validated_base_url(data.base_url)
            if data.model is not None:
                profile.model = data.model
            if data.api_key is not None:
                profile.api_key_enc = encrypt_api_key(data.api_key)
            if data.temperature is not None:
                profile.temperature = data.temperature
            if data.max_tokens is not None:
                profile.max_tokens = data.max_tokens
            s.commit()
            return _row_to_dict(profile)

    def delete(self, profile_id: str) -> bool:
        with self._session_local() as s:
            profile = s.get(LLMProfile, profile_id)
            if profile is None:
                return False
            s.delete(profile)
            s.commit()
            return True

    def activate(self, profile_id: str) -> dict[str, Any] | None:
        """单 profile 手动切换：全部置 inactive 后激活目标（事务内）。"""
        with self._session_local() as s:
            profile = s.get(LLMProfile, profile_id)
            if profile is None:
                return None
            for p in s.query(LLMProfile).all():
                p.is_active = p.id == profile_id
            s.commit()
            return _row_to_dict(profile)

    def get_active(self) -> LLMProfile | None:
        with self._session_local() as s:
            return s.query(LLMProfile).filter(LLMProfile.is_active.is_(True)).first()


def _validated_base_url(url: str) -> str:
    """SSRF 预检（codex K7 + cline W6 结论）：仅 http(s)，M1 部署绑定 127.0.0.1。"""
    from urllib.parse import urlparse

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(status_code=422, detail="base_url 仅支持 http/https")
    return url


_profile_store: ProfileStore | None = None


def get_profile_store() -> ProfileStore:
    global _profile_store
    if _profile_store is None:
        _profile_store = ProfileStore()
    return _profile_store


@router.get("", response_model=list[ProfileListItem])
async def list_profiles() -> list[dict[str, Any]]:
    return [_profile_to_item(r) for r in get_profile_store().list_profiles()]


@router.post("", status_code=201, response_model=ProfileListItem)
async def create_profile(data: ProfileCreate) -> dict[str, Any]:
    try:
        row = get_profile_store().create(data)
    except CryptoError as exc:
        raise HTTPException(status_code=500, detail="密钥服务不可用") from exc
    return _profile_to_item(row)


@router.patch("/{profile_id}", response_model=ProfileListItem)
async def update_profile(profile_id: str, data: ProfileUpdate) -> dict[str, Any]:
    row = get_profile_store().update(profile_id, data)
    if row is None:
        raise HTTPException(status_code=404, detail="/errors/profile-not-found")
    return _profile_to_item(row)


@router.delete("/{profile_id}", status_code=204)
async def delete_profile(profile_id: str) -> None:
    if not get_profile_store().delete(profile_id):
        raise HTTPException(status_code=404, detail="/errors/profile-not-found")


@router.post("/{profile_id}/activate", response_model=ProfileListItem)
async def activate_profile(profile_id: str) -> dict[str, Any]:
    row = get_profile_store().activate(profile_id)
    if row is None:
        raise HTTPException(status_code=404, detail="/errors/profile-not-found")
    return _profile_to_item(row)


# ---------------------------------------------------------------------------
# D13：模型拉取 / 连通性测试（戏外调试面——工程词允许；不落库不进世界事件）
# ---------------------------------------------------------------------------


class ModelListRequest(BaseModel):
    """拉取模型清单请求（OpenAI 兼容 GET {base_url}/models）。"""

    base_url: str = Field(min_length=1)
    api_key: str = Field(min_length=1)


class ModelListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: bool
    models: list[str] = []
    reason: str | None = None


class TestConnectionRequest(BaseModel):
    """连通性测试请求（极小对话：max_tokens=1，不烧钱）。"""

    base_url: str = Field(min_length=1)
    model: str = Field(min_length=1)
    api_key: str = Field(min_length=1)


class TestConnectionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: bool
    latency_ms: int | None = None
    reason: str | None = None


_LLM_TIMEOUT_SECONDS = 8.0


def _clean_reason(exc: Exception) -> str:
    """异常 → 安全原因串（K4：api_key/密钥材料绝不进 reason）。"""
    import httpx

    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        hints = {
            401: "密钥被拒（401）",
            403: "无权访问（403）",
            404: "路径不对（404，检查 base_url 是否带 /v1）",
        }
        return hints.get(code, f"对方返回 HTTP {code}")
    if isinstance(exc, httpx.TimeoutException):
        return "超时（8 秒无响应）"
    if isinstance(exc, httpx.ConnectError):
        return "连不上对方服务（检查 base_url / 网络）"
    return f"请求失败：{type(exc).__name__}"


def _fetch_models_sync(base_url: str, api_key: str) -> dict[str, Any]:
    """阻塞拉取（供 to_thread 包裹；测试 monkeypatch httpx.get）。"""
    import httpx

    try:
        resp = httpx.get(
            f"{base_url.rstrip('/')}/models",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=_LLM_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        payload = resp.json()
    except Exception as exc:
        return {"ok": False, "models": [], "reason": _clean_reason(exc)}
    models = sorted(
        str(m.get("id")) for m in payload.get("data", []) if isinstance(m, dict) and m.get("id")
    )
    if not models:
        return {"ok": False, "models": [], "reason": "对方返回了空模型清单"}
    return {"ok": True, "models": models, "reason": None}


@router.post("/models", response_model=ModelListResponse)
async def list_remote_models(data: ModelListRequest) -> dict[str, Any]:
    """拉对方模型清单（前端「拉取模型」按钮供数）。

    OpenAI 兼容口径：GET {base_url}/models，Authorization: Bearer。
    清单空视为失败（防静默成功）。阻塞 HTTP 走 to_thread（不占事件循环）。
    """
    base = _validated_base_url(data.base_url)
    return await asyncio.to_thread(_fetch_models_sync, base, data.api_key)


def _test_connection_sync(base_url: str, model: str, api_key: str) -> dict[str, Any]:
    """阻塞测试连接（供 to_thread 包裹；测试 monkeypatch httpx.post）。"""
    import time

    import httpx

    started = time.monotonic()
    try:
        resp = httpx.post(
            f"{base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": model,
                "messages": [{"role": "user", "content": "回一个字。"}],
                "max_tokens": 1,
                "temperature": 0,
            },
            timeout=_LLM_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        payload = resp.json()
    except Exception as exc:
        return {"ok": False, "latency_ms": None, "reason": _clean_reason(exc)}
    latency_ms = int((time.monotonic() - started) * 1000)
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return {
            "ok": False,
            "latency_ms": latency_ms,
            "reason": "对方响应缺 choices（非 OpenAI 兼容格式？）",
        }
    return {"ok": True, "latency_ms": latency_ms, "reason": None}


@router.post("/test", response_model=TestConnectionResponse)
async def test_connection(data: TestConnectionRequest) -> dict[str, Any]:
    """连通性测试（前端「测试连接」按钮供数）：极小对话请求 max_tokens=1。"""
    base = _validated_base_url(data.base_url)
    return await asyncio.to_thread(_test_connection_sync, base, data.model, data.api_key)
