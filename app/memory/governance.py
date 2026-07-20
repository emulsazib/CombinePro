"""Governance document helpers for the knbase memory bank.

knbase gates its whole state machine on six governance docs. Two rules from the
package drive everything here (see `dist/core/files.js` in the installed
`@vonneollc/knbase`):

1. `missingSections` requires every listed H2 to be present (case-insensitive).
2. `isPlaceholderContent` treats a doc as *empty* when every line is blank, a
   heading, an HTML comment, or a `>` blockquote — so knbase's own scaffold
   still reads as unauthored. A bootstrap template that emitted only headings
   and hints would pass rule 1, fail rule 2, and re-bootstrap forever.

Every function here is pure: no IO, no async, no Qt.
"""
from __future__ import annotations

import re

# Canonical order, mirroring GOVERNANCE_FILES in the knbase package.
GOVERNANCE_KEYS: tuple[str, ...] = ("prd", "architecture", "design", "phase", "rules", "memory")

# Required H2 headings per document, mirroring TEMPLATES[key].requiredSections.
REQUIRED_SECTIONS: dict[str, tuple[str, ...]] = {
    "prd": ("Problem", "Goals", "Users & Personas", "Functional Requirements",
            "Non-Goals", "Success Metrics"),
    "architecture": ("Overview", "Components", "Data Flow", "Tech Stack",
                     "External Dependencies"),
    "design": ("Modules & Interfaces", "Key Decisions", "Data Models",
               "Conventions", "Open Questions"),
    "phase": ("Current Phase", "Completed", "In Progress", "Next Up", "Backlog"),
    "rules": ("Must Do", "Must Not Do", "Coding Standards", "Guardrails"),
    "memory": ("Summary", "Recent Changes", "Learnings & Gotchas", "Known Issues"),
}

# Only H2 counts, matching extractHeadings() in files.js.
_H2 = re.compile(r"^##\s+(.+?)\s*$")

# Keep memory.md bounded: the sidecar caps request bodies at 2 MB and the doc is
# read back in full on every task.
MAX_SECTION_ENTRIES = 50
MAX_ENTRY_CHARS = 200


def headings(markdown: str) -> list[str]:
    """Every H2 heading in document order."""
    return [m.group(1).strip() for line in markdown.splitlines() if (m := _H2.match(line))]


def validate_sections(key: str, markdown: str) -> list[str]:
    """Required sections missing from `markdown`. Mirrors knbase's missingSections()."""
    present = {h.lower() for h in headings(markdown)}
    return [s for s in REQUIRED_SECTIONS.get(key, ()) if s.lower() not in present]


def is_placeholder(markdown: str) -> bool:
    """True when knbase would treat this doc as unauthored. Mirrors isPlaceholderContent()."""
    for raw in markdown.splitlines():
        line = raw.strip()
        if not line or line.startswith(("#", "<!--", "-->", ">")):
            continue
        return False
    return True


def splice_section(
    markdown: str,
    heading: str,
    new_lines: list[str],
    *,
    prepend: bool = True,
    cap: int = MAX_SECTION_ENTRIES,
) -> str:
    """Insert lines under an H2, bounded at `cap` entries.

    A missing heading is appended as a fresh section rather than raising: we
    never delete or rename a section, so the other required H2s always survive
    and the document keeps validating.
    """
    if not new_lines:
        return markdown

    lines = markdown.splitlines()
    start = next(
        (i for i, line in enumerate(lines)
         if (m := _H2.match(line)) and m.group(1).strip().lower() == heading.strip().lower()),
        None,
    )
    if start is None:
        tail = "" if markdown.endswith("\n") or not markdown else "\n"
        return f"{markdown}{tail}\n## {heading}\n\n" + "\n".join(new_lines) + "\n"

    end = next((i for i in range(start + 1, len(lines)) if _H2.match(lines[i])), len(lines))
    body = [line for line in lines[start + 1:end] if line.strip()]
    merged = (new_lines + body) if prepend else (body + new_lines)
    return "\n".join(lines[:start + 1] + [""] + merged[:cap] + [""] + lines[end:]).rstrip("\n") + "\n"


