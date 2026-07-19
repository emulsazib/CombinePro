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
│                                │ Orchestrator     │              ├─ OpenAIAgent (openai)     │
│                                │  (locks, memory) │              ├─ GeminiAgent (google-genai)│
│                                └────────┬─────────┘              └─ StubAgent (no key)        │
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

1. Select a folder in the file tree, pick an agent in the **Agent Domains**
   dock, and click *Assign to selected folder*.
2. Edit any source file in that folder (in your normal editor). Watch the
   **Activity** dock: delta → router wake → agent result → memory write.
3. If the changed file is open in the viewer, it flips to a colored unified
   diff automatically (Debug → *Return viewer to file mode* to go back).
4. Debug → *Simulate cross-domain signal…* demonstrates the cross-domain
   protocol without needing a second live agent.

Allocations persist in `<workspace>/.combinepro/domains.json`; knbase state
lives in `<workspace>/.knbase/` and `<workspace>/memory-bank/`.

## Repository layout

| Path | What it is |
|---|---|
| `sidecar/server.js` | Express REST wrapper over knbase (`/init`, `/session/start`, `/context`, `/task/*`, `/log`, `/governance/:key`) |
| `app/main.py` | Entry point — qasync merges the Qt and asyncio loops |
| `app/core/` | Event bus, typed events, rule-based router, domain map, per-file lock registry, orchestrator |
| `app/agents/` | `BaseAgent` contract + Claude / OpenAI / Gemini / stub connectors |
| `app/context/` | tree-sitter AST skeletons + watchdog delta watcher |
| `app/memory/` | Async HTTP client for the sidecar |
| `app/ui/` | Main window, code viewer (highlight + diff), domain dock, activity feed |

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
