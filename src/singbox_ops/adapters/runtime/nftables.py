"""Minimal nftables hardening.

Default-accept policy (no lockout risk), no IP whitelists, no GeoIP. It opens
the protocol ports, rate-limits SSH and drops a few obvious scan patterns. UDP
rate limiting is deliberately omitted so QUIC-based protocols keep working.
"""

from __future__ import annotations

import re
from typing import Mapping, Optional, Sequence

from ...core.command import CommandRunner, LocalCommandRunner
from ...core.protocols import PROTOCOL_PORTS, UDP_PROTOCOLS

TABLE_NAME = "inet singbox_guard"
NFT_CONF_PATH = "/etc/nftables.d/singbox-guard.conf"
DEFAULT_SSH_PORT = 22
SSHD_CONFIG_PATHS = ("/etc/ssh/sshd_config", "/etc/sshd_config")

_PORT_RE = re.compile(r"^\s*Port\s+(\d+)\s*$")


def _format_port_set(ports: Sequence[int]) -> str:
    return "{ " + ", ".join(str(item) for item in sorted(set(ports))) + " }"


def build_nftables_conf(
    tcp_ports: Sequence[int],
    udp_ports: Sequence[int],
    ssh_port: int = DEFAULT_SSH_PORT,
) -> str:
    lines = [
        "table inet singbox_guard {",
        "  chain input {",
        "    type filter hook input priority 0; policy accept;",
        "    iif lo accept",
        "    ct state established,related accept",
        "    ct state invalid drop",
        "    tcp flags & (fin|syn|rst|psh|ack|urg) == 0 drop",
        "    tcp flags & (fin|psh|urg) == (fin|psh|urg) drop",
        "    tcp flags & (fin|syn) == (fin|syn) drop",
        "    icmp type timestamp-request drop",
        f"    tcp dport {ssh_port} ct state new limit rate 15/minute accept",
    ]
    if tcp_ports:
        lines.append(f"    tcp dport {_format_port_set(tcp_ports)} accept")
    if udp_ports:
        lines.append(f"    udp dport {_format_port_set(udp_ports)} accept")
    lines.extend(["  }", "}", ""])
    return "\n".join(lines)


def detect_ssh_port(
    runner: Optional[CommandRunner] = None,
    paths: Sequence[str] = SSHD_CONFIG_PATHS,
    default: int = DEFAULT_SSH_PORT,
) -> int:
    runner = runner or LocalCommandRunner()
    for path in paths:
        if not runner.exists(path):
            continue
        try:
            text = runner.read_text(path)
        except OSError:
            continue
        for line in text.splitlines():
            match = _PORT_RE.match(line)
            if match:
                return int(match.group(1))
    return default


def protocol_ports(protocols: Sequence[str]) -> Mapping[str, Sequence[int]]:
    tcp = [PROTOCOL_PORTS[name] for name in protocols if name not in UDP_PROTOCOLS]
    udp = [PROTOCOL_PORTS[name] for name in protocols if name in UDP_PROTOCOLS]
    return {"tcp": tcp, "udp": udp}


class NftablesFirewall:
    def __init__(
        self,
        runner: Optional[CommandRunner] = None,
        conf_path: str = NFT_CONF_PATH,
    ):
        self.runner = runner or LocalCommandRunner()
        self.conf_path = conf_path

    def apply(self, plan, hosts: Mapping[str, str], *, dry_run: bool = False) -> None:
        ports = protocol_ports(plan.protocols)
        ssh_port = detect_ssh_port(self.runner)
        conf = build_nftables_conf(ports["tcp"], ports["udp"], ssh_port)
        # Takeover: drop any previous table (legacy included) before applying
        # ours, so chains never stack up and ``destroy`` cannot half-remove a
        # foreign ruleset.
        self.runner.run(["nft", "delete", "table", "inet", "singbox_guard"], check=False)
        self.runner.mkdir("/etc/nftables.d", mode=0o755)
        self.runner.write_text(self.conf_path, conf, mode=0o644)
        self.runner.run(["nft", "-f", self.conf_path], check=True)

    def destroy(self, plan, hosts: Mapping[str, str], *, dry_run: bool = False) -> None:
        self.runner.run(["nft", "delete", "table", "inet", "singbox_guard"], check=False)
        self.runner.unlink(self.conf_path, missing_ok=True)
