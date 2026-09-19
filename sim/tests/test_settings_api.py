"""设置页 API 测试 — K5/K1 出戏与密钥安全（T1 级）。"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("LZ_MASTER_KEY", Fernet.generate_key().decode())
    # 独立临时库（不碰 world.db）
    import sim.api.settings as settings_mod

    settings_mod._profile_store = settings_mod.ProfileStore(f"sqlite:///{tmp_path}/settings.db")
    from sim.api.main import app

    with TestClient(app) as c:
        yield c
    settings_mod._profile_store = None


BODY = {
    "name": "deepseek 主力",
    "base_url": "https://api.deepseek.com/v1",
    "model": "deepseek-chat",
    "api_key": "sk-secret-abc9999",
    "temperature": 0.7,
    "max_tokens": 2048,
}


class TestProfileCrud:
    def test_create_returns_8_fields_no_plaintext(self, client: TestClient):
        resp = client.post("/api/settings/profiles", json=BODY)
        assert resp.status_code == 201
        item = resp.json()
        assert set(item.keys()) == {
            "id",
            "name",
            "base_url",
            "model",
            "temperature",
            "max_tokens",
            "active",
            "api_key_hint",
        }
        assert "sk-secret" not in str(item)
        assert item["api_key_hint"].startswith("sk-***")
        assert "9999" in item["api_key_hint"]  # last4

    def test_activate_switches_single_active(self, client: TestClient):
        id1 = client.post("/api/settings/profiles", json={**BODY, "name": "a"}).json()["id"]
        id2 = client.post("/api/settings/profiles", json={**BODY, "name": "b"}).json()["id"]
        client.post(f"/api/settings/profiles/{id1}/activate")
        client.post(f"/api/settings/profiles/{id2}/activate")
        items = client.get("/api/settings/profiles").json()
        active = [i for i in items if i["active"]]
        assert len(active) == 1 and active[0]["id"] == id2

    def test_update_reencrypts_key(self, client: TestClient):
        pid = client.post("/api/settings/profiles", json=BODY).json()["id"]
        resp = client.patch(f"/api/settings/profiles/{pid}", json={"api_key": "sk-new-7777zzz"})
        assert resp.status_code == 200
        assert "sk-new" not in resp.text

    def test_delete_and_404(self, client: TestClient):
        pid = client.post("/api/settings/profiles", json=BODY).json()["id"]
        assert client.delete(f"/api/settings/profiles/{pid}").status_code == 204
        assert client.delete(f"/api/settings/profiles/{pid}").status_code == 404

    def test_base_url_scheme_whitelist(self, client: TestClient):
        resp = client.post(
            "/api/settings/profiles", json={**BODY, "base_url": "file:///etc/passwd"}
        )
        assert resp.status_code == 422

    def test_encrypted_at_rest(self, client: TestClient, tmp_path):
        """落库的是 Fernet 密文（gAAAA 开头），不是明文。"""
        pid = client.post("/api/settings/profiles", json=BODY).json()["id"]
        from sqlalchemy import create_engine, text

        engine = create_engine(f"sqlite:///{tmp_path}/settings.db")
        with engine.connect() as conn:
            enc = conn.execute(
                text("SELECT api_key_enc FROM llm_profiles WHERE id=:i"), {"i": pid}
            ).scalar()
        assert enc.startswith(b"gAAAA")
        assert b"sk-secret" not in enc
