"""Tests for the Ollama provider (LEG-63).

No server is contacted. A mock transport stands in for the network, so these
tests check the two things that are actually this class's job: that it builds
the right request, and that every way the call can fail becomes an LLMError
rather than something unexpected escaping into the service above it.
"""

import json

import httpx
import pytest

from services.llm import LLMError
from services.ollama_llm import OllamaLLMProvider


def transport_returning(payload: object, status_code: int = 200) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json=payload)

    return httpx.MockTransport(handler)


# --- the happy path --------------------------------------------------------


def test_the_reply_text_is_returned() -> None:
    provider = OllamaLLMProvider(transport=transport_returning({"response": "42 days [1]."}))

    reply = provider.generate("how long?")

    print(f"reply={reply!r}")
    assert reply == "42 days [1]."


def test_the_request_carries_the_prompt_model_and_zero_temperature() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        seen["url"] = str(request.url)
        return httpx.Response(200, json={"response": "ok"})

    provider = OllamaLLMProvider(
        model="test-model",
        host="http://example:11434",
        transport=httpx.MockTransport(handler),
    )
    provider.generate("the prompt")

    print(seen)
    assert seen["model"] == "test-model"
    assert seen["prompt"] == "the prompt"
    assert seen["stream"] is False
    assert seen["options"] == {"temperature": 0.0}
    assert seen["url"] == "http://example:11434/api/generate"


def test_a_trailing_slash_on_the_host_does_not_double_up() -> None:
    provider = OllamaLLMProvider(host="http://example:11434/")
    assert provider.host == "http://example:11434"


# --- every way it can fail -------------------------------------------------


def test_an_error_status_becomes_an_llm_error() -> None:
    provider = OllamaLLMProvider(
        transport=transport_returning({"error": "model not found"}, status_code=404)
    )

    with pytest.raises(LLMError) as caught:
        provider.generate("q")

    print(f"raised: {caught.value}")
    assert "404" in str(caught.value)


def test_an_unreachable_server_becomes_an_llm_error() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    provider = OllamaLLMProvider(transport=httpx.MockTransport(refuse))

    with pytest.raises(LLMError) as caught:
        provider.generate("q")

    print(f"raised: {caught.value}")
    assert "Could not reach Ollama" in str(caught.value)


def test_a_reply_without_the_expected_field_becomes_an_llm_error() -> None:
    """A 200 that contains no answer must not surface as a KeyError upstairs."""
    provider = OllamaLLMProvider(transport=transport_returning({"unexpected": "shape"}))

    with pytest.raises(LLMError):
        provider.generate("q")


# --- configuration ---------------------------------------------------------


def test_model_and_host_come_from_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OLLAMA_MODEL", "from-env")
    monkeypatch.setenv("OLLAMA_HOST", "http://elsewhere:1234")

    provider = OllamaLLMProvider()

    print(f"model={provider.model} host={provider.host}")
    assert provider.model == "from-env"
    assert provider.host == "http://elsewhere:1234"


def test_explicit_arguments_win_over_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OLLAMA_MODEL", "from-env")

    assert OllamaLLMProvider(model="explicit").model == "explicit"
