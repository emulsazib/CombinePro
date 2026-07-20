"""Bundle self-test: verifies the packaged app's runtime dependencies resolve.

Runs headlessly and prints PASS/FAIL per check. Invoked by the build scripts
after packaging (`CombinePro --selftest`) so a broken bundle fails the build
instead of failing on a user's machine.
"""
from __future__ import annotations

import sys
from pathlib import Path


def run() -> int:
    checks: list[tuple[str, bool, str]] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        checks.append((name, bool(ok), detail))

    from app.paths import is_frozen, resource_dir, user_data_dir

    # Informational: the same checks are useful from a source checkout too.
    check("running mode", True,
          f"{'frozen bundle' if is_frozen() else 'source checkout'} — resources={resource_dir()}")
    check("user data dir resolvable", bool(user_data_dir()), str(user_data_dir()))

    # Icons
    from app.ui.icons import ICON_DIR, ICON_SIZES

    present = [s for s in ICON_SIZES if (ICON_DIR / f"{s}.png").is_file()]
    check("app icons bundled", len(present) == len(ICON_SIZES), f"{len(present)}/{len(ICON_SIZES)}")

    # Node sidecar payload
    from app.memory.sidecar_process import find_node
    from app.paths import resource_path

    sidecar = resource_path("sidecar")
    check("sidecar server.js bundled", (sidecar / "server.js").is_file())
    check("sidecar node_modules bundled", (sidecar / "node_modules").is_dir())
    node = find_node()
    check("system Node located (optional)", True, node or "not found — Delta Memory disabled")

    # tree-sitter: the AST skeleton engine is useless without working grammars.
    try:
        from tree_sitter_language_pack import get_parser

        parser = get_parser("python")
        tree = parser.parse(b"class A:\n    def b(self):\n        return 1\n")
        ok = tree.root_node.child_count > 0
        check("tree-sitter python grammar", ok, f"root children={tree.root_node.child_count}")
    except Exception as exc:
        check("tree-sitter python grammar", False, f"{type(exc).__name__}: {exc}")

    # The real skeleton path, over a temp source file (bundled .py sources are
    # compiled away, so parse something we write ourselves).
    try:
        import tempfile

        from app.context.ast_skeleton import SkeletonBuilder

        with tempfile.TemporaryDirectory() as tmp:
            sample = Path(tmp) / "sample.py"
            sample.write_text(
                'class Widget:\n'
                '    """A sample class."""\n'
                '    def render(self, x: int) -> str:\n'
                '        """Render it."""\n'
                '        return str(x)\n',
                "utf-8",
            )
            text = SkeletonBuilder().skeleton_for_file(sample)
        ok = "class Widget" in text and "def render" in text
        check("AST skeleton builder runs", ok, f"{len(text)}B extracted")
    except Exception as exc:
        check("AST skeleton builder runs", False, f"{type(exc).__name__}: {exc}")

    # Governance templates must satisfy BOTH knbase gates. A doc that has every
    # required H2 but no plain prose still counts as unauthored, which would
    # leave the session in NEEDS_BOOTSTRAP and re-bootstrap on every start.
    try:
        from app.memory import governance

        bad: list[str] = []
        for key in governance.GOVERNANCE_KEYS:
            doc = governance.render_bootstrap(key, project="selftest")
            missing = governance.validate_sections(key, doc)
            if missing or governance.is_placeholder(doc):
                bad.append(f"{key}(missing={missing}, placeholder={governance.is_placeholder(doc)})")
        check("governance bootstrap templates valid", not bad,
              "; ".join(bad) or f"{len(governance.GOVERNANCE_KEYS)} docs")

        # A spliced memory.md must keep validating, or complete_task starts failing.
        doc = governance.render_bootstrap("memory")
        for i in range(60):
            doc = governance.record_change(doc, f"entry {i}")
        entries = governance.section_entries(doc, "Recent Changes")
        check("memory.md splice keeps doc valid",
              not governance.validate_sections("memory", doc)
              and len(entries) == governance.MAX_SECTION_ENTRIES
              and "entry 59" in entries[0],
              f"{len(entries)} entries retained, newest first")
    except Exception as exc:
        check("governance helpers", False, f"{type(exc).__name__}: {exc}")

    # Provider SDKs must import (they are only constructed when keys exist).
    for mod in ("anthropic", "openai", "google.genai", "httpx", "watchdog", "qasync"):
        try:
            __import__(mod)
            check(f"import {mod}", True)
        except Exception as exc:
            check(f"import {mod}", False, str(exc))

    # Qt widgets used by the UI.
    try:
        from PyQt6.QtWidgets import QApplication  # noqa: F401

        from app.ui.theme import build_stylesheet

        check("Qt + theme", len(build_stylesheet()) > 1000)
    except Exception as exc:
        check("Qt + theme", False, str(exc))

    # Feather icons need QtSvg. Without it every icon silently renders blank, so
    # rasterise one and assert it actually produced pixels.
    try:
        from PyQt6.QtWidgets import QApplication

        from app.ui import feather

        owned = QApplication.instance() is None
        app = QApplication([]) if owned else QApplication.instance()
        blank = [n for n in feather.ICONS if feather.pixmap(n, "#00e38a", 16).isNull()]
        drawn = feather.pixmap("cpu", "#00e38a", 16).toImage()
        opaque = any(
            drawn.pixelColor(x, y).alpha() > 0
            for y in range(drawn.height())
            for x in range(drawn.width())
        )
        check("feather icons render", not blank and opaque,
              f"{len(feather.ICONS)} icons" if not blank else f"blank: {blank[:5]}")
    except Exception as exc:
        check("feather icons render", False, f"{type(exc).__name__}: {exc}")

    print("CombinePro bundle self-test")
    failed = 0
    for name, ok, detail in checks:
        failed += not ok
        suffix = f"  ({detail})" if detail else ""
        print(f"  {'PASS' if ok else 'FAIL'}: {name}{suffix}")
    print(f"{len(checks) - failed}/{len(checks)} passed")
    return 1 if failed else 0
