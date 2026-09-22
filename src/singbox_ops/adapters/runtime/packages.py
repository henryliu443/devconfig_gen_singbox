"""Install the system packages the deployment needs.

Only actions that are missing are performed, so a healthy server is left alone.
"""

from __future__ import annotations

import shutil
from typing import Callable, Mapping, Optional

from ...core.command import CommandRunner, LocalCommandRunner
from ...core.exceptions import AdapterError

SINGBOX_INSTALL_URL = "https://sing-box.app/install.sh"
WARP_APT_KEYRING = "/usr/share/keyrings/cloudflare-warp-archive-keyring.gpg"
WARP_APT_SOURCE = "/etc/apt/sources.list.d/cloudflare-client.list"

WARP_APT_COMMANDS = (
    "curl -fsSL https://pkg.cloudflareclient.com/pubkey.gpg | "
    f"gpg --yes --dearmor -o {WARP_APT_KEYRING}",
    'echo "deb [signed-by=/usr/share/keyrings/cloudflare-warp-archive-keyring.gpg] '
    'https://pkg.cloudflareclient.com/ $(. /etc/os-release && echo $VERSION_CODENAME) main" '
    f"> {WARP_APT_SOURCE}",
    "apt-get update",
    "apt-get install -y cloudflare-warp",
)


class DebianPackagesRuntime:
    """Best-effort installer for sing-box, openssl and (optionally) WARP."""

    def __init__(
        self,
        runner: Optional[CommandRunner] = None,
        which: Optional[Callable[[str], Optional[str]]] = None,
    ):
        self.runner = runner or LocalCommandRunner()
        self.which = which or shutil.which

    def _has(self, name: str) -> bool:
        try:
            return bool(self.which(name))
        except OSError:
            return False

    def _pkg_install(self, packages) -> None:
        if self._has("apt-get"):
            self.runner.run(["apt-get", "update"], check=True)
            self.runner.run(["apt-get", "install", "-y", *packages], check=True)
            return
        if self._has("dnf"):
            self.runner.run(["dnf", "install", "-y", *packages], check=True)
            return
        if self._has("yum"):
            self.runner.run(["yum", "install", "-y", *packages], check=True)
            return
        raise AdapterError("no supported package manager found (apt-get/dnf/yum)")

    def ensure_openssl(self) -> None:
        if not self._has("openssl"):
            self._pkg_install(["openssl"])

    def ensure_curl(self) -> None:
        if not self._has("curl"):
            self._pkg_install(["curl"])

    def ensure_singbox(self) -> None:
        if self._has("sing-box"):
            return
        self.runner.shell(f"curl -fsSL {SINGBOX_INSTALL_URL} | sh", check=True)

    def ensure_warp(self) -> None:
        if self._has("warp-cli"):
            return
        for command in WARP_APT_COMMANDS:
            self.runner.shell(command, check=True)

    def apply(self, plan, hosts: Mapping[str, str], *, dry_run: bool = False) -> None:
        if dry_run:
            return
        self.ensure_openssl()
        self.ensure_curl()
        self.ensure_singbox()
        if plan.tunnel_mode in ("proxy", "tun"):
            self.ensure_warp()

    def destroy(self, plan, hosts: Mapping[str, str], *, dry_run: bool = False) -> None:
        # Package removal is intentionally left to the operator: yanking sing-box
        # while the service is running is riskier than leaving it installed.
        return None
