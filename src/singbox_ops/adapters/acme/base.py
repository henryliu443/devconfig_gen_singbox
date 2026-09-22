"""ACME adapter contract."""

from __future__ import annotations

from typing import Mapping, Protocol, Sequence, Tuple


class ACMEAdapter(Protocol):
    def apply(
        self,
        hosts: Mapping[str, str],
        protocols: Sequence[str],
        *,
        dry_run: bool = False,
    ) -> Mapping[str, Tuple[str, str]]:
        """Ensure certificates exist; return ``{protocol: (cert_path, key_path)}``."""
