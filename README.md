# CombinePro

A real-time, token-optimized, multi-agent collaborative IDE. Multiple LLMs
(Claude, OpenAI, Gemini) work on the same codebase simultaneously under strict
domain allocations, coordinated by a local rule-based router and governed by a
shared memory system (`@vonneollc/knbase`).

## Architecture

```
┌───────────────────────────── one process, one event loop (qasync) ─────────────────────────────┐
│                                                                                                │
│  PyQt6 UI                      asyncio core                            connectors              │
│  ┌─────────────────┐           ┌──────────────────┐                    ┌────────────────────┐  │
│  │ file tree       │           │ EventBus (pub/sub)│◄── FileDelta ─────│ watchdog watcher   │  │
│  │ code viewer/diff│◄─events──►│                  │◄── CrossDomain ──┐ │ (unified diffs)    │  │
│  │ domain dock     │           │ LocalRouter      │                  │ └────────────────────┘  │
│  │ activity feed   │           │  (rule triage,   │──── wake ──► BaseAgent                     │
│  └─────────────────┘           │   debounce)      │              ├─ ClaudeAgent (anthropic)    │
│                                │ Orchestrator     │              ├─ OpenAIAgent (openai)       │
│                                │  (locks, memory) │              ├─ GeminiAgent (google-genai) │
│                                └────────┬─────────┘              └─ StubAgent (no key)         │
│                                         │ Delta Memory (REST)                                  │
└─────────────────────────────────────────┼──────────────────────────────────────────────────────┘
                                          ▼
                     Node.js sidecar (Express) ──► @vonneollc/knbase
                     (governance docs, mind map, activity log in .knbase/ + memory-bank/)
```

### Token-optimization rules (enforced structurally)

- **Lazy waking** — agents run no loops; only `LocalRouter` may call
  `agent.wake()`, and each wake is one bounded API interaction.
- **AST-driven context** — agents receive a tree-sitter skeleton of their
  domain (signatures + docstrings, bodies elided; `app/context/ast_skeleton.py`)
  plus the full text of the *single* file they may mutate. Never the codebase.
- **Delta memory** — no shared chat logs. Each completed task writes a strict
  JSON structural summary to knbase via the sidecar (`/task/complete`, with an
  activity-log fallback while governance docs are unbootstrapped).
- **Delta file sync** — the watcher publishes debounced unified diffs, not
  full-file reads. Agent writes are echo-suppressed so they don't re-wake agents.
- **Cross-domain signal protocol** — an agent needing an out-of-domain change
  emits `{"target_domain", "request", "urgency"}`; the router resolves the
  domain and wakes the owning agent.

## Requirements

- **Python ≥ 3.10** (Homebrew `python3.14` works; the macOS system 3.9 does
  **not** — PyQt6/tree-sitter ship `cp310-abi3` wheels).
- **Node.js ≥ 18** for the memory sidecar.

## Setup

```sh
# 1. Python venv
/opt/homebrew/bin/python3.14 -m venv .venv
.venv/bin/pip install -r app/requirements.txt

# 2. Sidecar
cd sidecar && npm install && cd ..

# 3. Keys (optional — missing keys degrade that agent to a labeled stub)
cp .env.example .env   # then fill in ANTHROPIC_API_KEY / OPENAI_API_KEY / GEMINI_API_KEY
```

## Run

```sh
# Terminal 1 — memory sidecar
cd sidecar && npm start          # listens on http://127.0.0.1:8787

# Terminal 2 — the IDE
.venv/bin/python -m app.main
```

On first launch you'll be asked to choose a **workspace folder** (or set
`COMBINEPRO_WORKSPACE` in `.env`). Then:

1. **Assign domains** — right-click a folder in the Explorer file tree →
   *Assign Agent* → pick an agent. Assignments show on the Agents page.
2. **Watch the pipeline** — edit any source file in an assigned folder (in any
   editor): delta → router wake → agent result stream into the AI Thought
   Stream, System Terminal, and Recent Activity.
