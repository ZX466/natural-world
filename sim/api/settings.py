"""Profile 设置页 API — M1（TASK-C06-②，kilo K02 契约落地）。

契约（kilo K02 已批）：响应白名单 8 字段（含 api_key_hint 掩码，无 api_key 明文）；
api_key 提交即 Fernet 加密落库；明文永不回传/记日志（K1/K5）。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

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


@router.get("")
async def list_profiles() -> list[dict[str, Any]]:
    return [_profile_to_item(r) for r in get_profile_store().list_profiles()]


@router.post("", status_code=201)
async def create_profile(data: ProfileCreate) -> dict[str, Any]:
    try:
        row = get_profile_store().create(data)
    except CryptoError as exc:
        raise HTTPException(status_code=500, detail="密钥服务不可用") from exc
    return _profile_to_item(row)


@router.patch("/{profile_id}")
async def update_profile(profile_id: str, data: ProfileUpdate) -> dict[str, Any]:
    row = get_profile_store().update(profile_id, data)
    if row is None:
        raise HTTPException(status_code=404, detail="profile 不存在")
    return _profile_to_item(row)


@router.delete("/{profile_id}", status_code=204)
async def delete_profile(profile_id: str) -> None:
    if not get_profile_store().delete(profile_id):
        raise HTTPException(status_code=404, detail="profile 不存在")


@router.post("/{profile_id}/activate")
async def activate_profile(profile_id: str) -> dict[str, Any]:
    row = get_profile_store().activate(profile_id)
    if row is None:
        raise HTTPException(status_code=404, detail="profile 不存在")
    return _profile_to_item(row)
