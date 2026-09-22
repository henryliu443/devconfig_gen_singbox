"""systemd service management for sing-box."""

from __future__ import annotations

from typing import Mapping, Optional

from ...core.command import CommandRunner, LocalCommandRunner

SINGBOX_SERVICE = "sing-box"
SINGBOX_CONFIG_DIR = "/etc/sing-box"
SINGBOX_UNIT_PATH = f"/etc/systemd/system/{SINGBOX_SERVICE}.service"

SINGBOX_SYSTEMD_UNIT = """[Unit]
Description=sing-box service
Documentation=https://sing-box.sagernet.org/
After=network-online.target nss-lookup.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/bin/sing-box run -C /etc/sing-box
ExecReload=/bin/kill -HUP $MAINPID
Restart=on-failure
RestartSec=5s
LimitNOFILE=1048576

[Install]
WantedBy=multi-user.target
"""


class SystemdRuntime:
    def __init__(
        self,
        runner: Optional[CommandRunner] = None,
        unit_path: str = SINGBOX_UNIT_PATH,
        config_dir: str = SINGBOX_CONFIG_DIR,
        service: str = SINGBOX_SERVICE,
    ):
        self.runner = runner or LocalCommandRunner()
        self.unit_path = unit_path
        self.config_dir = config_dir
        self.service = service

    def apply(self, plan, hosts: Mapping[str, str], *, dry_run: bool = False) -> None:
        self.runner.mkdir(self.config_dir, mode=0o700)
        self.runner.write_text(self.unit_path, SINGBOX_SYSTEMD_UNIT, mode=0o644)
        self.runner.run(["sing-box", "check", "-C", self.config_dir], check=True)
        self.runner.run(["systemctl", "daemon-reload"], check=True)
        self.runner.run(["systemctl", "enable", "--now", self.service], check=True)

    def destroy(self, plan, hosts: Mapping[str, str], *, dry_run: bool = False) -> None:
        self.runner.run(["systemctl", "disable", "--now", self.service], check=False)
        self.runner.unlink(self.unit_path, missing_ok=True)
        self.runner.run(["systemctl", "daemon-reload"], check=False)
