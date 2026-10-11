"""D13 密钥引导 + 模型拉取/测试端点 钉子。

三个面：
1. 密钥三级引导（crypto.py）：env `LZ_MASTER_KEY` > `~/.linhe/master.key`
   > 自动生成并持久化（K2 订正：原「缺钥拒启」在单机本地部署下把用户挡在
   门外——改为「生成后持久化固定文件」，密钥不丢 ⇒ 密文永远可解，K2 原意
   「防生成即丢」保住；env 存在时优先，零行为变化）。
2. `POST /api/settings/profiles/models`：带 base_url+api_key 拉对方模型清单
   （GET {base_url}/models，OpenAI 兼容），返回 id 列表——前端「拉取模型」。
3. `POST /api/settings/profiles/test`：带四元组发极小对话请求（max_tokens=1），
   返回 ok+延迟 ms 或失败原因——前端「测试连接」。

安全：SSRF 预检沿用 _validated_base_url；api_key 走既有日志脱敏链（K8）；
测试/拉取请求不落库、不进世界事件流。
"""

from __future__ import annotations

import json
from collections.abc import Iterator

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

pytestmark = pytest.mark.t1


# ---------------------------------------------------------------------------
# ① 密钥三级引导（crypto.py）
# ---------------------------------------------------------------------------


