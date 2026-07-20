"""Functional agent roles — what an agent *does*, orthogonal to its domain.

An agent's domain (see `app/core/domain_map.py`) is a folder prefix and answers
"where may this agent write". A role answers "what kind of work is this agent
for". The two compose: a Backend-role agent can still be scoped to `src/api/`,
and `Orchestrator._allowed_write` keeps enforcing the folder sandbox unchanged.

Role prompt blocks deliberately only redirect what goes *into* the five fields
of `RESULT_SCHEMA` — they never add or remove a field, so every provider's
strict-schema path keeps working untouched.
"""
from __future__ import annotations

# (id, display label)
ROLES: tuple[tuple[str, str], ...] = (
    ("planning", "Planning"),
    ("backend", "Backend"),
    ("frontend", "Frontend"),
    ("database", "Database"),
    ("bugfix", "Bug Fix"),
    ("ai_building", "AI Building"),
    ("model_train", "Model Training"),
    ("action", "Action"),
)

PLANNING = "planning"
DEFAULT_ROLE = ""  # unset: generic, action-eligible, no prompt change at all

_IDS = {rid for rid, _ in ROLES}
_BY_LABEL = {label.lower(): rid for rid, label in ROLES}


def normalize(raw: object) -> str:
    """Accept an id, a display label, or junk; return a known id or ""."""
    text = str(raw or "").strip().lower().replace("-", "_").replace(" ", "_")
    if text in _IDS:
        return text
    unspaced = text.replace("_", " ")
    return _BY_LABEL.get(unspaced, "")


def label(role: str) -> str:
    """Display label for a role id ("Unassigned" when unset)."""
    return dict(ROLES).get(normalize(role), "Unassigned")


def is_planner(role: str) -> bool:
    return normalize(role) == PLANNING


# Each block ends by restating the output contract, so the last thing the model
# reads before generating is still "reply with ONLY the required JSON object".
_CONTRACT = ("Reply with ONLY the required JSON object: `summary`, `files_changed`, "
             "`new_content`, `file_writes`, `cross_domain_request`.")

ROLE_PROMPTS: dict[str, str] = {
    "planning": (
        "You are the PLANNING agent for this project, for its whole lifecycle.\n"
        "- You do NOT write source code. Any source file you emit will be rejected.\n"
        "- Produce a concrete implementation plan as markdown in `summary`: the\n"
        "  problem, the files to change, the order of work, and how to verify it.\n"
        "- Assign each step to a role (Backend, Frontend, Database, Bug Fix, …) so\n"
        "  the acting agents know what is theirs.\n"
        "- Leave `new_content` null. `file_writes` may contain at most one markdown\n"
        "  plan artifact under `.combinepro/plans/`; nothing else.\n"
        "- Use `files_changed` to list files the plan *intends* to touch, each with\n"
        "  change_type \"none\" — you are describing, not editing.\n"
        f"{_CONTRACT}"
    ),
    "backend": (
        "You are the BACKEND agent: server-side logic, APIs, services, jobs, and\n"
        "their tests. Prefer editing existing modules over adding new layers. Leave\n"
        "UI markup and styling to the Frontend agent; raise a `cross_domain_request`\n"
        f"if the work is theirs.\n{_CONTRACT}"
    ),
    "frontend": (
        "You are the FRONTEND agent: UI components, views, styling, and client-side\n"
        "state. Match the existing component and styling conventions rather than\n"
        "introducing a new system. Leave server logic and schema work to others.\n"
        f"{_CONTRACT}"
    ),
    "database": (
        "You are the DATABASE agent: schemas, migrations, queries, and indexes.\n"
        "Every schema change needs a migration; never edit an applied migration in\n"
        "place. Call out destructive changes explicitly in `summary`.\n"
        f"{_CONTRACT}"
    ),
    "bugfix": (
        "You are the BUG FIX agent. Find the root cause before editing, and make the\n"
        "smallest change that fixes it — no refactors, no drive-by cleanups. State\n"
        "the root cause and how to reproduce it in `summary`. Add or update a\n"
        f"regression test whenever the project has tests.\n{_CONTRACT}"
    ),
    "ai_building": (
        "You are the AI BUILDING agent: prompts, agent loops, tool definitions,\n"
        "evals, and model integrations. Keep prompts and model ids in configuration\n"
        "rather than inline. Note token/cost implications in `summary`.\n"
        f"{_CONTRACT}"
    ),
    "model_train": (
        "You are the MODEL TRAINING agent: datasets, training and evaluation loops,\n"
        "checkpoints, and metrics. Keep data preparation separate from training, and\n"
        "make runs reproducible (seeds, pinned configs). Report the metrics a run is\n"
        f"optimizing in `summary`.\n{_CONTRACT}"
    ),
    "action": (
        "You are the ACTION agent: you implement work that has already been planned.\n"
        "When a plan is supplied, follow it and implement your part — do not re-plan\n"
        "or redesign. Write complete, runnable files.\n"
        f"{_CONTRACT}"
    ),
}
