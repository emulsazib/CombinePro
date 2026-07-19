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

    print("CombinePro bundle self-test")
    failed = 0
    for name, ok, detail in checks:
        failed += not ok
        suffix = f"  ({detail})" if detail else ""
        print(f"  {'PASS' if ok else 'FAIL'}: {name}{suffix}")
    print(f"{len(checks) - failed}/{len(checks)} passed")
    return 1 if failed else 0
