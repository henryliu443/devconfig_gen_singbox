"""Assemble a sing-box provider context from a plan plus generated secrets.

This is the bridge between the ops layer and the pure engine: the engine only
ever sees a plain context mapping, exactly as if a user had written it by hand.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional

from .exceptions import AdapterError
from .plan import DeployPlan
from .protocols import (
    CERT_PATHS,
    HOST_KEYS,
    PROTOCOL_PORTS,
    TLS_PROTOCOLS,
    requires_tls,
)

DEFAULT_ANYTLS_DECOY_SERVER = "www.cloudflare.com"
DEFAULT_ANYTLS_DECOY_PORT = 443
DEFAULT_MASQUERADE = "https://www.cloudflare.com"
DEFAULT_SERVER_UP_MBPS = 500
DEFAULT_SERVER_DOWN_MBPS = 500
DEFAULT_CLIENT_UP_MBPS = 50
DEFAULT_CLIENT_DOWN_MBPS = 200


def _require(secrets: Mapping[str, Any], path: str, context_name: str) -> Any:
    current: Any = secrets
    for part in path.split("."):
        if not isinstance(current, Mapping) or part not in current:
            raise AdapterError(f"missing secret {path!r} for protocol {context_name!r}")
        current = current[part]
    return current


def build_context(
    plan: DeployPlan,
    secrets: Mapping[str, Any],
    server_ip: Optional[str],
    *,
    subdomain_prefixes: Optional[Mapping[str, str]] = None,
    cert_paths: Optional[Mapping[str, str]] = None,
) -> dict:
    """Return a provider context mapping for ``plan``.

    ``secrets`` is keyed by protocol type (``anytls`` / ``tuic`` / ``hysteria2``)
    and holds only explicit credential values.
    """

    prefixes = dict(subdomain_prefixes or plan.subdomain_prefixes or {})
    if not prefixes:
        raise AdapterError(
            "no subdomain prefixes available; provide plan.subdomain_prefixes or a secrets adapter"
        )

    protocols = []
    for protocol in plan.protocols:
        credentials = secrets.get(protocol) or {}
        entry = _build_protocol(protocol, credentials, prefixes, cert_paths)
        protocols.append(entry)

    client = {"fingerprint": plan.fingerprint}
    resolved_ip = server_ip or plan.server_ip
    if resolved_ip:
        client["server_ip"] = resolved_ip

    return {
        "network": {
            "domain_root": plan.domain_root,
            "subdomain_prefixes": prefixes,
            "tunnel_mode": plan.tunnel_mode,
            "protocols": protocols,
            "routing": dict(plan.routing),
            "dns": dict(plan.dns),
        },
        "client": client,
        "options": {"target": plan.target, "format": plan.output_format},
    }


def _resolve_cert(protocol: str, cert_paths: Optional[Mapping[str, str]]) -> tuple:
    """Return ``(cert_path, key_path)`` for a TLS protocol."""

    if cert_paths:
        cert = cert_paths.get("cert") or cert_paths.get(f"{protocol}_cert")
        key = cert_paths.get("key") or cert_paths.get(f"{protocol}_key")
        if cert and key:
            return cert, key
    return CERT_PATHS[protocol]


def _build_protocol(
    protocol: str,
    credentials: Mapping[str, Any],
    prefixes: Mapping[str, str],
    cert_paths: Optional[Mapping[str, str]],
) -> dict:
    host_key = HOST_KEYS[protocol]
    if host_key not in prefixes:
        raise AdapterError(f"subdomain prefix for {host_key!r} is required ({protocol})")

    entry: dict = {
        "type": protocol,
        "enabled": True,
        "port": PROTOCOL_PORTS[protocol],
    }

    if protocol == "anytls":
        entry["auth"] = {"password": _require(credentials, "password", protocol)}
        entry["reality"] = {
            "decoy_server": credentials.get("decoy_server", DEFAULT_ANYTLS_DECOY_SERVER),
            "decoy_port": int(credentials.get("decoy_port", DEFAULT_ANYTLS_DECOY_PORT)),
            "private_key": _require(credentials, "private_key", protocol),
            "public_key": _require(credentials, "public_key", protocol),
            "short_id": _require(credentials, "short_id", protocol),
        }
    elif protocol == "tuic":
        entry["auth"] = {
            "uuid": _require(credentials, "uuid", protocol),
            "password": _require(credentials, "password", protocol),
        }
        cert, key = _resolve_cert(protocol, cert_paths)
        entry["tls"] = {"cert_path": cert, "key_path": key}
    elif protocol == "hysteria2":
        entry["auth"] = {
            "password": _require(credentials, "password", protocol),
            "obfs_password": _require(credentials, "obfs_password", protocol),
        }
        entry["bandwidth"] = {
            "up_mbps": int(credentials.get("up_mbps", DEFAULT_SERVER_UP_MBPS)),
            "down_mbps": int(credentials.get("down_mbps", DEFAULT_SERVER_DOWN_MBPS)),
        }
        entry["masquerade"] = credentials.get("masquerade", DEFAULT_MASQUERADE)
        cert, key = _resolve_cert(protocol, cert_paths)
        entry["tls"] = {"cert_path": cert, "key_path": key}
    else:  # pragma: no cover - guarded by DeployPlan validation
        raise AdapterError(f"unsupported protocol: {protocol}")

    return entry


def needed_certificates(plan: DeployPlan) -> Mapping[str, str]:
    """Return ``{protocol: host_key}`` for protocols that need certificates."""

    return {protocol: HOST_KEYS[protocol] for protocol in plan.protocols if requires_tls(protocol)}


__all__ = [
    "build_context",
    "needed_certificates",
    "TLS_PROTOCOLS",
]