def section_entries(markdown: str, heading: str) -> list[str]:
    """The non-blank lines under one H2, in document order."""
    lines = markdown.splitlines()
    start = next(
        (i for i, line in enumerate(lines)
         if (m := _H2.match(line)) and m.group(1).strip().lower() == heading.strip().lower()),
        None,
    )
    if start is None:
        return []
    end = next((i for i in range(start + 1, len(lines)) if _H2.match(lines[i])), len(lines))
    return [line for line in lines[start + 1:end] if line.strip()]


def record_change(markdown: str, entry: str) -> str:
    """Prepend one bullet under memory.md's 'Recent Changes'."""
    text = " ".join(entry.split())
    if len(text) > MAX_ENTRY_CHARS:
        text = text[: MAX_ENTRY_CHARS - 1].rstrip() + "…"
    return splice_section(markdown, "Recent Changes", [f"- {text}"])


# ------------------------------------------------------------------ bootstrap

# One plain (non-blockquote, non-heading) line per section, so the rendered doc
# clears isPlaceholderContent as well as missingSections.
_BOOTSTRAP_BODY: dict[str, dict[str, str]] = {
    "prd": {
        "Problem": "Not yet documented. CombinePro agents will populate this during planning.",
        "Goals": "Deliver the work requested through the CombinePro prompt bar.",
        "Users & Personas": "The developer operating this workspace.",
        "Functional Requirements": "Derived per task from user prompts; see phase.md for current scope.",
        "Non-Goals": "Anything outside the workspace root.",
        "Success Metrics": "Requested changes land on disk and tests pass.",
    },
    "architecture": {
        "Overview": "Auto-generated baseline. Refine as the project takes shape.",
        "Components": "See the AST skeleton CombinePro builds per agent domain.",
        "Data Flow": "Not yet documented.",
        "Tech Stack": "{stack}",
        "External Dependencies": "Not yet documented.",
    },
    "design": {
        "Modules & Interfaces": "Not yet documented.",
        "Key Decisions": "Recorded here as agents make them.",
        "Data Models": "Not yet documented.",
        "Conventions": "Match the surrounding code: naming, comment density, and idiom.",
        "Open Questions": "None recorded yet.",
    },
    "phase": {
        "Current Phase": "Bootstrap — governance scaffolded, awaiting the first planning task.",
        "Completed": "Governance documents initialised.",
        "In Progress": "Nothing yet.",
        "Next Up": "Awaiting the first prompt.",
        "Backlog": "Empty.",
    },
    "rules": {
        "Must Do": "Write complete, runnable files. Stay inside your allocated domain.",
        "Must Not Do": "Never modify files outside your domain; raise a cross-domain request instead.",
        "Coding Standards": "Follow the conventions already present in the surrounding code.",
        "Guardrails": "Planning agents author plans only and never write source files.",
    },
    "memory": {
        "Summary": "Delta memory for {project}. Each completed task appends an entry below.",
        "Recent Changes": "- Governance bootstrapped by CombinePro.",
        "Learnings & Gotchas": "None recorded yet.",
        "Known Issues": "None recorded yet.",
    },
}

_TITLES: dict[str, str] = {
    "prd": "Product Requirements",
    "architecture": "Architecture",
    "design": "Design",
    "phase": "Phase",
    "rules": "Rules",
    "memory": "Memory",
}


def render_bootstrap(key: str, project: str = "this workspace", stack: str = "") -> str:
    """A valid starter document for one governance key.

    Deliberately code-generated rather than agent-authored: bootstrap runs at
    startup before any prompt, so it has to work with zero API keys, and
    knbase's section validation is a hard gate that a nondeterministic author
    could fail indefinitely.
    """
    if key not in REQUIRED_SECTIONS:
        raise KeyError(f"unknown governance key {key!r}")

    body = _BOOTSTRAP_BODY[key]
    out = [f"# {_TITLES[key]}", ""]
    for section in REQUIRED_SECTIONS[key]:
        text = body[section].format(project=project, stack=stack or "Not yet detected.")
        out += [f"## {section}", "", text, ""]
    return "\n".join(out)
