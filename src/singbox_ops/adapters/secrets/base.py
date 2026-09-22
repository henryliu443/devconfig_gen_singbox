"""Secrets adapter contract and pure-Python primitive generators."""

from __future__ import annotations

import base64
import secrets as _secrets
import string
import uuid
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Protocol, Tuple

from ...core.exceptions import AdapterError

_ALPHABET = string.ascii_letters + string.digits


@dataclass(frozen=True)
class GeneratedSecrets:
    """Credentials keyed by protocol plus per-host subdomain prefixes."""

    credentials: Mapping[str, Any] = field(default_factory=dict)
    subdomain_prefixes: Mapping[str, str] = field(default_factory=dict)


class SecretsAdapter(Protocol):
    def generate(self, plan, *, dry_run: bool = False) -> GeneratedSecrets:
        ...


def new_uuid() -> str:
    return str(uuid.uuid4())


def new_password(length: int = 20) -> str:
    return "".join(_secrets.choice(_ALPHABET) for _ in range(length))


def new_hex(length: int) -> str:
    """Return ``length`` hex characters (length must be even)."""

    return _secrets.token_hex(length // 2)


def new_subdomain_prefix(length: int = 8) -> str:
    return new_hex(length)


def new_reality_keypair() -> Tuple[str, str]:
    """Return a base64url (unpadded) X25519 keypair, matching sing-box output."""

    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
    except Exception as exc:  # noqa: BLE001 - surface an actionable message
        raise AdapterError(
            "generating a REALITY keypair without the sing-box binary requires "
            "the 'cryptography' package (pip install 'devconfig_gen_singbox[ops]')"
        ) from exc

    private_key = X25519PrivateKey.generate()
    private_bytes = private_key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_bytes = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    private = base64.urlsafe_b64encode(private_bytes).decode("ascii").rstrip("=")
    public = base64.urlsafe_b64encode(public_bytes).decode("ascii").rstrip("=")
    return private, public


def generate_prefixes(protocols, host_keys) -> Mapping[str, str]:
    """Return a unique random prefix per enabled protocol host key."""

    seen = set()
    prefixes = {}
    for protocol in protocols:
        host_key = host_keys[protocol]
        while True:
            candidate = new_subdomain_prefix()
            if candidate not in seen:
                seen.add(candidate)
                prefixes[host_key] = candidate
                break
    return prefixes


def generate_credentials(protocols) -> Mapping[str, Any]:
    """Generate the credential block for each enabled protocol."""

    credentials: dict = {}
    for protocol in protocols:
        if protocol == "anytls":
            private_key, public_key = new_reality_keypair()
            credentials["anytls"] = {
                "password": new_password(),
                "private_key": private_key,
                "public_key": public_key,
                "short_id": new_hex(16),
            }
        elif protocol == "tuic":
            credentials["tuic"] = {"uuid": new_uuid(), "password": new_password()}
        elif protocol == "hysteria2":
            credentials["hysteria2"] = {
                "password": new_password(),
                "obfs_password": new_password(),
            }
        else:  # pragma: no cover - guarded by plan validation
            raise AdapterError(f"unsupported protocol: {protocol}")
    return credentials


def optional_str(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