3. **Prompt agents** — the ⚡ bar under the editor wakes the real agents with
   your instruction (routed per domain assignments).
4. **Run / Stop** — the top-bar ▶ Run button executes the open file, streaming
   output into the System Terminal; it toggles to a red ■ Stop that terminates
   the process safely (SIGTERM, then SIGKILL after 1.5 s). The terminal input
   line stays interactive while a process runs — typed lines go to its stdin —
   and it doubles as a shell (`ls`, `git status`, `cd`, `clear`, history keys).
5. **Add agents** — Agents page → *⊕ Add New Agent*: pick Commercial
   (OpenAI / Anthropic / Gemini) or Local (Ollama / vLLM / custom
   OpenAI-compatible), fill the key-value env grid (`KEY=value` pastes are
   split automatically; secrets are masked), and *Save Agent*. Profiles persist
   in `<workspace>/.combinepro/agents.json` and reload on startup; local
   endpoints run through the OpenAI-compatible connector
   (e.g. `LOCAL_BASE_URL=http://localhost:11434/v1` for Ollama).

Allocations persist in `<workspace>/.combinepro/domains.json`; knbase state
lives in `<workspace>/.knbase/` and `<workspace>/memory-bank/`.

## Settings

All seven Settings pages are live. Saving writes to `.env` **and** applies
immediately — only a workspace change needs a restart.

| Page | What it does |
|---|---|
| **API Configuration** | Provider keys (masked, reveal toggle). Saving reloads the connectors in place. |
| **General** | Workspace folder (restart-scoped) and editor font size (applies live to open viewers + terminal). |
| **AI Models** | Per-provider model IDs and the token knobs — AST skeleton cap, max file size, router debounce — pushed onto the running orchestrator. |
| **Agents** | The live roster with provider/model/domain. Add agents via the dialog; user-added ones can be removed (which clears their domains). Built-ins are key-driven. |
| **Memory & MCP** | Sidecar URL (live-applied) plus a real *Test Connection* showing knbase session state, governance status and the latest log entries. |
| **Git & PRs** | Real repo state for the workspace — branch, remote, working tree, recent commits — read non-blocking via the `git` CLI. |
| **Usage & Diagnostics** | Live session counters (wakes, results, deltas, memory writes, signals) and the running environment. |

## Repository layout

| Path | What it is |
|---|---|
| `sidecar/server.js` | Express REST wrapper over knbase (`/init`, `/session/start`, `/context`, `/task/*`, `/log`, `/governance/:key`) |
| `app/main.py` | Entry point — qasync merges the Qt and asyncio loops |
| `AppIcons/` | Application icon source (16–1024px set, loaded by `app/ui/icons.py`) |
| `app/core/` | Event bus, typed events, rule-based router, domain map, per-file lock registry, orchestrator |
| `app/agents/` | `BaseAgent` contract + Claude / OpenAI / Gemini / stub connectors |
| `app/context/` | tree-sitter AST skeletons + watchdog delta watcher |
| `app/memory/` | Async HTTP client for the sidecar |
| `app/ui/` | Main window, code viewer (highlight + diff), agent dialog, activity feed |
| `app/ui/views/` | The three top-level views: Explorer workspace, Agents cluster, Settings |
| `app/ui/views/settings_pages/` | The seven Settings pages (API, General, AI Models, Agents, Memory & MCP, Git & PRs, Usage & Diagnostics) |

## Notes & next steps

- The Claude connector uses streaming, adaptive thinking, and a prompt-cached
  system block for the AST skeleton, so repeat wakes in the same domain reuse
  the cached prefix. OpenAI/Gemini model IDs are configurable via `.env`.
- knbase starts in `NEEDS_BOOTSTRAP` until its six governance docs are
  authored (`POST /governance/:key`); until then, task deltas fall back to
  activity-log appends — visible in `GET /log`.
- Planned next: cross-process file locks, WebSocket push from the sidecar,
  an Ollama-backed `TriageModel` (drop-in for `RuleBasedTriage`), per-agent
  cost dashboards.
