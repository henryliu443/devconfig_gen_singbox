"""Structural contracts for every adapter."""

from __future__ import annotations

from typing import Any, Mapping, Optional, Protocol, Sequence, Tuple


class SecretsAdapter(Protocol):
    """Produce explicit credentials and subdomain prefixes for a plan."""

    def generate(self, plan, *, dry_run: bool = False) -> Mapping[str, Any]:
        ...


class DNSAdapter(Protocol):
    """Point protocol hostnames at the server's public IP."""

    def apply(
        self, hosts: Mapping[str, str], ip: str, *, dry_run: bool = False
    ) -> Mapping[str, str]:
        ...

    def destroy(self, record_ids: Mapping[str, str], *, dry_run: bool = False) -> None:
        ...


class ACMEAdapter(Protocol):
    """Ensure TLS certificates exist for the hosts that need them."""

    def apply(
        self, hosts: Mapping[str, str], protocols: Sequence[str], *, dry_run: bool = False
    ) -> Mapping[str, Tuple[str, str]]:
        ...


class RuntimeAdapter(Protocol):
    """Install, configure, or remove one piece of the server runtime."""

    def apply(self, plan, hosts: Mapping[str, str], *, dry_run: bool = False) -> None:
        ...

    def destroy(self, plan, hosts: Mapping[str, str], *, dry_run: bool = False) -> None:
        ...


class StateAdapter(Protocol):
    """Optional persistence of deployment metadata."""

    def load(self) -> Optional[Mapping[str, Any]]:
        ...

    def save(self, data: Mapping[str, Any], *, dry_run: bool = False) -> None:
        ...


class ExportAdapter(Protocol):
    """Write generated artifacts to their final destinations."""

    def write(
        self, artifacts: Sequence[Any], outputs: Mapping[str, str], *, dry_run: bool = False
    ) -> Mapping[str, str]:
        ...
