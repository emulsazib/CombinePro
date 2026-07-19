"""Offscreen smoke test for the Obsidian Logic dashboard.

Boots MainWindow offscreen, switches all three views, injects one representative
event of each bus type, asserts the agent cards / thought stream / terminal /
recent activity populate, exercises the file-tree domain assignment, and grabs
proof screenshots (three views at 1500px + workspace at 800px).

Run: .venv/bin/python scratchpad/ui_smoke2.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from PyQt6.QtWidgets import QApplication  # noqa: E402

from app.config import Config  # noqa: E402
from app.core.events import (  # noqa: E402
    AgentResult,
    AgentStateChanged,
    CrossDomainSignal,
    DomainAssigned,
    FileChange,
    FileDelta,
    MemoryWritten,
    SidecarStatus,
    TaskRequest,
)
from app.core.orchestrator import Orchestrator  # noqa: E402
from app.ui.main_window import MainWindow  # noqa: E402
from app.ui.theme import apply_theme  # noqa: E402

SHOTS = REPO / "scratchpad" / "shots"
SHOTS.mkdir(parents=True, exist_ok=True)

SAMPLE_DIFF = """\
--- a/src/main.py
+++ b/src/main.py
@@ -8,6 +8,8 @@ def initialize_system():
     agents = backend_controller.spawn_agents("backend_orchestrator")
-    for agent in agents:
-        agent.listen_to("event_bus")
+    await asyncio.gather(*[agent.listen() for agent in agents])
+    return "System Ready"
"""

NEW_CONTENT = (
    "async def initialize_system():\n"
    "    agents = spawn_agents()\n"
    "    await asyncio.gather(*[a.listen() for a in agents])\n"
    "    return 'System Ready'\n"
)


def main() -> int:
    app = QApplication(sys.argv)
    apply_theme(app)

    config = Config()
    orch = Orchestrator(config, REPO)
    win = MainWindow(config, REPO, orch)
    win.resize(1500, 950)
    win.show()
    app.processEvents()

    first_agent = next(iter(orch.agents))

    # Open a real file so the diff view has a matching current path.
    target = REPO / "app" / "main.py"
    win.workspace_view.editor.open_file(target, rel_label="app/main.py")
    app.processEvents()

    events = [
        FileDelta(path="app/main.py", change_type="modified", diff=SAMPLE_DIFF,
                  old_hash="a", new_hash="b"),
        TaskRequest(agent_name=first_agent, domain="app", description="Refactor init"),
        AgentStateChanged(agent_name=first_agent, state="awake"),
        AgentResult(
            agent_name=first_agent, task_id="t1", ok=True,
            summary="Simplified initialize_system to gather agent listeners concurrently.",
            files_changed=(FileChange(path="app/main.py", change_type="modified", symbols=("initialize_system",)),),
            new_content=NEW_CONTENT,
        ),
        AgentStateChanged(agent_name=first_agent, state="dormant"),
        CrossDomainSignal(target_domain="tests", request="Add a test for the new gather path.",
                          urgency="high", origin_agent=first_agent),
        DomainAssigned(folder="app", agent_name=first_agent),
        MemoryWritten(task_id="t1", detail="delta summary"),
        SidecarStatus(healthy=True, detail="session ok"),
    ]
    for ev in events:
        win._on_event(ev)
    app.processEvents()

    # ---- assertions -------------------------------------------------------
    assert win.workspace_view.thought._layout.count() >= 3, "thought stream empty"
    assert win.cluster_view._activity_layout.count() >= 1, "recent activity empty"
    assert win.cluster_view.agent_cards[first_agent] is not None
    assert win.workspace_view.editor.current_path() in ("app/main.py", None)

    # Domain assignment through the DomainMap (as the tree context menu does).
    orch.domain_map.assign("app/ui", first_agent)
    assert orch.domain_map.assignments().get("app/ui") == first_agent, "domain not assigned"
    win.cluster_view.refresh_domains()

    # Terminal log bridge is live.
    win.workspace_view.terminal.append_line("smoke: terminal ok", None)

    # ---- interactive features --------------------------------------------
    # AI chat / prompt bar (no running loop in the smoke → handled gracefully).
    win.workspace_view.prompt_bar._input.setText("Optimise the initialize_system function")
    win.workspace_view.prompt_bar._submit()
    app.processEvents()
    assert win.workspace_view.thought._layout.count() >= 4, "prompt not added to thought stream"

    # Editable code + save round-trip on a throwaway file.
    scratch = SHOTS.parent / "_edit_probe.py"
    scratch.write_text("x = 1\n")
    win.workspace_view.editor.open_file(scratch, rel_label="scratchpad/_edit_probe.py")
    app.processEvents()
    viewer = win.workspace_view.editor._stack.currentWidget()
    viewer.setPlainText("x = 42  # edited by smoke\n")
    assert viewer.is_dirty, "editor did not flag dirty on edit"
    assert viewer.save(), "editor save failed"
    assert scratch.read_text().startswith("x = 42"), "edit not written to disk"
    assert not viewer.is_dirty, "editor still dirty after save"
    scratch.unlink()

    # Terminal command execution via QProcess.
    win.workspace_view.terminal.set_cwd(REPO)
    win.workspace_view.terminal._input.setText("echo smoke-terminal-ok")
    win.workspace_view.terminal._run()
    for _ in range(20):
        app.processEvents()

    # Run button: run a real Python file, capture output in the terminal.
    prog = SHOTS.parent / "_run_probe.py"
    prog.write_text("print('run-button-works', 6 * 7)\n")
    win.workspace_view.editor.open_file(prog, rel_label="scratchpad/_run_probe.py")
    app.processEvents()
    win._on_run()
    proc = win.workspace_view.terminal._proc
    if proc is not None:
        proc.waitForFinished(5000)
    for _ in range(20):
        app.processEvents()
    term_text = win.workspace_view.terminal._view.toPlainText()
    assert "run-button-works 42" in term_text, f"Run output missing:\n{term_text[-400:]}"
    prog.unlink()

    # ---- screenshots ------------------------------------------------------
    win._switch_view("explorer")
    app.processEvents()
    win.grab().save(str(SHOTS / "workspace_1500.png"))

    win._switch_view("agents")
    app.processEvents()
    win.grab().save(str(SHOTS / "cluster_1500.png"))

    win._switch_view("settings")
    app.processEvents()
    win.grab().save(str(SHOTS / "settings_1500.png"))

    # Responsive collapse proof — resize in steps, as a real drag fires resizeEvent.
    win._switch_view("explorer")
    win.setMinimumSize(0, 0)
    for w in (1100, 1000, 900, 820, 800):
        win.resize(w, 900)
        app.processEvents()
    print("width after resize:", win.width(),
          "nav visible:", win.workspace_view.nav.isVisible(),
          "hamburger visible:", win._hamburger.isVisible(),
          "cluster visible:", win.workspace_view.right_panel.isVisible())
    assert not win.workspace_view.right_panel.isVisible(), "cluster panel should hide when narrow"
    win.grab().save(str(SHOTS / "workspace_800.png"))

    print("SMOKE OK — screenshots in", SHOTS)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
