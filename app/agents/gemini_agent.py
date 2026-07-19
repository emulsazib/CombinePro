"""Gemini connector via the official google-genai SDK."""
from __future__ import annotations

from google import genai
from google.genai import errors as genai_errors
from google.genai import types as genai_types

from app.agents.base import RESULT_SCHEMA, AgentError, BaseAgent


class GeminiAgent(BaseAgent):
    provider = "google"

    def __init__(self, name: str, model: str, api_key: str) -> None:
        super().__init__(name, model)
        self._client = genai.Client(api_key=api_key)

    async def _complete(self, system_static: str, system_skeleton: str, user: str) -> str:
        config = genai_types.GenerateContentConfig(
            system_instruction=f"{system_static}\n\nAST skeleton of your domain:\n{system_skeleton}",
            response_mime_type="application/json",
            response_json_schema=RESULT_SCHEMA,
        )
        try:
            resp = await self._client.aio.models.generate_content(
                model=self.model,
                contents=user,
                config=config,
            )
        except genai_errors.APIError as exc:
            if getattr(exc, "code", None) == 429:
                raise AgentError("Gemini rate limit") from exc
            raise AgentError(f"Gemini API error: {exc}") from exc

        text = getattr(resp, "text", None)
        if not text:
            raise AgentError("Gemini returned no text content")
        return text
