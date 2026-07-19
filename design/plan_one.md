# CombinePro — "Obsidian Logic" Multi-View Dashboard

## Context

The user supplied a complete Stitch design package in `design/` — five mockups
(HTML + PNG), a design-system doc (`design/obsidian_logic/DESIGN.md`), and a
PyQt6 structural reference (`design/pyqt6_ide_implementation.txt`). The design is
tailored to CombinePro: it references `ast_skeleton.py`, the diff view, `agents/`,
pytest, per-agent state badges, and API-key config. The task is to **rebuild the
CombinePro dashboard to match this design as a full multi-view app, and make the
layout responsive.**

This **replaces** the indigo-violet theme from the previous session with the
**"Obsidian Logic"** system: deep obsidian (`#111317`) + terminal-green primary
(`#00ff9c`/`#00e38a`) + logic-blue secondary (`#adc6ff`/`#0566d9`), **sharp 0px
corners**, **1px borders**, Inter + JetBrains Mono, high-density IDE aesthetic.

Confirmed with the user: **full multi-view app** (Explorer / Agents / Settings),
and **full visual shell with real data where it exists** (representative/static
where CombinePro has no backing). All of `core/`, `agents/`, `context/`,
`memory/`, and `sidecar/` are untouched — this is UI only.

## Design system (exact tokens — `design/obsidian_logic/DESIGN.md` + orchestration HTML)

- **Surfaces**: bg `#111317`, lowest `#0c0e12`, low `#1a1c20`, container `#1e2024`,
  high `#282a2e`, highest `#333539`, bright `#37393e`.
- **Text/lines**: on-surface `#e2e2e8`, variant `#b9cbbc`, outline `#849587`,
  outline-variant (borders) `#3b4b3f`.
- **Primary (green)**: container `#00ff9c`, tint `#00e38a`, on-primary `#00391f`,
  inverse `#006d40`. **Secondary (blue)**: `#adc6ff` / container `#0566d9`.
  **Tertiary (amber)**: `#ffe17a` / `#ffdd65`. **Error (red)**: `#ffb4ab` /
  container `#93000a`.
- **Agent states**: ACTIVE green `#00e38a`, RUNNING blue `#adc6ff`, IDLE gray
  `#849587`, ERROR red `#ffb4ab` (glowing circular dots).
- **Syntax**: keyword `#ffb4ab`, func/def `#00e38a`, string `#ffe17a`, comment
  `#849587`; numbers `#adc6ff`.
- **Type**: Inter (UI: h1 24/600, h2 18/600, body 14/400, caps-label 10/700
  +0.05em), JetBrains Mono (code 13/450, terminal). Font stacks degrade to
  SF Pro / SF Mono / Menlo (Inter/JetBrains Mono used if installed — no download).
- **Shape/density**: radius 0 everywhere except status dots; 1px `#3b4b3f`
  borders as separators (not shadows); button padding `4px 12px`; scrollbars 4px
  (track `#1a1c20`, thumb `#3b4b3f`, hover `#00e38a`).

## Architecture — persistent chrome + 3 stacked views

`QMainWindow`:
- **Top bar** (`QToolBar#topbar`): "CombinePro" logo (green), nav tabs, spacer,
  **Run** (green) / **Sync** (ghost) buttons, cluster icons, avatar. On narrow
  width collapses to a hamburger.
- **Central `QStackedWidget`** switched by the left nav (Explorer / Agents /
  Settings):
  1. **WorkspaceView** (Explorer) — `[NavSidebar + file tree | tabbed editor +
     terminal | Agent Cluster panel]`.
  2. **ClusterView** (Agents) — `[NavSidebar | stat cards + agent grid + recent
     activity]`.
  3. **SettingsView** (Settings) — `[settings nav | settings panels incl. API
     config]`.
- **Bottom `QStatusBar`**: green "SYSTEM ONLINE" dot, sidecar/API status, agent
  count, workspace, latency (representative), version.

`NavSidebar` (shared widget) holds the DevOS/CombinePro header + Explorer/Agents/
Settings `NavButton`s + Settings/Help at bottom; emits view-switch signals.
QDockWidgets are dropped entirely — everything is fixed `QSplitter` panels (the
mockups have no floating docks).

## New / rewritten UI modules

- **`app/ui/theme.py`** (rewrite) — Obsidian tokens above, `dark_palette()`,
  `build_stylesheet()` (sharp corners, 1px borders, 4px scrollbars, caps labels),
  `apply_theme(app)` (Fusion + palette + font stacks; `addApplicationFont` if
  Inter/JetBrains Mono files ever bundled, else graceful fallback).
- **`app/ui/flow_layout.py`** — standard Qt wrapping layout for the responsive
  stat-card row and agent grid.
