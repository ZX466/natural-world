"""模型请求预算与连接池生命周期，使用真实 SDK 和内存 HTTP transport。"""

from __future__ import annotations

from functools import partial
from typing import Any, cast

import httpx
import pytest
from openai import AsyncOpenAI

from sim.llm.client import LlmClient, LlmError, ProfileSnapshot


@pytest.fixture
def profile() -> ProfileSnapshot:
    return ProfileSnapshot(
        profile_name="attempt-budget-test",
        base_url="https://llm.invalid/v1",
        model="test-model",
        temperature=0.0,
        max_tokens=16,
        api_key_plain="test-key",
    )


def _completion_response() -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "id": "test-completion",
            "object": "chat.completion",
            "created": 0,
            "model": "test-model",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "收到。"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 3},
        },
    )


@pytest.mark.parametrize("error_type", [httpx.ConnectError, httpx.ReadTimeout])
async def test_default_attempts_retry_transient_failure(
    monkeypatch: pytest.MonkeyPatch,
    profile: ProfileSnapshot,
    error_type: type[httpx.RequestError],
) -> None:
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            raise error_type("transient failure", request=request)
        return _completion_response()

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http_client:
        monkeypatch.setattr(
            "sim.llm.client.AsyncOpenAI", partial(AsyncOpenAI, http_client=http_client)
        )
        result = await LlmClient().complete(profile, [{"role": "user", "content": "近来可好？"}])

    assert result.content == "收到。"
    assert result.attempt == 2
    assert len(requests) == 2


@pytest.mark.parametrize("max_attempts", [1, 3])
@pytest.mark.parametrize(
    ("error_type", "error_kind"),
    [(httpx.ConnectError, "connection"), (httpx.ReadTimeout, "timeout")],
)
async def test_configured_attempt_limit_bounds_actual_http_requests(
    monkeypatch: pytest.MonkeyPatch,
    profile: ProfileSnapshot,
    max_attempts: int,
    error_type: type[httpx.RequestError],
    error_kind: str,
) -> None:
    requests: list[httpx.Request] = []

    def fail(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        raise error_type("transient failure", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(fail)) as http_client:
        monkeypatch.setattr(
            "sim.llm.client.AsyncOpenAI", partial(AsyncOpenAI, http_client=http_client)
        )
        client = LlmClient(max_attempts=max_attempts)
        with pytest.raises(LlmError) as caught:
            await client.complete(profile, [{"role": "user", "content": "近来可好？"}])

    assert caught.value.error_kind == error_kind
    assert len(requests) == max_attempts


@pytest.mark.parametrize("bad_attempts", [0, -1, True, False, 1.0, "2", None])
def test_invalid_attempt_configuration_is_rejected(bad_attempts: object) -> None:
    with pytest.raises(ValueError, match="max_attempts"):
        LlmClient(max_attempts=cast(int, bad_attempts))


async def test_aclose_before_first_request_is_idempotent() -> None:
    client = LlmClient()

    await client.aclose()
    await client.aclose()


async def test_aclose_releases_sdk_pool_and_allows_fresh_client(
    monkeypatch: pytest.MonkeyPatch, profile: ProfileSnapshot
) -> None:
    sdk_clients: list[AsyncOpenAI] = []

    def make_sdk(**kwargs: Any) -> AsyncOpenAI:
        sdk = AsyncOpenAI(
            **kwargs,
            http_client=httpx.AsyncClient(
                transport=httpx.MockTransport(lambda _request: _completion_response())
            ),
        )
        sdk_clients.append(sdk)
        return sdk

    monkeypatch.setattr("sim.llm.client.AsyncOpenAI", make_sdk)
    client = LlmClient()
    messages = [{"role": "user", "content": "近来可好？"}]
    try:
        await client.complete(profile, messages)
        first_sdk = sdk_clients[0]
        assert not first_sdk.is_closed()

        await client.aclose()

        assert first_sdk.is_closed()
        assert client._client is None
        assert client._client_profile is None
        await client.aclose()

        result = await client.complete(profile, messages)
        assert result.content == "收到。"
        assert len(sdk_clients) == 2
        assert not sdk_clients[1].is_closed()
    finally:
        for sdk in sdk_clients:
            if not sdk.is_closed():
                await sdk.close()
