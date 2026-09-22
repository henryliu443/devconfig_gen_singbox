"""Static secrets supplied by the operator (reproducible deploys)."""

from __future__ import annotations

from typing import Any, Mapping, Optional

from ...core.exceptions import AdapterError
from ...core.protocols import HOST_KEYS
from .base import GeneratedSecrets


class StaticSecrets:
    """Wrap an explicit ``{"credentials": ..., "subdomain_prefixes": ...}`` mapping."""

    def __init__(self, data: Optional[Mapping[str, Any]] = None):
        self.data = dict(data or {})

    def generate(self, plan, *, dry_run: bool = False) -> GeneratedSecrets:
        raw = self.data
        if "credentials" in raw or "subdomain_prefixes" in raw:
            credentials = dict(raw.get("credentials") or {})
            prefixes = dict(raw.get("subdomain_prefixes") or {})
        else:
            # Treat the whole mapping as credentials.
            credentials = dict(raw)
            prefixes = {}

        if not prefixes:
            prefixes = dict(plan.subdomain_prefixes)

        missing = []
        for protocol in plan.protocols:
            if protocol not in credentials:
                missing.append(protocol)
        if missing:
            raise AdapterError(
                "static secrets missing credentials for: " + ", ".join(sorted(missing))
            )

        if not prefixes:
            raise AdapterError("static secrets must provide subdomain_prefixes")
        for protocol in plan.protocols:
            host_key = HOST_KEYS[protocol]
            if host_key not in prefixes:
                raise AdapterError(f"static secrets missing subdomain prefix {host_key!r}")

        return GeneratedSecrets(credentials=credentials, subdomain_prefixes=prefixes)
