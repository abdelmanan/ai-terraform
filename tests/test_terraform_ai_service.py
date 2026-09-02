from types import SimpleNamespace

import openai
import pytest

from backend.exceptions.api_exception import ApiException
from backend.services.ai.terraform_ai_service import TerraformAIService


@pytest.fixture
def service():
    return TerraformAIService()


def _completion(content, finish_reason="stop"):
    message = SimpleNamespace(content=content)
    choice = SimpleNamespace(message=message, finish_reason=finish_reason)
    return SimpleNamespace(choices=[choice])


def test_generate_success(monkeypatch, service):
    monkeypatch.setattr(
        service.client.chat.completions,
        "create",
        lambda **kwargs: _completion("### provider.tf\n...")
    )

    result = service.generate("prompt")

    assert result == "### provider.tf\n..."


def test_generate_passes_expected_params(monkeypatch, service):
    captured = {}

    def fake_create(**kwargs):
        captured.update(kwargs)
        return _completion("ok")

    monkeypatch.setattr(service.client.chat.completions, "create", fake_create)

    service.generate("my prompt")

    assert captured["messages"] == [{"role": "user", "content": "my prompt"}]
    assert captured["max_tokens"] > 0
    assert captured["extra_body"] == {"reasoning_effort": "low"}


def test_generate_empty_content_raises(monkeypatch, service):
    monkeypatch.setattr(
        service.client.chat.completions,
        "create",
        lambda **kwargs: _completion("   ")
    )

    with pytest.raises(ApiException) as exc_info:
        service.generate("prompt")

    assert exc_info.value.status_code == 502
    assert "empty" in exc_info.value.message.lower()


def test_generate_no_choices_raises(monkeypatch, service):
    monkeypatch.setattr(
        service.client.chat.completions,
        "create",
        lambda **kwargs: SimpleNamespace(choices=[])
    )

    with pytest.raises(ApiException) as exc_info:
        service.generate("prompt")

    assert exc_info.value.status_code == 502


def test_generate_truncated_response_returns_partial_content(monkeypatch, service):
    monkeypatch.setattr(
        service.client.chat.completions,
        "create",
        lambda **kwargs: _completion("### provider.tf\npartial...", finish_reason="length")
    )

    result = service.generate("prompt")

    assert result == "### provider.tf\npartial..."


def test_generate_timeout_maps_to_504(monkeypatch, service, fake_openai_request):
    def raise_timeout(**kwargs):
        raise openai.APITimeoutError(request=fake_openai_request)

    monkeypatch.setattr(service.client.chat.completions, "create", raise_timeout)

    with pytest.raises(ApiException) as exc_info:
        service.generate("prompt")

    assert exc_info.value.status_code == 504


def test_generate_connection_error_maps_to_502(monkeypatch, service, fake_openai_request):
    def raise_connection_error(**kwargs):
        raise openai.APIConnectionError(request=fake_openai_request)

    monkeypatch.setattr(service.client.chat.completions, "create", raise_connection_error)

    with pytest.raises(ApiException) as exc_info:
        service.generate("prompt")

    assert exc_info.value.status_code == 502


def test_generate_rate_limit_maps_to_429(monkeypatch, service, fake_openai_response):
    def raise_rate_limit(**kwargs):
        raise openai.RateLimitError(
            "rate limited",
            response=fake_openai_response(429),
            body=None
        )

    monkeypatch.setattr(service.client.chat.completions, "create", raise_rate_limit)

    with pytest.raises(ApiException) as exc_info:
        service.generate("prompt")

    assert exc_info.value.status_code == 429


def test_generate_authentication_error_maps_to_500(monkeypatch, service, fake_openai_response):
    def raise_auth_error(**kwargs):
        raise openai.AuthenticationError(
            "bad key",
            response=fake_openai_response(401),
            body=None
        )

    monkeypatch.setattr(service.client.chat.completions, "create", raise_auth_error)

    with pytest.raises(ApiException) as exc_info:
        service.generate("prompt")

    assert exc_info.value.status_code == 500


def test_generate_generic_status_error_maps_to_502(monkeypatch, service, fake_openai_response):
    def raise_status_error(**kwargs):
        raise openai.APIStatusError(
            "model not found",
            response=fake_openai_response(404),
            body=None
        )

    monkeypatch.setattr(service.client.chat.completions, "create", raise_status_error)

    with pytest.raises(ApiException) as exc_info:
        service.generate("prompt")

    assert exc_info.value.status_code == 502
    assert "model not found" in exc_info.value.message