class TestKeyBootstrap:
    """env > 文件 > 自动生成持久化——三级优先级。"""

    def test_env_still_wins(self, tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
        """env 存在时优先（原行为零回归）。"""
        from sim.core.persistence import crypto

        env_key = Fernet.generate_key().decode()
        monkeypatch.setenv("LZ_MASTER_KEY", env_key)
        monkeypatch.setattr(crypto, "_KEY_FILE", tmp_path / "master.key")
        key = crypto.load_master_key()
        assert key == env_key.encode()

    def test_file_fallback(self, tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
        """无 env → 读 ~/.linhe 位置的 key 文件。"""
        from sim.core.persistence import crypto

        monkeypatch.delenv("LZ_MASTER_KEY", raising=False)
        key_file = tmp_path / "master.key"
        file_key = Fernet.generate_key().decode()
        key_file.write_text(file_key, encoding="utf-8")
        monkeypatch.setattr(crypto, "_KEY_FILE", key_file)
        assert crypto.load_master_key() == file_key.encode()

    def test_autogenerate_persists(self, tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
        """无 env 无文件 → 生成合法 Fernet key 并写文件（下次可读回）。"""
        from sim.core.persistence import crypto

        monkeypatch.delenv("LZ_MASTER_KEY", raising=False)
        key_file = tmp_path / "master.key"
        monkeypatch.setattr(crypto, "_KEY_FILE", key_file)
        key = crypto.load_master_key()
        Fernet(key)  # 生成的必须可用
        assert key_file.exists()
        assert key_file.read_text(encoding="utf-8").encode() == key
        # 第二次调用读回同一把（幂等）
        assert crypto.load_master_key() == key

    def test_autogenerate_rejects_bad_env(self, tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
        """env 存在但格式非法 → 仍拒绝（不覆盖、不绕过——坏 key 是配置错误）。"""
        from sim.core.persistence import crypto

        monkeypatch.setenv("LZ_MASTER_KEY", "not-a-fernet-key")
        monkeypatch.setattr(crypto, "_KEY_FILE", tmp_path / "master.key")
        with pytest.raises(crypto.CryptoError):
            crypto.load_master_key()

    def test_file_roundtrip_encrypt(self, tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
        """文件引导后加密解密闭环（端到端可用性）。"""
        from sim.core.persistence import crypto

        monkeypatch.delenv("LZ_MASTER_KEY", raising=False)
        monkeypatch.setattr(crypto, "_KEY_FILE", tmp_path / "master.key")
        enc = crypto.encrypt_api_key("sk-hello-123456")
        assert crypto.decrypt_api_key(enc) == "sk-hello-123456"


# ---------------------------------------------------------------------------
# ② 拉取模型 / ③ 测试连接（settings.py 新端点）
# ---------------------------------------------------------------------------


@pytest.fixture()
def client(tmp_path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.delenv("LZ_MASTER_KEY", raising=False)
    import sim.api.settings as settings_mod

    settings_mod._profile_store = settings_mod.ProfileStore(f"sqlite:///{tmp_path}/settings.db")
    from sim.api.main import app

    with TestClient(app) as c:
        yield c
    settings_mod._profile_store = None


class TestListModelsEndpoint:
    """POST /api/settings/profiles/models——拉对方 /models 清单。"""

    @staticmethod
    def _fake_response(payload: object):
        """httpx.Response 形状的轻量 stub（pyright 友好）。"""

        class _Resp:
            def raise_for_status(self) -> None:
                return None

            def json(self) -> object:
                return payload

        return _Resp()

    @staticmethod
    def _raise_status(code: int):
        """HTTPStatusError 构造器（真实 httpx 请求/响应对象，pyright 友好）。"""
        import httpx

        def _raise(url: str) -> None:
            request = httpx.Request("GET", url)
            response = httpx.Response(code, request=request, text="stub")
            raise httpx.HTTPStatusError(f"{code}", request=request, response=response)

        return _raise

    def test_lists_models(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        captured: dict = {}

        def fake_get(url: str, headers=None, timeout=None):
            captured["url"] = url
            return self._fake_response(
                {"data": [{"id": "deepseek-v4-flash"}, {"id": "deepseek-chat"}]}
            )

        monkeypatch.setattr("httpx.get", fake_get)
        res = client.post(
            "/api/settings/profiles/models",
            json={"base_url": "https://api.example.com/v1", "api_key": "sk-abc9999"},
        )
        assert res.status_code == 200
        body = res.json()
        assert body["ok"] is True
        assert "deepseek-v4-flash" in body["models"]
        assert captured["url"].startswith("https://api.example.com/v1")
        assert "sk-abc9999" not in json.dumps(body)  # 明文不回显（K5）

    def test_http_error_maps_to_reason(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """对方 401 → ok:false + reason（工程词可，密钥不出）。"""
        monkeypatch.setattr(
            "httpx.get", lambda url, headers=None, timeout=None: self._raise_status(401)(url)
        )
        res = client.post(
            "/api/settings/profiles/models",
            json={"base_url": "https://api.example.com/v1", "api_key": "sk-bad"},
        )
        assert res.status_code == 200
        body = res.json()
        assert body["ok"] is False
        assert "401" in body["reason"]

    def test_ssrf_rejected(self, client: TestClient) -> None:
        """非 http(s) base_url → 422（复用既有预检口径）。"""
        res = client.post(
            "/api/settings/profiles/models",
            json={"base_url": "ftp://evil.example.com", "api_key": "sk-x"},
        )
        assert res.status_code == 422

    def test_empty_model_list_is_error_shape(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """清单空 → ok:false（防「拉到了但什么都没有」静默成功）。"""
        monkeypatch.setattr(
            "httpx.get",
            lambda url, headers=None, timeout=None: self._fake_response({"data": []}),
        )
        res = client.post(
            "/api/settings/profiles/models",
            json={"base_url": "https://api.example.com/v1", "api_key": "sk-x"},
        )
        body = res.json()
        assert body["ok"] is False and body["models"] == []


class TestTestConnectionEndpoint:
    """POST /api/settings/profiles/test——极小对话请求连通性。

    注意：不把 staticmethod 别名为类属性——`_alias = A.s` 在类体内取出的
    staticmethod 会在实例访问时重新绑定为普通方法（self 占第一参），实测
    payload 串位。工具函数经类名显式调用。
    """

    def _post(self, client: TestClient, **overrides: str):
        """提交测试连接请求（返回 TestClient.Response 供断言）。"""
        payload = {
            "base_url": "https://api.example.com/v1",
            "model": "deepseek-v4-flash",
            "api_key": "sk-abc9999",
        }
        payload.update(overrides)
        return client.post("/api/settings/profiles/test", json=payload)

    def test_ok_returns_latency(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        sent: dict = {}
        resp = TestListModelsEndpoint._fake_response

        def fake_post(url: str, headers=None, json=None, timeout=None):
            sent["url"] = url
            sent["body"] = json
            return resp({"choices": [{"message": {"content": "好"}}], "usage": {"total_tokens": 1}})

        monkeypatch.setattr("httpx.post", fake_post)
        res = self._post(client)
        assert res.status_code == 200
        body = res.json()
        assert body["ok"] is True
        assert isinstance(body["latency_ms"], int) and body["latency_ms"] >= 0
        # 极小请求：max_tokens=1（不烧钱）
        assert sent["body"]["max_tokens"] == 1
        assert "sk-abc9999" not in json.dumps(body)  # K5

    def test_401_reason(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        raiser = TestListModelsEndpoint._raise_status
        monkeypatch.setattr(
            "httpx.post",
            lambda url, headers=None, json=None, timeout=None: raiser(401)(url),
        )
        body = self._post(client).json()
        assert body["ok"] is False and "401" in body["reason"]

    def test_timeout_reason(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        import httpx

        def fake_post(url: str, headers=None, json=None, timeout=None):
            raise httpx.TimeoutException("too slow")

        monkeypatch.setattr("httpx.post", fake_post)
        body = self._post(client).json()
        assert body["ok"] is False and body["reason"]

    def test_ssrf_rejected(self, client: TestClient) -> None:
        res = self._post(client, base_url="file:///etc/passwd")
        assert res.status_code == 422
