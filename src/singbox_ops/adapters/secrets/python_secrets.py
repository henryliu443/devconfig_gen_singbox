"""Pure-Python secret generation (no sing-box binary, no subprocess)."""

from __future__ import annotations

from ...core.protocols import HOST_KEYS
from .base import GeneratedSecrets, generate_credentials, generate_prefixes


class PythonSecrets:
    """Deterministic contract, random values; useful on machines without sing-box."""

    def generate(self, plan, *, dry_run: bool = False) -> GeneratedSecrets:
        if plan.subdomain_prefixes:
            prefixes = dict(plan.subdomain_prefixes)
        else:
            prefixes = generate_prefixes(plan.protocols, HOST_KEYS)
        return GeneratedSecrets(
            credentials=generate_credentials(plan.protocols),
            subdomain_prefixes=prefixes,
        )
