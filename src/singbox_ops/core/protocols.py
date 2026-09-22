"""Static facts about the protocols the sing-box provider supports.

Kept here (not imported from ``devconfig_gen``) so the ops layer can describe
certificate paths and default ports without reaching into provider internals.
The provider remains the single source of truth for *config shape*.
"""

from __future__ import annotations

from typing import Mapping, Tuple

PROTOCOLS: Tuple[str, ...] = ("anytls", "tuic", "hysteria2")

PROTOCOL_PORTS: Mapping[str, int] = {
    "anytls": 23244,
    "tuic": 9443,
    "hysteria2": 7443,
}

HOST_KEYS: Mapping[str, str] = {
    "anytls": "reality",
    "tuic": "tuic",
    "hysteria2": "hy2",
}

#: Protocols that need an acme-issued certificate on disk.
TLS_PROTOCOLS: Tuple[str, ...] = ("tuic", "hysteria2")

#: (certificate_path, key_path) per TLS protocol.
CERT_PATHS: Mapping[str, Tuple[str, str]] = {
    "tuic": ("/etc/sing-box-tuic/certs/tuic.crt", "/etc/sing-box-tuic/certs/tuic.key"),
    "hysteria2": ("/etc/hysteria/server.crt", "/etc/hysteria/server.key"),
}

DEFAULT_FINGERPRINT = "chrome"
DEFAULT_TUNNEL_MODE = "proxy"
DEFAULT_FORMAT = "json"

# Single source of truth for protocol-level defaults. Anything that wants a
# fallback (context builder, wizard prompts, docs) reads these, so nothing is
# hard-coded in more than one place and operators can reason about one value.
DEFAULT_ANYTLS_DECOY_SERVER = "www.cloudflare.com"
DEFAULT_ANYTLS_DECOY_PORT = 443
DEFAULT_HY2_MASQUERADE = "https://www.cloudflare.com"
DEFAULT_HY2_SERVER_UP_MBPS = 500
DEFAULT_HY2_SERVER_DOWN_MBPS = 500
DEFAULT_HY2_CLIENT_UP_MBPS = 50
DEFAULT_HY2_CLIENT_DOWN_MBPS = 200

#: TCP / UDP classification, used for firewall rules.
UDP_PROTOCOLS: Tuple[str, ...] = ("tuic", "hysteria2")


def build_protocol_hosts(domain_root: str, prefixes: Mapping[str, str]) -> Mapping[str, str]:
    """Return ``{protocol: "<prefix>.<domain_root>"}`` for enabled protocols."""

    root = str(domain_root).strip().lower().rstrip(".")
    hosts = {}
    for protocol, host_key in HOST_KEYS.items():
        prefix = prefixes.get(host_key)
        if prefix:
            hosts[protocol] = f"{prefix}.{root}"
    return hosts


def requires_tls(protocol: str) -> bool:
    return protocol in TLS_PROTOCOLS


def protocol_port(protocol: str) -> int:
    return PROTOCOL_PORTS[protocol]


def cert_paths(protocol: str) -> Tuple[str, str]:
    return CERT_PATHS[protocol]
