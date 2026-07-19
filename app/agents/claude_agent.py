"""Claude connector: official anthropic SDK, streaming, prompt-cached skeleton."""
from __future__ import annotations

import anthropic

from app.agents.base import RESULT_SCHEMA, AgentError, BaseAgent


class ClaudeAgent(BaseAgent):
    provider = "anthropic"

    def __init__(self, name: str, model: str, api_key: str) -> None:
        super().__init__(name, model)
        self._client = anthropic.AsyncAnthropic(api_key=api_key)

    async def _complete(self, system_static: str, system_skeleton: str, user: str) -> str:
        # System layout is cache-friendly: static instructions first, then the
        # AST skeleton with a cache breakpoint — the whole prefix is reused
        # across wakes while only the user turn (task + target file) varies.
        system = [
            {"type": "text", "text": system_static},
            {
                "type": "text",
                "text": f"AST skeleton of your domain:\n{system_skeleton}",
                "cache_control": {"type": "ephemeral"},
            },
        ]
        try:
            async with self._client.messages.stream(
                model=self.model,
                max_tokens=32_000,
                thinking={"type": "adaptive"},
                system=system,
                output_config={"format": {"type": "json_schema", "schema": RESULT_SCHEMA}},
                messages=[{"role": "user", "content": user}],
            ) as stream:
                message = await stream.get_final_message()
        except anthropic.RateLimitError as exc:
            retry_after = None
            try:
                retry_after = float(exc.response.headers.get("retry-after", ""))
            except (TypeError, ValueError):
                pass
            raise AgentError("Anthropic rate limit", retry_after=retry_after) from exc
        except anthropic.APIStatusError as exc:
            raise AgentError(f"Anthropic API error {exc.status_code}: {exc.message}") from exc
        except anthropic.APIConnectionError as exc:
            raise AgentError(f"Anthropic connection error: {exc}") from exc

        if message.stop_reason == "refusal":
            raise AgentError("Anthropic refused the request")
        if message.stop_reason == "max_tokens":
            raise AgentError("Anthropic reply truncated at max_tokens")
        text = next((b.text for b in message.content if b.type == "text"), "")
        if not text:
            raise AgentError("Anthropic returned no text content")
        return text
