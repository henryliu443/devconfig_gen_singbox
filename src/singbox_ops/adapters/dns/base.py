"""DNS adapter contract."""

from __future__ import annotations

from typing import Mapping, Protocol


class DNSAdapter(Protocol):
    def apply(
        self, hosts: Mapping[str, str], ip: str, *, dry_run: bool = False
    ) -> Mapping[str, str]:
        """Ensure one A record per hostname; return ``{fqdn: record_id}``."""

    def destroy(self, record_ids: Mapping[str, str], *, dry_run: bool = False) -> None:
        """Remove previously created records."""
