"""Bedrock request shape, safe failure and provider metadata."""

import io
import json

import pytest
from botocore.exceptions import ClientError

from emma_core.services import ai_gateway


@pytest.mark.parametrize("facility,expected", [(None, False), ("real-facility", False), ("synthetic-facility", True)])
def test_external_models_are_limited_to_approved_synthetic_facilities(monkeypatch, facility, expected):
    monkeypatch.setattr(ai_gateway.settings, "bedrock_enabled", True)
    monkeypatch.setattr(ai_gateway.settings, "ai_synthetic_facility_ids", "synthetic-facility")
    providers = ai_gateway.default_gateway(facility_id=facility).providers
    assert any(p.is_model for p in providers) == expected


class Runtime:
    def __init__(self, stop="end_turn"):
        self.calls = []
        self.stop = stop

    def converse(self, **kwargs):
        self.calls.append(kwargs)
        return {
            "output": {"message": {"content": [{"text": '{"answer":"ok"}'}]}},
            "stopReason": self.stop,
            "usage": {"inputTokens": 90, "outputTokens": 12},
            "ResponseMetadata": {"RequestId": "synthetic-request"},
        }


def test_grok_uses_the_configured_profile_and_bounded_output():
    runtime = Runtime()
    provider = ai_gateway.BedrockProvider(region="ap-southeast-1", client=runtime)
    result = ai_gateway.Gateway([provider], max_tokens=400).complete(
        system="Use only evidence", prompt="STAFF_1 eligible=true"
    )
    call = runtime.calls[0]
    assert call["modelId"] == "global.xai.grok-4.7"
    assert call["inferenceConfig"] == {"maxTokens": 400, "temperature": 0}
    assert result.metrics["request_id"] == "synthetic-request"
    assert result.metrics["input_tokens"] == 90
    assert result.from_model


def test_an_incomplete_or_blocked_answer_falls_back_safely():
    stop = "max_tokens"
    provider = ai_gateway.BedrockProvider(region="ap-southeast-1", client=Runtime(stop))
    result = ai_gateway.Gateway(
        [provider, ai_gateway.OfflineProvider()], attempts=1
    ).complete(system="s", prompt="STAFF_1 compliance_ok=true")
    assert not result.from_model
    assert result.provider == "offline"
    assert result.degraded


@pytest.mark.parametrize("finish", ["stop", "length", "content_filter", "ThrottlingException"])
def test_kimi_uses_bounded_non_reasoning_requests_and_rejects_incomplete_output(finish):
    class KimiRuntime:
        def invoke_model(self, **kwargs):
            self.request = kwargs
            if finish == "ThrottlingException":
                raise ClientError({"Error": {"Code": finish, "Message": "sensitive provider detail"}}, "InvokeModel")
            return {
                "body": io.BytesIO(json.dumps({
                    "choices": [{"finish_reason": finish, "message": {"content": '{"answer":"ok"}'}}],
                    "usage": {"prompt_tokens": 90, "completion_tokens": 12},
                }).encode()),
                "ResponseMetadata": {"RequestId": "synthetic-kimi-request"},
            }

    runtime = KimiRuntime()
    provider = ai_gateway.BedrockProvider(
        region="ap-southeast-1", model="global.moonshotai.kimi-k3", client=runtime
    )
    result = ai_gateway.Gateway([provider, ai_gateway.OfflineProvider()], attempts=1, max_tokens=400).complete(
        system="Use only evidence", prompt="STAFF_1 eligible=true"
    )
    assert runtime.request["modelId"] == "global.moonshotai.kimi-k3"
    request = json.loads(runtime.request["body"])
    assert request["max_tokens"] == 400
    assert request["reasoning_effort"] == "none"
    assert "temperature" not in request
    assert result.from_model == (finish == "stop")
    assert result.degraded == (finish != "stop")
    if finish == "stop":
        assert result.metrics["api"] == "invoke_model"
        assert result.metrics["output_tokens"] == 12
    if finish == "ThrottlingException":
        assert "ThrottlingException" in result.failures[0]
        assert "sensitive provider detail" not in result.failures[0]
