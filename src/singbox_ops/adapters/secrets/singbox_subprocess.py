"""Generate credentials using the ``sing-box`` binary, with a Python fallback.

The binary is the canonical source for UUIDs and REALITY keypairs, so we prefer
it. During ``--dry-run`` (or on a machine without sing-box) we transparently
fall back to :mod:`python_secrets` so the rest of the pipeline can still run.
"""

from __future__ import annotations

import re
from typing import Any, Mapping, Optional

from ...core.command import CommandRunner, LocalCommandRunner
from ...core.protocols import HOST_KEYS
from .base import (
    GeneratedSecrets,
    generate_prefixes,
    new_hex,
    new_password,
    new_reality_keypair,
    new_subdomain_prefix,
    new_uuid,
)

_PRIVATE_RE = re.compile(r"PrivateKey:\s*(\S+)")
_PUBLIC_RE = re.compile(r"PublicKey:\s*(\S+)")


class SingboxSubprocessSecrets:
    """Prefer ``sing-box generate``; fall back to pure Python."""

    def __init__(self, runner: Optional[CommandRunner] = None, binary: str = "sing-box"):
        self.runner = runner or LocalCommandRunner()
        self.binary = binary

    # -- subprocess helpers ---------------------------------------------
    def _singbox_uuid(self) -> Optional[str]:
        try:
            result = self.runner.run([self.binary, "generate", "uuid"], check=False)
        except Exception:  # noqa: BLE001 - fallback is intentional
            return None
        if result.returncode != 0:
            return None
        value = (result.stdout or "").strip()
        return value or None

    def _singbox_keypair(self):
        try:
            result = self.runner.run([self.binary, "generate", "reality-keypair"], check=False)
        except Exception:  # noqa: BLE001 - fallback is intentional
            return None
        if result.returncode != 0:
            return None
        text = result.stdout or ""
        private = _PRIVATE_RE.search(text)
        public = _PUBLIC_RE.search(text)
        if not private or not public:
            return None
        return private.group(1), public.group(1)

    # -- adapter contract ------------------------------------------------
    def generate(self, plan, *, dry_run: bool = False) -> GeneratedSecrets:
        if plan.subdomain_prefixes:
            prefixes = dict(plan.subdomain_prefixes)
        else:
            prefixes = generate_prefixes(plan.protocols, HOST_KEYS)

        credentials: dict = {}
        for protocol in plan.protocols:
            if protocol == "anytls":
                credentials["anytls"] = self._anytls()
            elif protocol == "tuic":
                uuid = self._singbox_uuid() or new_uuid()
                credentials["tuic"] = {"uuid": uuid, "password": new_password()}
            elif protocol == "hysteria2":
                credentials["hysteria2"] = {
                    "password": new_password(),
                    "obfs_password": new_password(),
                }
        return GeneratedSecrets(credentials=credentials, subdomain_prefixes=prefixes)

    def _anytls(self) -> Mapping[str, Any]:
        keypair = self._singbox_keypair()
        if keypair is None:
            try:
                private_key, public_key = new_reality_keypair()
            except Exception:  # noqa: BLE001 - last-resort placeholders for dry-run
                private_key = public_key = f"placeholder-{new_subdomain_prefix()}"
        else:
            private_key, public_key = keypair
        return {
            "password": new_password(),
            "private_key": private_key,
            "public_key": public_key,
            "short_id": new_hex(16),
        }
