# CombinePro — Multi-Agent AI IDE for Claude, GPT, Gemini, Kimi & GLM

**A local-first desktop IDE where multiple AI coding agents work on the same codebase at once** — each assigned its own role and its own folder, coordinated by a rule-based router, and governed by a shared knowledge base. Built with Python and PyQt6 for macOS and Windows.

[![Release](https://img.shields.io/github/v/release/emulsazib/CombinePro?label=release)](https://github.com/emulsazib/CombinePro/releases)
[![License: GPL v3](https://img.shields.io/badge/license-GPL--3.0-blue)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-macOS%20%7C%20Windows-1e2024)](#install)
[![Python](https://img.shields.io/badge/python-3.10%2B-3776ab)](#requirements-development)
[![Built with PyQt6](https://img.shields.io/badge/built%20with-PyQt6-41cd52)](https://www.riverbankcomputing.com/software/pyqt/)

Most AI coding tools are a single assistant in a chat box. CombinePro is an **AI agent orchestration platform**: you allocate domains and roles to several large language models, and they work in parallel — a Planning agent designs, a Backend agent implements, a Frontend agent builds the UI — without stepping on each other's files.

---

## Table of contents

- [Why CombinePro](#why-combinepro)
- [Key features](#key-features)
- [Supported AI models](#supported-ai-models)
- [How it works](#how-it-works)
- [Token optimization](#token-optimization)
- [Install](#install)
- [Quick start](#quick-start)
- [Assigning AI agent roles](#assigning-ai-agent-roles)
- [Settings reference](#settings-reference)
- [Build from source](#build-from-source)
- [Repository layout](#repository-layout)
- [FAQ](#faq)
- [Roadmap](#roadmap)
- [License](#license)
- [Open source](#open-source)

---

## Why CombinePro

| Typical AI coding assistant | CombinePro |
|---|---|
| One model, one conversation | **Many models in parallel**, each with a role and a folder |
| Ships your whole repo as context | **AST skeleton + one file** per call — bounded token cost |
| Chat history as memory | **Structured delta memory** in a governed knowledge base |
| Cloud editor or plugin | **Native desktop IDE** — your workspace stays on disk |
| Locked to one vendor | **Claude, OpenAI, Gemini, Kimi, GLM, or any local LLM** |

Useful when you want AI agents to own separate parts of a project, when you care what a model is actually sent, or when you want to mix a frontier model for planning with a cheap or local model for routine edits.

## Key features

### Multi-agent orchestration
- **Domain allocation** — assign any folder to an agent; it may only write inside that folder. Enforced in the orchestrator, not just in the prompt.
- **Functional roles** — Planning, Backend, Frontend, Database, Bug Fix, AI Building, Model Training, Action. Roles are independent of folders and reassignable at runtime.
- **Two-phase Plan → Act pipeline** — a Planning agent authors a plan, then the acting agents implement it with that plan in context. Planning agents are structurally prevented from writing source code.
- **Cross-domain signals** — an agent needing a change outside its folder raises a request; the router resolves the owner and wakes it.
- **Activate / deactivate** — switch any agent off from its card. It keeps its configuration and is never woken.

### Efficient by construction
- **AST-driven context** — agents get a tree-sitter skeleton (signatures and docstrings, bodies elided) plus the full text of the one file they may change.
- **Delta file sync** — the file watcher publishes debounced unified diffs, not full-file reads.
- **Lazy waking** — agents run no loops. Only the router wakes them, and each wake is one bounded API call.
- **Prompt caching** — the Claude connector caches the skeleton prefix, so repeat wakes in a domain reuse it.

### Governed shared memory
- Every completed task writes a structured summary to a local knowledge base ([`@vonneollc/knbase`](https://www.npmjs.com/package/@vonneollc/knbase)) through a bundled Node sidecar — six governance documents plus a searchable activity log, all inside your workspace.

### A real IDE
- Syntax-highlighted viewer with diffs, tabbed editor, integrated shell with history and live stdin, file tree with per-folder agent assignment, live agent cluster panel, and a copyable AI thought stream.

## Supported AI models

| Provider | Default model | Credential |
|---|---|---|
| **Anthropic Claude** | `claude-opus-4-8` | `ANTHROPIC_API_KEY` |
| **OpenAI** | `gpt-5.1` | `OPENAI_API_KEY` |
| **Google Gemini** | `gemini-2.5-pro` | `GEMINI_API_KEY` |
| **Moonshot Kimi** | `kimi-k2-0905-preview` | `KIMI_API_KEY` |
| **Zhipu GLM** | `glm-4.6` | `GLM_API_KEY` |
| **Ollama / vLLM / any OpenAI-compatible endpoint** | your choice | `LOCAL_BASE_URL` |

Model IDs are editable per agent. A provider with no key still appears in the roster as a labeled stub, so nothing breaks and you can see exactly what is missing.

**Run entirely offline** by pointing every agent at a local model (`LOCAL_BASE_URL=http://localhost:11434/v1` for Ollama).

## How it works

```
┌───────────────────────────── one process, one event loop (qasync) ─────────────────────────────┐
│                                                                                                │
│  PyQt6 UI                      asyncio core                            connectors              │
│  ┌─────────────────┐           ┌──────────────────┐                    ┌────────────────────┐  │
│  │ file tree       │           │ EventBus (pub/sub)│◄── FileDelta ─────│ watchdog watcher   │  │
│  │ code viewer/diff│◄─events──►│                  │◄── CrossDomain ──┐ │ (unified diffs)    │  │
│  │ agent cluster   │           │ LocalRouter      │                  │ └────────────────────┘  │
│  │ thought stream  │           │  (rule triage,   │──── wake ──► BaseAgent                     │
│  └─────────────────┘           │   debounce)      │              ├─ ClaudeAgent (anthropic)    │
│                                │ Orchestrator     │              ├─ OpenAIAgent (openai)       │
│                                │  (roles, locks,  │              ├─ GeminiAgent (google-genai) │
│                                │   plan→act,      │              ├─ Kimi / GLM (OpenAI proto)  │
│                                │   memory)        │              └─ StubAgent (no key)         │
│                                └────────┬─────────┘                                            │
│                                         │ Delta Memory (REST)                                  │
└─────────────────────────────────────────┼──────────────────────────────────────────────────────┘
                                          ▼
                     Node.js sidecar (Express) ──► @vonneollc/knbase
                     (governance docs, mind map, activity log in .knbase/ + memory-bank/)
```

**One wake, end to end:** you save a file (or send a prompt) → the watcher emits a debounced diff → the router triages it and picks the owning agent → the orchestrator builds a bounded context → the agent returns strict JSON → writes are applied under a per-file lock, scoped to its domain and role → the delta is recorded in the knowledge base → the UI updates from the event bus.

## Token optimization

Cost control is structural rather than advisory:

| Rule | Effect |
|---|---|
| Lazy waking | Agents never poll. One wake is one bounded API interaction. |
| AST skeleton | Signatures and docstrings only, capped in bytes (configurable). |
| Single mutable file | An agent receives the full text of exactly one file. |
| Debounced deltas | Rapid saves coalesce into a single wake. |
| Delta memory | Structured task summaries, never a growing chat transcript. |
| Prompt caching | The skeleton prefix is cached where the provider supports it. |

The skeleton cap, maximum file size, and router debounce are all live-editable in *Settings → AI Models*.

## Install

Download an installer from the [latest release](https://github.com/emulsazib/CombinePro/releases), or [build one yourself](#build-from-source).

| Platform | File | How to install |
|---|---|---|
| macOS | `CombinePro-1.0.5-macOS.dmg` | Open the DMG, drag **CombinePro** onto **Applications**. |
| Windows | `CombinePro-1.0.5-Windows-Setup.exe` | Double-click and follow the wizard. |

The app is self-contained — Python, Qt and every dependency are bundled. API keys are stored per user (`~/Library/Application Support/CombinePro/.env` on macOS, `%APPDATA%\CombinePro\.env` on Windows) and survive upgrades.

**Node.js is optional.** The memory sidecar is bundled and starts automatically when Node 18+ is present. Without it the app runs normally with Delta Memory offline — shown any time in *Settings → Memory & MCP*.

> **Unsigned builds:** without code-signing certificates, macOS Gatekeeper needs a right-click → *Open* on first launch, and Windows SmartScreen needs *More info → Run anyway*. See [Signing](#signing).

## Quick start

On first launch, choose a **workspace folder** (or set `COMBINEPRO_WORKSPACE` in `.env`). Then:

1. **Add your API keys** — *Settings → API Configuration*. Each field shows the key in use; clearing one disables that provider. Saving reloads the connectors immediately, with no restart.
2. **Assign a domain** — right-click a folder in the Explorer tree → *Assign Agent*. That agent may now write only inside that folder.
3. **Assign a role** — *Settings → Agents*, or **Configure** on any card in the Agents cluster.
4. **Prompt the agents** — the bar under the editor wakes the real agents with your instruction, routed by domain.
5. **Watch it work** — results stream into the AI Thought Stream, System Terminal and Recent Activity as they land.
6. **Run your code** — the top-bar **Run** button executes the open file into the System Terminal and toggles to **Stop** (SIGTERM, then SIGKILL after 1.5 s). The terminal stays interactive — typed lines go to the process's stdin — and doubles as a shell with history.

Agent profiles persist in `<workspace>/.combinepro/agents.json`, domains in `domains.json`, roles and on/off state in `agent_settings.json`. Knowledge-base state lives in `<workspace>/.knbase/` and `<workspace>/memory-bank/`.

## Assigning AI agent roles

A **domain** is *where* an agent may write. A **role** is *what kind of work it does*. They are independent, so a Backend agent can be scoped to `src/api/` while a Planning agent has no folder at all.

| Role | What the agent focuses on |
|---|---|
| **Planning** | Designs the implementation plan for the project lifecycle. Cannot write source files. |
| **Backend** | Server-side logic, APIs, services, jobs and their tests. |
| **Frontend** | UI components, views, styling, client state. |
| **Database** | Schemas, migrations, queries, indexes. |
| **Bug Fix** | Root-cause diagnosis and the smallest correct fix, plus a regression test. |
| **AI Building** | Prompts, agent loops, tool definitions, evals, model integrations. |
| **Model Training** | Datasets, training and evaluation loops, checkpoints, metrics. |
| **Action** | Implements work that has already been planned. |

**When one agent holds the Planning role**, prompts run a two-phase pipeline: the planner authors a plan first, then the acting agents implement it with the plan in context. With no Planning role assigned, every routed agent simply runs in parallel as before — the pipeline stays out of the way until you opt in.

File-save wakes deliberately skip the planning phase (it would double the cost of every keystroke-triggered wake), but they do inherit a recent plan for their domain.

## Settings reference

Every page is live: saving writes to `.env` **and** applies immediately. Only a workspace change needs a restart.

| Page | What it does |
|---|---|
| **API Configuration** | Provider keys, masked with a reveal toggle. Saving reloads connectors in place; clearing a key disables that provider. |
| **General** | Workspace folder and editor font size (applies live to open viewers and the terminal). |
| **AI Models** | Per-provider model IDs plus the token knobs — skeleton cap, max file size, router debounce — pushed onto the running orchestrator. |
| **Agents** | The live roster with provider, model, role and domain. Assign roles, add agents, remove user-added ones. |
| **Memory & MCP** | Sidecar URL plus a real *Test Connection* showing knowledge-base session state, governance status and recent log entries. |
| **Git & PRs** | Real repo state for the workspace — branch, remote, working tree, recent commits — read non-blocking via the `git` CLI. |
| **Usage & Diagnostics** | Live session counters (wakes, results, deltas, memory writes, signals) and the running environment. |

## Build from source

### Requirements (development)

- **Python ≥ 3.10** — Homebrew `python3.14` works; macOS system Python 3.9 does **not** (PyQt6 and tree-sitter ship `cp310-abi3` wheels).
- **Node.js ≥ 18** for the memory sidecar.

### Setup

```sh
# 1. Python virtual environment
python3 -m venv .venv
.venv/bin/pip install -r app/requirements.txt

# 2. Memory sidecar
cd sidecar && npm install && cd ..

# 3. API keys (optional — a missing key degrades that agent to a labeled stub)
cp .env.example .env
```

### Run

```sh
.venv/bin/python -m app.main
```

The sidecar starts automatically when Node is installed. To run it yourself:

```sh
cd sidecar && npm start          # listens on http://127.0.0.1:8787
```

### Package installers

```sh
# macOS  →  installer/dist/CombinePro-1.0.5-macOS.dmg
./installer/build_macos.sh

# Windows (must run ON Windows)  →  installer/dist/...-Windows-Setup.exe
powershell -ExecutionPolicy Bypass -File installer\build_windows.ps1
```

Each script vendors the sidecar's `node_modules`, regenerates the `.icns`/`.ico` from `AppIcons/`, runs PyInstaller, then **self-tests the bundle** (`CombinePro --selftest`) and refuses to package a broken build.

PyInstaller cannot cross-compile, so **each installer must be built on its own OS**. [`.github/workflows/build-installers.yml`](.github/workflows/build-installers.yml) does both on native runners — push a `v*` tag and it attaches the DMG and setup `.exe` to the release.

### Signing

```sh
# macOS — needs an Apple Developer ID
CODESIGN_IDENTITY="Developer ID Application: You (TEAMID)" ./installer/build_macos.sh

# Windows — sign the setup .exe with your certificate
signtool sign /fd SHA256 /a installer\dist\CombinePro-1.0.5-Windows-Setup.exe
```

In CI, set the `MACOS_CODESIGN_IDENTITY` repository secret.

## Repository layout

| Path | What it is |
|---|---|
| `app/main.py` | Entry point — qasync merges the Qt and asyncio loops |
| `app/core/` | Event bus, typed events, router, domain map, agent settings, locks, orchestrator |
| `app/agents/` | `BaseAgent` contract, role definitions, provider registry, connectors |
| `app/context/` | tree-sitter AST skeletons + watchdog delta watcher |
| `app/memory/` | Async sidecar client, governance document helpers, sidecar process supervisor |
| `app/ui/` | Main window, code viewer, Feather icon set, agent dialogs, theme |
| `app/ui/views/` | The three top-level views: Explorer, Agents cluster, Settings |
| `sidecar/server.js` | Express REST wrapper over knbase (`/init`, `/session/start`, `/context`, `/task/*`, `/log`, `/governance/:key`) |
| `installer/` | PyInstaller spec, icon generation, macOS/Windows build scripts |
| `AppIcons/` | Application icon source (16–1024 px) |

## FAQ

### Does my source code get sent to the AI providers?
Only a bounded slice. Each agent receives an AST skeleton of its own folder — signatures and docstrings, with function bodies removed — plus the full text of the single file it is allowed to change. Never the whole repository. To keep everything on your machine, point the agents at a local model through Ollama or vLLM.

### Can I use CombinePro without an API key?
Yes. Agents without a key appear as labeled stubs, so the full pipeline — routing, domains, roles, memory — still runs and is inspectable. Add a key whenever you want real completions.

### Can I run it fully offline with a local LLM?
Yes. Any OpenAI-compatible endpoint works. Set `LOCAL_BASE_URL` on an agent (for example `http://localhost:11434/v1` for Ollama, or a vLLM server) and no request leaves your network.

### How do multiple AI agents avoid conflicting edits?
Three mechanisms. Each agent may only write inside its allocated folder, enforced in the orchestrator. Every file write takes a per-file lock. And an agent that needs a change elsewhere raises a cross-domain request instead of reaching outside its domain.

### What is the difference between a domain and a role?
A domain is a folder — *where* an agent may write. A role is a specialty — *what* it works on. They compose, so a Backend agent can be scoped to `src/api/` while a Planning agent owns no folder at all.

### Is Node.js required?
No. It is only needed for the shared-memory sidecar. Without Node, CombinePro runs normally with Delta Memory offline, and says so in *Settings → Memory & MCP*.

### Which platforms are supported?
macOS and Windows have packaged installers. Linux is not packaged yet, but the app runs from source anywhere PyQt6 and tree-sitter wheels are available.

### Why does macOS say the app is damaged or unverified?
The published builds are unsigned. Right-click the app → *Open* on first launch, or build it yourself with a Developer ID via `CODESIGN_IDENTITY`.

### Can I add an agent that is not one of the built-ins?
Yes. *Agents → Add New Agent* takes a name, provider, model, role and an environment grid (pasting `KEY=value` splits automatically; secrets are masked). Profiles persist in `<workspace>/.combinepro/agents.json` and reload on startup.

## Roadmap

- Cross-process file locks
- WebSocket push from the memory sidecar
- A local-LLM triage model (drop-in replacement for the rule-based router)
- Per-agent cost and token dashboards
- Linux packaging

## License

CombinePro is free and open source software, released under the
**[GNU General Public License v3.0](LICENSE)**.

Copyright © 2026 Emul Ahamed Sazib.

### What that means

| You may | On this condition |
|---|---|
| Use it for anything, including commercially | — |
| Read, study and modify the source | — |
| Share it, modified or not | Recipients get the same freedoms |
| Sell it or build a business on it | — |
| Distribute a modified version | You publish your source under GPL-3.0 too |

There is **no warranty**. See sections 15 and 16 of the [LICENSE](LICENSE).

### Why GPL-3.0 specifically

CombinePro's UI is built on **PyQt6**, which Riverbank Computing dual-licenses
as GPL-3.0 or a paid commercial licence. Any application that links PyQt6
without a commercial licence must itself be distributed under GPL-compatible
terms, so GPL-3.0 is the licence that makes the published installers compliant.

If you need to ship a closed-source derivative, you have two routes: buy a
[commercial PyQt licence](https://www.riverbankcomputing.com/commercial/pyqt)
from Riverbank, or port the UI layer to **PySide6**, the Qt Company's LGPL
binding.

## Open source

CombinePro is developed in the open. Issues, discussions and pull requests are
welcome at [github.com/emulsazib/CombinePro](https://github.com/emulsazib/CombinePro).
Contributions are accepted under the project's GPL-3.0 licence.

Getting set up takes three commands — see [Build from source](#build-from-source).
Before opening a pull request, please run the bundle self-test:

```sh
.venv/bin/python -c "from app.selftest import run; raise SystemExit(run())"
```

### Third-party components

CombinePro stands on other people's work. The installers redistribute these,
and their licences travel with them:

| Component | Licence | Role |
|---|---|---|
| [Qt 6](https://www.qt.io/) | LGPL-3.0 | UI toolkit |
| [PyQt6](https://www.riverbankcomputing.com/software/pyqt/) | GPL-3.0 | Python bindings for Qt |
| [Feather Icons](https://feathericons.com/) | MIT | Icon set, embedded in `app/ui/feather.py` |
| [@vonneollc/knbase](https://www.npmjs.com/package/@vonneollc/knbase) | MIT | Governed knowledge base |
| [tree-sitter](https://tree-sitter.github.io/) + language pack | MIT | AST skeleton parsing |
| [qasync](https://github.com/CabbageDevelopment/qasync) | BSD-2-Clause | Qt/asyncio event-loop bridge |
| [watchdog](https://github.com/gorakhargosh/watchdog) | Apache-2.0 | Filesystem watching |
| [httpx](https://www.python-httpx.org/) · [python-dotenv](https://github.com/theskumar/python-dotenv) | BSD-3-Clause | HTTP client · env loading |
| [anthropic](https://github.com/anthropics/anthropic-sdk-python) | MIT | Claude connector |
| [openai](https://github.com/openai/openai-python) · [google-genai](https://github.com/googleapis/python-genai) | Apache-2.0 | OpenAI · Gemini connectors |
| [PyInstaller](https://pyinstaller.org/) | GPL-2.0 with bootloader exception | Packaging (the exception permits distributing the result) |
| [Express](https://expressjs.com/) and the sidecar's npm tree | MIT / ISC / BSD | Memory sidecar HTTP layer |

Full licence texts ship inside each package in `.venv/` and
`sidecar/node_modules/`.

---

**Keywords:** multi-agent AI IDE · AI coding assistant · AI agent orchestration · Claude Opus · GPT-5.1 · Gemini 2.5 Pro · Kimi K2 · GLM-4.6 · Ollama · vLLM · local LLM IDE · PyQt6 desktop app · token optimization · AI pair programming · autonomous coding agents
