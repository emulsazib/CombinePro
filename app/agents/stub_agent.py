"""Stub agent used when a provider's API key is missing.

Keeps the whole pipeline (router → wake → result → memory write) testable with
zero keys. It never proposes content changes, so it can't cause write loops.
"""
from __future__ import annotations

import json

from app.agents.base import BaseAgent


class StubAgent(BaseAgent):
    provider = "stub"

    def __init__(self, name: str, missing_key: str) -> None:
        super().__init__(name, model="stub")
        self.missing_key = missing_key

    async def _complete(self, system_static: str, system_skeleton: str, user: str) -> str:
        target = ""
        for line in user.splitlines():
            if line.startswith("--- Target file: "):
                target = line.removeprefix("--- Target file: ").rstrip(" -")
                break
        return json.dumps(
            {
                "summary": (
                    f"[stub:{self.name}] Reviewed the task but made no changes — "
                    f"set {self.missing_key} to enable the real connector. "
                    f"Context received: {len(system_skeleton)}B skeleton, {len(user)}B task."
                ),
                "files_changed": [
                    {"path": target, "change_type": "none", "symbols": []}
                ] if target else [],
                "new_content": None,
                "cross_domain_request": None,
            }
        )
