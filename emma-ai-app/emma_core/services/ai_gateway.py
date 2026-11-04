"""One way out to a language model, with the privacy gate welded to it.

Every call runs `privacy.assert_clean` on the payload first, so there is no path
to a provider that skips it. Providers are tried in order and each is retried
before moving on; when they all fail the caller gets a degraded result rather
than an exception, because the deterministic answer is still worth serving.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol, Sequence

from . import privacy
from ..config import settings

VERTEX_ENDPOINT = ("https://{region}-aiplatform.googleapis.com/v1/projects/{project}"
                   "/locations/{region}/publishers/google/models/{model}:generateContent")


class NotConfigured(RuntimeError):
    """The provider has no credentials yet, so it cannot be called."""


class ProviderError(RuntimeError):
    """The provider was called and did not answer usefully."""


class Provider(Protocol):
    name: str
    # False for anything that derives its answer locally, so a caller can tell
    # a real explanation from an echo of the evidence.
    is_model: bool

    def complete(self, *, system: str, prompt: str, max_tokens: int) -> str:
        ...


@dataclass
class Result:
    """What the gateway got, and what it had to do to get it."""

    text: str | None
    provider: str | None = None
    from_model: bool = False
    degraded: bool = False
    failures: list[str] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)

    def json(self) -> Any:
        """The answer parsed as JSON, or None if it was not JSON."""
        if not self.text:
            return None
        # Widest braces, so a code fence or a sentence of preamble costs nothing.
        start, end = self.text.find("{"), self.text.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            return json.loads(self.text[start:end + 1])
        except ValueError:
            return None


class OfflineProvider:
    """Answers from the evidence alone, so the loop runs with no account.

    Not a model and not a stand-in for one. It picks what the deterministic
    ranking already picked, which is the floor any real provider has to clear.
    """

    name = "offline"
    is_model = False

    def complete(self, *, system: str, prompt: str, max_tokens: int) -> str:
        candidates = []
        for line in prompt.splitlines():
            if line.startswith("Not eligible"):
                break
            token = line.strip().split()[0].strip("-*.") if line.strip() else ""
            if token.startswith("STAFF_") and token not in candidates:
                candidates.append(token)
        if not candidates:
            return json.dumps({"pick": None, "ranking": [],
                               "reason": "no eligible candidate in the evidence"})
        return json.dumps({
            "pick": candidates[0],
            "ranking": candidates,
            "reason": "highest ranked eligible candidate in the evidence",
        })


class VertexProvider:
    """Gemini through Vertex AI, pinned to one region.

    `token` is injected rather than minted here so the request shape can be
    exercised without a Google Cloud project.
    """

    name = "vertex"
    is_model = True

    def __init__(self, *, project: str = "", region: str = "", model: str = "",
                 token: Callable[[], str] | None = None,
                 transport: Callable[[str, dict, str], tuple[int, dict]] | None = None) -> None:
        self.project = project or settings.vertex_project
        self.region = region or settings.vertex_region
        self.model = model or settings.vertex_model
        self._token = token
        self._transport = transport or _http_post

    def _access_token(self) -> str:
        if self._token:
            return self._token()
        raise NotConfigured(
            "no Vertex AI credential; set VERTEX_ACCESS_TOKEN or pass a token callable")

    def complete(self, *, system: str, prompt: str, max_tokens: int) -> str:
        if not (self.project and self.region and self.model):
            raise NotConfigured("VERTEX_PROJECT, VERTEX_REGION and VERTEX_MODEL are required")
        url = VERTEX_ENDPOINT.format(region=self.region, project=self.project,
                                     model=self.model)
        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0, "maxOutputTokens": max_tokens,
                                 "responseMimeType": "application/json"},
        }
        status, payload = self._transport(url, body, self._access_token())
        if status != 200:
            raise ProviderError(f"vertex returned {status}: {str(payload)[:200]}")
        try:
            return payload["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError, TypeError):
            raise ProviderError(f"vertex returned no text: {str(payload)[:200]}")


class BedrockProvider:
    """One configured Bedrock model, authenticated by the AWS credential chain."""

    name = "bedrock"
    is_model = True

    def __init__(self, *, region: str = "", model: str = "", client=None):
        self.region = region or settings.bedrock_region
        self.model = model or settings.bedrock_model_id
        self._client = client
        self.last_metrics: dict = {}

    def complete(self, *, system: str, prompt: str, max_tokens: int) -> str:
        if not self.region or not self.model:
            raise NotConfigured("BEDROCK_REGION and BEDROCK_MODEL_ID are required")
        if not self._client:
            import boto3
            from botocore.config import Config
            self._client = boto3.client(
                "bedrock-runtime", region_name=self.region,
                config=Config(connect_timeout=5, read_timeout=settings.bedrock_timeout_seconds,
                              retries={"total_max_attempts": 1}),
            )
        started = time.monotonic()
        self.last_metrics = {}
        kimi = "moonshotai.kimi-k3" in self.model
        try:
            if kimi:
                # These short explanations do not need Kimi's default reasoning.
                raw = self._client.invoke_model(
                    modelId=self.model, contentType="application/json", accept="application/json",
                    body=json.dumps({
                        "messages": [{"role": "system", "content": system},
                                     {"role": "user", "content": prompt}],
                        "max_tokens": max_tokens, "reasoning_effort": "none",
                    }),
                )
                with raw["body"] as body:
                    data = json.loads(body.read())
                choice = (data.get("choices") or [{}])[0]
                message = choice.get("message") or {}
                usage = data.get("usage") or {}
                finish = choice.get("finish_reason")
                stop = {"stop": "end_turn", "length": "max_tokens",
                        "content_filter": "content_filtered"}.get(finish, "incomplete")
                if message.get("refusal"):
                    stop = "content_filtered"
                reply = {
                    "output": {"message": {"content": [{"text": message.get("content") or ""}]}},
                    "stopReason": stop, "ResponseMetadata": raw.get("ResponseMetadata", {}),
                    "usage": {"inputTokens": usage.get("prompt_tokens"),
                              "outputTokens": usage.get("completion_tokens"),
                              "cacheReadInputTokens": (usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0),
                              "cacheWriteInputTokens": (usage.get("prompt_tokens_details") or {}).get("cache_write_tokens", 0)},
                }
            else:
                reply = self._client.converse(
                    modelId=self.model,
                    system=[{"text": system}],
                    messages=[{"role": "user", "content": [{"text": prompt}]}],
                    inferenceConfig={"maxTokens": max_tokens, "temperature": 0},
                )
        except Exception as exc:
            # Provider errors must not echo prompts or signed request details.
            reason = type(exc).__name__
            response = getattr(exc, "response", None)
            if isinstance(response, dict):
                reason = (response.get("Error") or {}).get("Code") or reason
            raise ProviderError(f"Bedrock request failed ({reason})") from None
        usage = reply.get("usage") or {}
        self.last_metrics = {
            "model_id": self.model, "region": self.region,
            "request_id": (reply.get("ResponseMetadata") or {}).get("RequestId"),
            "input_tokens": usage.get("inputTokens"), "output_tokens": usage.get("outputTokens"),
            "latency_ms": round((time.monotonic() - started) * 1000),
            "stop_reason": reply.get("stopReason"),
            "api": "invoke_model" if kimi else "converse",
            "cache_read_input_tokens": usage.get("cacheReadInputTokens", 0),
            "cache_write_input_tokens": usage.get("cacheWriteInputTokens", 0),
        }
        if reply.get("stopReason") in {"guardrail_intervened", "content_filtered", "max_tokens", "incomplete"}:
            raise ProviderError("Bedrock response was blocked or incomplete")
        blocks = ((reply.get("output") or {}).get("message") or {}).get("content") or []
        answer = "".join(block.get("text", "") for block in blocks)
        if not answer.strip():
            raise ProviderError("Bedrock returned no text")
        return answer


def _http_post(url: str, body: dict, token: str) -> tuple[int, dict]:
    import requests

    reply = requests.post(url, json=body, timeout=30,
                          headers={"Authorization": f"Bearer {token}"})
    try:
        return reply.status_code, reply.json()
    except ValueError:
        return reply.status_code, {"body": reply.text[:500]}


class Gateway:
    """Tries each provider in turn and never lets a dirty payload out."""

    def __init__(self, providers: Sequence[Provider] | None = None, *,
                 attempts: int = 2, max_tokens: int = 800) -> None:
        self.providers = list(providers) if providers is not None else [OfflineProvider()]
        self.attempts = max(1, attempts)
        self.max_tokens = max_tokens

    def complete(self, *, system: str, prompt: str, payload: Any = None,
                 secrets: Sequence[str] = (), allow_cjk: bool = False) -> Result:
        # The prompt is what actually leaves, so it is checked even when the
        # caller also hands over the structure it was built from.
        privacy.assert_clean(prompt, secrets=secrets, allow_cjk=allow_cjk)
        privacy.assert_clean(system, secrets=secrets, allow_cjk=allow_cjk)
        if payload is not None:
            privacy.assert_clean(payload, secrets=secrets, allow_cjk=allow_cjk)

        failures: list[str] = []
        for provider in self.providers:
            for attempt in range(self.attempts):
                try:
                    text = provider.complete(system=system, prompt=prompt,
                                             max_tokens=self.max_tokens)
                except NotConfigured as exc:
                    failures.append(f"{provider.name}: {exc}")
                    break
                except Exception as exc:
                    failures.append(f"{provider.name} attempt {attempt + 1}: {exc}")
                    continue
                if text and text.strip():
                    return Result(text=text, provider=provider.name,
                                  from_model=getattr(provider, "is_model", True),
                                  failures=failures,
                                  degraded=bool(failures) and not getattr(provider, "is_model", True),
                                  metrics=dict(getattr(provider, "last_metrics", {})))
                failures.append(f"{provider.name} attempt {attempt + 1}: empty answer")
        return Result(text=None, provider=None, degraded=True, failures=failures)


def default_gateway(*, facility_id: str | None = None) -> Gateway:
    """External models are limited to explicitly approved synthetic tenants."""
    allowed = {value.strip() for value in settings.ai_synthetic_facility_ids.split(",") if value.strip()}
    if not facility_id or facility_id not in allowed:
        return Gateway([OfflineProvider()])
    chain: list[Provider] = []
    if settings.bedrock_enabled:
        chain.append(BedrockProvider())
    elif settings.vertex_project and settings.vertex_access_token:
        chain.append(VertexProvider(token=lambda: settings.vertex_access_token))
    chain.append(OfflineProvider())
    return Gateway(chain)