- **`app/ui/widgets.py`** (expand) — `StateBadge` (caps + glowing dot),
  `AgentCard` (compact for side panel / full for grid with latency, success,
  Configure/Deactivate), `StatCard` (metric tiles), `NavButton`, `SectionHeader`
  (caps), `ClusterLoadChart` (paintEvent bar chart), `ThoughtStream` (chat-style
  real AgentResult/cross-domain feed), `LogTerminal` (mono, green prompt),
  `StatusPill`.
- **`app/ui/log_bridge.py`** — a `logging.Handler` → `pyqtSignal(str)` so
  `LogTerminal` shows **real** orchestrator logs (`app.core.*`, `app.agents.*`)
  thread-safely.
- **`app/ui/editor_tabs.py`** — `QTabBar` + `QStackedWidget` of `CodeViewer`s
  keyed by path; opening a tree file adds a tab; a **"Diff View"** tab appears on
  `FileDelta` (renders the review-console diff + a compact "AI Analysis" side
  panel populated from the matching `AgentResult`).
- **`app/ui/views/{workspace_view,cluster_view,settings_view}.py`** — the three
  stacked pages.

## Modified existing files

- **`app/ui/main_window.py`** (major rewrite) — top bar + nav + `QStackedWidget`
  + status bar; central bus subscription in `run_event_pump` dispatching each
  event to the views that need it (agent cards, thought stream, terminal, recent
  activity, cluster load, sidecar pill); `resizeEvent` responsiveness (below).
- **`app/ui/highlighter.py`** — syntax colors → Obsidian tokens.
- **`app/ui/code_viewer.py`** — gutter/current-line/selection → Obsidian tokens
  (Qt `#AARRGGBB` alpha ordering, per the bug fixed last session).
- **`app/ui/activity_dock.py`** → trimmed to a formatting module: keep
  `describe(event)` + `_event_color()` (reused by `ThoughtStream` / recent
  activity); drop the `QDockWidget`.
- **`app/ui/domain_dock.py`** — **removed**. Domain assignment moves to a **file-
  tree right-click context menu** ("Assign Agent → claude / openai / gemini"),
  matching `pyqt6_ide_implementation.txt`; assignments still go through the
  existing `DomainMap` and surface in the Agent Cluster panel.
- **`app/main.py`** — unchanged except it already calls `apply_theme`.
- **`app/config.py`** — add `update_env(values: dict)` to let the Settings API-key
  form persist keys to `.env`.

## Real vs representative data (per the approved "full shell" choice)

- **Real, wired**: file tree; code view + syntax + unified-diff; `AgentCard`
  states from live `AgentStateChanged` (dormant→IDLE, awake→ACTIVE); ThoughtStream
  from `AgentResult` + `CrossDomainSignal`; `LogTerminal` from orchestrator logs;
  sidecar pill from `SidecarStatus`; domain assignment (context menu → `DomainMap`);
  Recent Activity from an event ring buffer; ClusterView "active agents" stat;
  API-key config (reads masked env, Save writes `.env`); ClusterLoad from
  awake-count sampling.
- **Representative/static** (styled, clearly non-functional): Run button
  (disabled) — Sync re-scans the workspace (real-ish); token/latency stats
  (labeled honestly or representative); the "Prompt all agents" bar shown
  **disabled** with a placeholder; secondary settings categories (Plan & Usage,
  Plugins, Git & PRs, etc.) as styled static panels.

## Responsiveness (PyQt6)

`MainWindow.resizeEvent` applies width breakpoints:
- `< 1120px`: hide the right Agent Cluster panel in WorkspaceView (top-bar toggle
  to reveal).
- `< 860px`: collapse the left NavSidebar/file tree to an icon rail / hide behind
  a hamburger toggle.
- Card grids (stat cards, agent grid) reflow 3→2→1 columns via `flow_layout.py`.
- Settings two-column → stacked.
- `QSplitter` panels get min sizes + `setCollapsible`; the top-bar nav tabs hide
  on narrow widths.

## Verification

1. **Compile/import**: `.venv/bin/python -m compileall app/ui` + offscreen import
   of every new module and `app.main`.
2. **Behavior smoke** (new `scratchpad/ui_smoke2.py`): boot `MainWindow`
   offscreen, switch all three views, inject one representative event of each type,
   assert no exceptions and that agent cards, thought stream, terminal, and recent
   activity populate; confirm the file-tree context menu assigns a domain via
   `DomainMap`.
3. **Visual proof**: `window.grab().save(png)` for each view (Workspace, Cluster,
   Settings) at 1500px, plus Workspace at 800px to prove the responsive collapse;
   Read each PNG and compare against the corresponding mockup, iterating on
   tokens/spacing until it matches the Obsidian Logic look.
4. **No-regression**: the orchestrator pipeline is untouched — re-run the existing
   headless `scratchpad/e2e_test.py` (watcher → router → stub agent → memory) to
   confirm the backend still works end-to-end with the sidecar up.

No changes to `sidecar/`, `app/core/`, `app/agents/`, `app/context/`, `app/memory/`.
