"""Daily sing-box auto-update job (copied verbatim from the legacy deployment).

The script is shipped as a template and installed as-is, then scheduled through
``/etc/cron.d`` so no interactive crontab editing is needed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Mapping, Optional

from ...core.command import CommandRunner, LocalCommandRunner

SCRIPT_PATH = "/usr/local/bin/singbox_auto_update.py"
CRON_PATH = "/etc/cron.d/singbox-auto-update"
LOG_PATH = "/var/log/singbox-auto-update.log"
CRON_SCHEDULE = "17 4 * * *"

_TEMPLATE = Path(__file__).resolve().parents[2] / "templates" / "singbox_auto_update.py.template"


def build_auto_update_script() -> str:
    return _TEMPLATE.read_text(encoding="utf-8")


def build_cron_entry(script_path: str = SCRIPT_PATH, log_path: str = LOG_PATH) -> str:
    return f"{CRON_SCHEDULE} root /usr/bin/env python3 {script_path} >> {log_path} 2>&1\n"


class AutoUpdateRuntime:
    def __init__(
        self,
        runner: Optional[CommandRunner] = None,
        script_path: str = SCRIPT_PATH,
        cron_path: str = CRON_PATH,
    ):
        self.runner = runner or LocalCommandRunner()
        self.script_path = script_path
        self.cron_path = cron_path

    def apply(self, plan, hosts: Mapping[str, str], *, dry_run: bool = False) -> None:
        self.runner.write_text(self.script_path, build_auto_update_script(), mode=0o755)
        self.runner.write_text(self.cron_path, build_cron_entry(self.script_path), mode=0o644)

    def destroy(self, plan, hosts: Mapping[str, str], *, dry_run: bool = False) -> None:
        self.runner.unlink(self.cron_path, missing_ok=True)
        self.runner.unlink(self.script_path, missing_ok=True)
