"""LLM 客户端 — M1 认知闭环的地基（DESIGN §4/§15，TASK-C06-①）。

- OpenAI 协议通吃（OpenAI / DeepSeek / 通义 / Ollama / LM Studio），单 profile 手动切换。
- api_key 只在调用瞬间经 crypto 解密，用完即丢（K3）；明文绝不进日志/异常（K4，
  structlog 链上的 redact_sensitive 是第二道）。
- 监控字段逐项对齐 docs/perf/llm-monitoring.md（pi F05 口径）：
  llm.request / llm.response / llm.retry / llm.timeout / llm.error / llm.cache_hit / llm.decision。
- 世界照常运转：LLM 调用永远异步，失败降级由上层（闸门/计划队列）处理，本模块只如实上报。
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field

import structlog
from openai import APIConnectionError, APIStatusError, APITimeoutError, AsyncOpenAI
from pydantic import BaseModel, ConfigDict

from sim.core.persistence.crypto import decrypt_api_key

logger = structlog.get_logger(__name__)

REQUEST_TIMEOUT_SECONDS = 30.0
MAX_ATTEMPTS = 2  # §15 成本治理：单次决策最多重试一次，避免烧钱循环

_ERROR_KINDS = {
    APITimeoutError: "timeout",
    APIConnectionError: "connection",
}


class LlmCallResult(BaseModel):
    """一次成功调用的结果——只含 token 计数与延迟，不落响应全文（监控口径）。"""

    model_config = ConfigDict(frozen=True)

    request_id: str
    content: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    latency_ms: float
    attempt: int
    cache_hit: bool


class LlmError(Exception):
    """LLM 调用最终失败（重试耗尽）。error_kind 对齐监控口径，不含明文。"""

    def __init__(self, error_kind: str, detail: str) -> None:
        super().__init__(f"llm_{error_kind}: {detail}")
        self.error_kind = error_kind


@dataclass
class ProfileSnapshot:
    """调用瞬间的 profile 影子。api_key 明文只活在本对象生命周期内（K3）。"""

    profile_name: str
    base_url: str
    model: str
    temperature: float
    max_tokens: int
    api_key_plain: str


@dataclass
class DecisionTracker:
    """llm.decision 端到端计时：意图触发 → Intent 产出（含队列/重试）。

    同一决策链的多次请求以 request_id 前缀串联（监控口径 §4）。
    """

    started: float = field(default_factory=time.monotonic)
    chain_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])

    def finish(self, ok: bool) -> float:
        decision_ms = (time.monotonic() - self.started) * 1000
        logger.info(
            "llm.decision",
            chain_id=self.chain_id,
            decision_ms=round(decision_ms, 1),
            ok=ok,
        )
        return decision_ms


class LlmClient:
    """异步 LLM 客户端。单实例复用底层 httpx 连接池。"""

    def __init__(self) -> None:
        self._client: AsyncOpenAI | None = None
        self._client_profile: str | None = None

    def _ensure_client(self, profile: ProfileSnapshot) -> AsyncOpenAI:
        """按 profile 复用客户端（base_url/key 变化才重建）。"""
        if self._client is None or self._client_profile != profile.profile_name:
            self._client = AsyncOpenAI(
                api_key=profile.api_key_plain,
                base_url=profile.base_url,
                timeout=REQUEST_TIMEOUT_SECONDS,
                max_retries=0,  # 重试由本模块统一管理（要记 llm.retry 字段）
            )
            self._client_profile = profile.profile_name
        return self._client

    async def complete(
        self,
        profile: ProfileSnapshot,
        messages: list[dict[str, str]],
        decision: DecisionTracker | None = None,
    ) -> LlmCallResult:
        """单次补全调用：监控事件 + 重试一次 + 结构化错误。"""
        client = self._ensure_client(profile)
        cache_hit = _prefix_cache_probe(profile.profile_name, messages)
        last_error: tuple[str, str] | None = None

        for attempt in range(1, MAX_ATTEMPTS + 1):
            request_id = f"{decision.chain_id}-r{attempt}" if decision else uuid.uuid4().hex[:12]
            logger.info(
                "llm.request",
                request_id=request_id,
                profile_name=profile.profile_name,
                model=profile.model,
                attempt=attempt,
            )
            started = time.monotonic()
            try:
                resp = await client.chat.completions.create(
                    model=profile.model,
                    messages=messages,  # type: ignore[arg-type]
                    temperature=profile.temperature,
                    max_tokens=profile.max_tokens,
                )
            except APITimeoutError as exc:
                last_error = ("timeout", str(type(exc).__name__))
                logger.warning("llm.timeout", request_id=request_id, attempt=attempt)
                continue
            except APIConnectionError as exc:
                last_error = ("connection", str(type(exc).__name__))
                logger.warning(
                    "llm.error", request_id=request_id, attempt=attempt, error_kind="connection"
                )
                continue
            except APIStatusError as exc:
                kind = _status_kind(exc)
                last_error = (kind, f"status={exc.status_code}")
                logger.warning("llm.error", request_id=request_id, attempt=attempt, error_kind=kind)
                break  # 4xx/5xx 语义明确：4xx 重试无意义，5xx 由上层决定，均不盲试
            except Exception as exc:
                last_error = ("http_5xx", str(type(exc).__name__))
                logger.warning(
                    "llm.error", request_id=request_id, attempt=attempt, error_kind="unexpected"
                )
                break

            latency_ms = (time.monotonic() - started) * 1000
            usage = resp.usage
            result = LlmCallResult(
                request_id=request_id,
                content=resp.choices[0].message.content or "",
                prompt_tokens=usage.prompt_tokens if usage else 0,
                completion_tokens=usage.completion_tokens if usage else 0,
                total_tokens=usage.total_tokens if usage else 0,
                latency_ms=round(latency_ms, 1),
                attempt=attempt,
                cache_hit=cache_hit,
            )
            logger.info(
                "llm.response",
                request_id=request_id,
                profile_name=profile.profile_name,
                model=profile.model,
                prompt_tokens=result.prompt_tokens,
                completion_tokens=result.completion_tokens,
                total_tokens=result.total_tokens,
                latency_ms=result.latency_ms,
                attempt=result.attempt,
                cache_hit=result.cache_hit,
            )
            if attempt > 1:
                logger.info("llm.retry", request_id=request_id, resolved=True, attempt=attempt)
            return result

        if last_error is None:
            raise LlmError("unknown", "no attempts recorded")
        raise LlmError(last_error[0], last_error[1])


def _status_kind(exc: APIStatusError) -> str:
    code = exc.status_code
    if code == 429:
        return "rate_limit"
    if 400 <= code < 500:
        return "http_4xx"
    return "http_5xx"


def _prefix_cache_probe(profile_name: str, messages: list[dict[str, str]]) -> bool:
    """身份锚前缀缓存探针（M1 口径）：messages[0] 指纹与该 profile 上次相同
    → 判定前缀命中（供应商 cached_tokens 回报前的近似，非精确值）。

    状态按 (profile_name, fingerprint) 记忆：同锚连发 → True；换锚 → False。
    """
    import hashlib

    if not messages:
        return False
    fingerprint = hashlib.sha256(messages[0].get("content", "").encode()).hexdigest()
    cached = _LAST_ANCHOR_FP.get(profile_name)
    _LAST_ANCHOR_FP[profile_name] = fingerprint
    return cached == fingerprint


_LAST_ANCHOR_FP: dict[str, str] = {}


def load_profile_snapshot(
    profile_name: str,
    base_url: str,
    model: str,
    temperature: float,
    max_tokens: int,
    api_key_enc: bytes,
) -> ProfileSnapshot:
    """从 DB 行组装调用影子：此处一次性解密（K3：用完即丢，不落实例字段以外处）。"""
    return ProfileSnapshot(
        profile_name=profile_name,
        base_url=base_url,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        api_key_plain=decrypt_api_key(api_key_enc),
    )
