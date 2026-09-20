"""Internal data structures for the sing-box provider.

These types are deliberately small and immutable. They carry the *normalized*
input (already validated by :mod:`schema`) so that variant plugins only deal
with their own domain fields and never with raw, untrusted mappings.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Sequence


@dataclass(frozen=True)
class ProtocolConfig:
    """One entry of ``network.protocols`` after normalization.

    ``raw`` is the whole protocol mapping (including ``auth`` / ``tls`` /
    variant sections). ``path`` is the dotted location used for diagnostics,
    for example ``network.protocols.0``.
    """

    type: str
    enabled: bool
    port: Optional[int]
    raw: Mapping[str, Any] = field(default_factory=dict)
    path: str = "network.protocols.0"

    def section(self, name: str) -> Mapping[str, Any]:
        """Return a nested mapping section (``auth`` / ``tls`` / ...)."""

        value = self.raw.get(name)
        return value if isinstance(value, Mapping) else {}


@dataclass(frozen=True)
class NetworkConfig:
    """Normalized ``network`` section."""

    domain_root: str = ""
    subdomain_prefixes: Mapping[str, str] = field(default_factory=dict)
    tunnel_mode: str = "proxy"
    protocols: Sequence[ProtocolConfig] = ()
    routing: Mapping[str, Any] = field(default_factory=dict)
    dns: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ClientConfig:
    """Normalized ``client`` section."""

    server_ip: Optional[str] = None
    fingerprint: str = "chrome"


@dataclass(frozen=True)
class BuildContext:
    """Everything a plugin needs to build its pieces.

    Plugins receive this instead of reaching into the raw context, which keeps
    them free of side effects and of knowledge about the surrounding schema.
    """

    network: NetworkConfig
    client: ClientConfig
    hosts: Mapping[str, str]
    options: Mapping[str, Any] = field(default_factory=dict)

    def host(self, key: str) -> str:
        """Return the FQDN for a plugin's ``host_key``."""

        return self.hosts.get(key, "")

    @property
    def fingerprint(self) -> str:
        return self.client.fingerprint or "chrome"
