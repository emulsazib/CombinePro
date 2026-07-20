"""OpenAI-protocol connector via the official openai SDK.

Also serves local OpenAI-compatible endpoints (Ollama `http://host:11434/v1`,
vLLM `http://host:8000/v1`) via `base_url` — dynamic "Local LLM" agents reuse
this class. Local servers that reject strict json_schema response_format get
one retry without it (the system prompt already demands JSON-only replies).
"""
from __future__ import annotations

import openai

from app.agents.base import RESULT_SCHEMA, AgentError, BaseAgent


class OpenAIAgent(BaseAgent):
    provider = "openai"

    def __init__(
        self,
        name: str,
        model: str,
        api_key: str,
        base_url: str | None = None,
        provider: str | None = None,
    ) -> None:
        super().__init__(name, model)
        self._client = openai.AsyncOpenAI(api_key=api_key, base_url=base_url)
        # Two independent things, deliberately not conflated: any non-OpenAI
        # endpoint may reject strict json_schema and needs the plain retry, but
        # only an unnamed one should be *labelled* "local" in the UI. Kimi and
        # GLM need the retry while keeping their own provider badge.
        self._schema_fallback = bool(base_url)
        if provider:
            self.provider = provider
        elif base_url:
            self.provider = "local"

    async def _complete(self, system_static: str, system_skeleton: str, user: str) -> str:
        messages = [
            {"role": "system", "content": system_static},
            {"role": "system", "content": f"AST skeleton of your domain:\n{system_skeleton}"},
            {"role": "user", "content": user},
        ]
        response_format = {
            "type": "json_schema",
            "json_schema": {"name": "agent_result", "schema": RESULT_SCHEMA, "strict": True},
        }
        try:
            try:
                resp = await self._client.chat.completions.create(
                    model=self.model, messages=messages, response_format=response_format
                )
            except openai.BadRequestError:
                if not self._schema_fallback:
                    raise
                # Endpoint doesn't support structured outputs — plain retry.
                resp = await self._client.chat.completions.create(
                    model=self.model, messages=messages
                )
        except openai.RateLimitError as exc:
            retry_after = None
            try:
                retry_after = float(exc.response.headers.get("retry-after", ""))
            except (TypeError, ValueError, AttributeError):
                pass
            raise AgentError(f"{self.provider} rate limit", retry_after=retry_after) from exc
        except openai.APIStatusError as exc:
            raise AgentError(f"{self.provider} API error {exc.status_code}") from exc
        except openai.APIConnectionError as exc:
            raise AgentError(f"{self.provider} connection error: {exc}") from exc

        choice = resp.choices[0] if resp.choices else None
        text = choice.message.content if choice and choice.message else None
        if not text:
            raise AgentError(f"{self.provider} returned no content")
        return text
