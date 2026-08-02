"""Company-hosted LLM, via an OpenAI-compatible chat completions API (LEG-63).

Same shape as OllamaLLMProvider — this exists as a separate class rather than
a config flag on it because the request/response shape genuinely differs
(chat-completions messages + bearer auth, vs. Ollama's own /api/generate).
Swapping between them is still just choosing which provider gets built in
query_router.py; RagService and AnswerService never know which one is live.

Config comes from the environment, so which model or endpoint is in use is a
config change, not a code change.
"""

import os
from typing import Any

import httpx

from services.llm import LLMError, LLMProvider

DEFAULT_MODEL = "gpt-oss"
DEFAULT_TIMEOUT_SECONDS = 120.0


class CompanyLLMProvider(LLMProvider):
    """Talks to the company's hosted chat-completions endpoint.

    Accepts an injected transport so the request this builds can be inspected
    without a live server, same as OllamaLLMProvider.
    """

    def __init__(
        self,
        api_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.api_url = (api_url or os.environ["COMPANY_API_URL"]).rstrip("/")
        self.api_key = api_key or os.environ["COMPANY_API_KEY"]
        self.model = model or os.environ.get("COMPANY_LLM_MODEL", DEFAULT_MODEL)
        self.timeout = timeout
        self._transport = transport

    def generate(self, prompt: str) -> str:
        try:
            with httpx.Client(timeout=self.timeout, transport=self._transport) as client:
                response = client.post(
                    f"{self.api_url}/v1/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json={
                        "model": self.model,
                        "messages": [{"role": "user", "content": prompt}],
                        # Same reasoning as everywhere else: the same question
                        # over the same passages must give the same answer
                        # every time.
                        "temperature": 0,
                    },
                )
        except httpx.HTTPError as exc:
            raise LLMError(f"Could not reach {self.api_url}: {exc}") from exc

        if response.status_code != 200:
            raise LLMError(f"Company API returned {response.status_code}: {response.text[:300]}")

        return self._text(response.json())

    @staticmethod
    def _text(payload: Any) -> str:
        try:
            return str(payload["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError(f"Unexpected response shape: {payload}") from exc
