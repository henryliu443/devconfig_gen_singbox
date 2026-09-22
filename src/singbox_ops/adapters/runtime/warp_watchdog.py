"""Deploy the WARP health watchdog as a ``cron.d`` job."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping, Optional

from ...core.command import CommandRunner, LocalCommandRunner
from ...core.exceptions import AdapterError

SCRIPT_PATH = "/root/warp_lazy_watchdog.sh"
CRON_PATH = "/etc/cron.d/singbox-warp-watchdog"
_TEMPLATE = Path(__file__).resolve().parents[2] / "templates" / "warp_watchdog.sh.template"

_WARP_CHECK_PROXY = """check_warp_data_plane() {
    if ! tcp_connect "$WARP_PROXY_HOST" "$WARP_PROXY_PORT" "$PROXY_CONNECT_TIMEOUT"; then
        return 1
    fi

    timeout "$WARP_CHECK_TIMEOUT" curl -fsS --proxy "$WARP_PROXY" \\
        --connect-timeout "$PROXY_CONNECT_TIMEOUT" \\
        --max-time "$WARP_CHECK_TIMEOUT" \\
        "$WARP_TRACE_URL" 2>/dev/null | grep -Eq 'warp=(on|plus)'
}
"""

_WARP_CHECK_TUN = """check_warp_data_plane() {
    timeout "$WARP_CHECK_TIMEOUT" curl -fsS \\
        --connect-timeout "$PROXY_CONNECT_TIMEOUT" \\
        --max-time "$WARP_CHECK_TIMEOUT" \\
        "$WARP_TRACE_URL" 2>/dev/null | grep -Eq 'warp=(on|plus)'
}
"""


def build_watchdog_script(warp_mode: str) -> str:
    if warp_mode == "proxy":
        check_block = _WARP_CHECK_PROXY
    elif warp_mode == "tun":
        check_block = _WARP_CHECK_TUN
    else:
        raise AdapterError(f"watchdog is only used for proxy/tun, got {warp_mode!r}")
    template = _TEMPLATE.read_text(encoding="utf-8")
    script = template.replace("%%WARP_MODE%%", warp_mode)
    script = script.replace("%%WARP_CHECK_BLOCK%%", check_block)
    return script


def build_cron_entry(script_path: str = SCRIPT_PATH) -> str:
    return f"* * * * * root {script_path}\n"


class WarpWatchdogRuntime:
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
        if plan.tunnel_mode not in ("proxy", "tun"):
            return
        script = build_watchdog_script(plan.tunnel_mode)
        self.runner.write_text(self.script_path, script, mode=0o755)
        self.runner.write_text(self.cron_path, build_cron_entry(self.script_path), mode=0o644)

    def destroy(self, plan, hosts: Mapping[str, str], *, dry_run: bool = False) -> None:
        self.runner.unlink(self.cron_path, missing_ok=True)
        self.runner.unlink(self.script_path, missing_ok=True)
