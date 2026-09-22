"""Optional local JSON state.

State exists so ``redeploy``/``destroy`` can reuse record IDs and credentials
without the operator re-supplying them. It is optional: set
``adapters.state: null`` in the plan for a fully stateless run.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Mapping, Optional

from ...core.command import CommandRunner, LocalCommandRunner
from ...core.exceptions import AdapterError

STATE_VERSION = 1


class LocalJsonState:
    def __init__(self, path: str, runner: Optional[CommandRunner] = None):
        self.path = path
        self.runner = runner or LocalCommandRunner()

    def load(self) -> Optional[Mapping[str, Any]]:
        if not self.runner.exists(self.path):
            return None
        try:
            raw = self.runner.read_text(self.path)
        except OSError as exc:
            raise AdapterError(f"cannot read state {self.path}: {exc}") from exc
        if not raw.strip():
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise AdapterError(f"state file {self.path} is not valid JSON: {exc}") from exc

    def save(self, data: Mapping[str, Any], *, dry_run: bool = False) -> None:
        payload = dict(data)
        payload.setdefault("version", STATE_VERSION)
        payload["deployed_at"] = datetime.now(timezone.utc).isoformat()
        text = json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=False) + "\n"
        self.runner.write_text(self.path, text, mode=0o600)
