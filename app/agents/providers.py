"""One registry of provider facts, shared by the orchestrator and every UI form.

Model ids, env-var names and base URLs were previously repeated across
`config.py`, `.env.example` and `agent_dialog.py`, which let them drift. The
config dialogs, the API Configuration page and `_register_profile` all read
this instead.

Kimi (Moonshot) and GLM (Zhipu) both speak the OpenAI protocol, so they reuse
`OpenAIAgent` with a preset `base_url` — but they keep their own provider id so
the UI badges them correctly instead of calling them "local".
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Provider:
    id: str
    label: str  # shown in the Configure / Add Agent dropdowns
    kind: str  # "commercial" | "local"
    env_key: str  # the credential this provider cannot work without
    models: tuple[str, ...]  # suggested versions, newest first; editable in the UI
    base_url: str = ""  # OpenAI-compatible endpoint ("" = the SDK default)
    extra_env: tuple[tuple[str, str], ...] = field(default_factory=tuple)


PROVIDERS: tuple[Provider, ...] = (
    Provider(
        id="anthropic", label="Claude (Anthropic)", kind="commercial",
        env_key="ANTHROPIC_API_KEY",
        models=("claude-opus-4-8", "claude-sonnet-5", "claude-haiku-4-5-20251001"),
    ),
    Provider(
        id="openai", label="OpenAI", kind="commercial",
        env_key="OPENAI_API_KEY",
        models=("gpt-5.1", "gpt-5", "gpt-4o"),
    ),
    Provider(
        id="gemini", label="Gemini (Google)", kind="commercial",
        env_key="GEMINI_API_KEY",
        models=("gemini-2.5-pro", "gemini-2.5-flash"),
    ),
    Provider(
        id="kimi", label="Kimi (Moonshot)", kind="commercial",
        env_key="KIMI_API_KEY",
        models=("kimi-k2-0905-preview", "moonshot-v1-128k", "moonshot-v1-32k"),
        base_url="https://api.moonshot.cn/v1",
    ),
    Provider(
        id="glm", label="GLM (Zhipu)", kind="commercial",
        env_key="GLM_API_KEY",
        models=("glm-4.6", "glm-4-plus", "glm-4-flash"),
        base_url="https://open.bigmodel.cn/api/paas/v4",
    ),
    Provider(
        id="ollama", label="Local — Ollama", kind="local",
        env_key="LOCAL_BASE_URL",
        models=("llama3.1", "qwen2.5-coder", "deepseek-coder-v2"),
        extra_env=(("LOCAL_BASE_URL", "http://localhost:11434/v1"), ("LOCAL_API_KEY", "ollama")),
    ),
    Provider(
        id="vllm", label="Local — vLLM", kind="local",
        env_key="LOCAL_BASE_URL",
        models=("meta-llama/Llama-3.1-8B-Instruct",),
        extra_env=(("LOCAL_BASE_URL", "http://localhost:8000/v1"), ("LOCAL_API_KEY", "")),
    ),
    Provider(
        id="custom", label="Local — Custom (OpenAI-compatible)", kind="local",
        env_key="LOCAL_BASE_URL",
        models=(),
        extra_env=(("LOCAL_BASE_URL", ""), ("LOCAL_API_KEY", "")),
    ),
)

BY_ID: dict[str, Provider] = {p.id: p for p in PROVIDERS}

# Providers backed by a key in .env (the API Configuration page). Local ones are
# configured per-agent instead, so they are excluded.
KEYED: tuple[Provider, ...] = tuple(p for p in PROVIDERS if p.kind == "commercial")


def get(provider_id: str) -> Provider | None:
    return BY_ID.get(str(provider_id or "").strip().lower())


def default_model(provider_id: str) -> str:
    p = get(provider_id)
    return p.models[0] if p and p.models else ""


def env_rows(provider_id: str) -> tuple[tuple[str, str], ...]:
    """Starter env rows for the Add-Agent grid."""
    p = get(provider_id)
    if p is None:
        return ()
    return p.extra_env or ((p.env_key, ""),)
