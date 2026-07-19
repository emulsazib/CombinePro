"""OpenAI (Codex-family) connector via the official openai SDK."""
from __future__ import annotations

import openai

from app.agents.base import RESULT_SCHEMA, AgentError, BaseAgent


class OpenAIAgent(BaseAgent):
    provider = "openai"

    def __init__(self, name: str, model: str, api_key: str) -> None:
        super().__init__(name, model)
        self._client = openai.AsyncOpenAI(api_key=api_key)

    async def _complete(self, system_static: str, system_skeleton: str, user: str) -> str:
        try:
            resp = await self._client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_static},
                    {"role": "system", "content": f"AST skeleton of your domain:\n{system_skeleton}"},
                    {"role": "user", "content": user},
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {"name": "agent_result", "schema": RESULT_SCHEMA, "strict": True},
                },
            )
        except openai.RateLimitError as exc:
            retry_after = None
            try:
                retry_after = float(exc.response.headers.get("retry-after", ""))
            except (TypeError, ValueError, AttributeError):
                pass
            raise AgentError("OpenAI rate limit", retry_after=retry_after) from exc
        except openai.APIStatusError as exc:
            raise AgentError(f"OpenAI API error {exc.status_code}") from exc
        except openai.APIConnectionError as exc:
            raise AgentError(f"OpenAI connection error: {exc}") from exc

        choice = resp.choices[0] if resp.choices else None
        text = choice.message.content if choice and choice.message else None
        if not text:
            raise AgentError("OpenAI returned no content")
        return text
