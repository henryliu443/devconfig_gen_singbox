"""Plugin contract and shared helpers for sing-box protocol variants.

A variant plugin owns *all* domain detail for one protocol: the exact inbound
and outbound field names, the share-link format, and the variant-specific
validation rules. The rest of the provider (``provider.py`` / ``schema.py`` /
``route.py``) never mentions a variant name, so an upstream sing-box change is
absorbed by editing a single file here plus the registry.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional, Protocol

from ....validation import expect_integer, expect_string
from ..models import BuildContext, ProtocolConfig


class ProtocolPlugin(Protocol):
    """Structural contract every variant plugin implements."""

    protocol_type: str
    host_key: str
    inbound_tag: str
    outbound_tag: str
    default_port: int

    def validate(self, cfg: ProtocolConfig, errors: list) -> None:
        ...

    def build_server_inbound(self, cfg: ProtocolConfig, ctx: BuildContext) -> dict:
        ...

    def build_client_outbound(self, cfg: ProtocolConfig, ctx: BuildContext) -> dict:
        ...

    def build_share_link(self, cfg: ProtocolConfig, ctx: BuildContext) -> str:
        ...


def dig(source: Mapping[str, Any], path: str) -> Any:
    """Read a dotted path from a mapping, returning ``None`` when absent."""

    current: Any = source
    for part in path.split("."):
        if not isinstance(current, Mapping):
            return None
        current = current.get(part)
    return current


def field_path(cfg: ProtocolConfig, relative: str) -> str:
    return f"{cfg.path}.{relative}" if relative else cfg.path


def require_string(
    cfg: ProtocolConfig,
    relative: str,
    errors: list,
    *,
    default: Optional[str] = None,
) -> Optional[str]:
    """Validate a required string field, falling back to ``default``."""

    value = dig(cfg.raw, relative)
    if value is None and default is not None:
        return default
    result = expect_string(value, field_path(cfg, relative), errors)
    return result if result is not None else default


def optional_string(
    cfg: ProtocolConfig,
    relative: str,
    errors: list,
    *,
    default: Optional[str] = None,
) -> Optional[str]:
    """Validate a string field only when it is present."""

    value = dig(cfg.raw, relative)
    if value is None:
        return default
    result = expect_string(value, field_path(cfg, relative), errors)
    return result if result is not None else default


def optional_integer(
    cfg: ProtocolConfig,
    relative: str,
    errors: list,
    *,
    default: Optional[int] = None,
    minimum: Optional[int] = None,
    maximum: Optional[int] = None,
) -> Optional[int]:
    """Validate an integer field only when it is present."""

    value = dig(cfg.raw, relative)
    if value is None:
        return default
    result = expect_integer(
        value,
        field_path(cfg, relative),
        errors,
        minimum=minimum,
        maximum=maximum,
    )
    return result if result is not None else default


DIRECT_DNS_TAG = "dns-direct"


def domain_resolver(server_tag: str = DIRECT_DNS_TAG) -> dict:
    """Domain resolver shared by every client outbound."""

    return {"server": server_tag, "strategy": "prefer_ipv4"}
