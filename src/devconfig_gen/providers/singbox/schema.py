"""Context schema definition and structural validation for sing-box.

Validation is path-aware and collects *all* problems in one pass as
:class:`~devconfig_gen.models.Diagnostic` values with dotted paths such as
``network.protocols.0.auth.password``. Variant-specific field checks are
delegated to the plugins; this module only owns the neutral structure.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Mapping, Optional, Tuple

from ...models import Diagnostic
from ...validation import expect_enum, expect_integer, expect_mapping, expect_string
from .models import ClientConfig, NetworkConfig, ProtocolConfig
from .plugins import get_plugin, protocol_types
from .route import REQUIRED_BUCKETS

TUNNEL_MODES = ("none", "proxy", "tun")
TARGETS = ("server", "client", "both")
OUTPUT_FORMATS = ("json", "yaml")
RULES_SOURCES = ("embedded", "custom")

DEFAULT_TUNNEL_MODE = "proxy"
DEFAULT_TARGET = "both"
DEFAULT_FORMAT = "json"
DEFAULT_FINGERPRINT = "chrome"


@dataclass(frozen=True)
class ParsedContext:
    """A normalized request context plus the resolved protocol hosts."""

    network: NetworkConfig
    client: ClientConfig
    options: Mapping[str, Any]
    hosts: Mapping[str, str]

    def enabled_protocols(self) -> Tuple[ProtocolConfig, ...]:
        return tuple(cfg for cfg in self.network.protocols if cfg.enabled)


def parse(
    context: Any, options: Optional[Mapping[str, Any]] = None
) -> Tuple[ParsedContext, List[Diagnostic]]:
    """Normalize and validate a request context.

    Always returns a best-effort :class:`ParsedContext`; callers must check the
    returned diagnostics before generating artifacts.
    """

    diagnostics: List[Diagnostic] = []
    if context is None:
        context = {}
    if not isinstance(context, Mapping):
        diagnostics.append(
            Diagnostic("", f"context must be a mapping at the document root, got {_describe(context)}")
        )
        context = {}

    merged_options = _parse_options(context, options, diagnostics)

    if "network" not in context:
        diagnostics.append(Diagnostic("network", "network is required"))
        network_raw: Mapping = {}
    else:
        network_raw = expect_mapping(context["network"], "network", diagnostics) or {}

    network = _parse_network(network_raw, diagnostics)
    client = _parse_client(context.get("client"), diagnostics)
    hosts = _build_hosts(network, diagnostics)

    parsed = ParsedContext(network=network, client=client, options=merged_options, hosts=hosts)
    return parsed, diagnostics


def _parse_options(
    context: Mapping, options: Optional[Mapping[str, Any]], diagnostics: List[Diagnostic]
) -> dict:
    merged: dict = {}
    context_options = context.get("options")
    if context_options is not None:
        if isinstance(context_options, Mapping):
            merged.update(context_options)
        else:
            diagnostics.append(
                Diagnostic(
                    "options",
                    f"options must be a mapping, got {_describe(context_options)}",
                )
            )
    if options:
        merged.update(options)

    target = DEFAULT_TARGET
    if "target" in merged:
        resolved = expect_enum(merged["target"], "options.target", diagnostics, allowed=TARGETS)
        if resolved:
            target = resolved
    fmt = DEFAULT_FORMAT
    if "format" in merged:
        resolved = expect_enum(merged["format"], "options.format", diagnostics, allowed=OUTPUT_FORMATS)
        if resolved:
            fmt = resolved
    merged["target"] = target
    merged["format"] = fmt
    return merged


def _parse_network(raw: Mapping, diagnostics: List[Diagnostic]) -> NetworkConfig:
    domain_root = ""
    if "domain_root" not in raw:
        diagnostics.append(Diagnostic("network.domain_root", "domain_root is required"))
    else:
        domain_root = expect_string(raw.get("domain_root"), "network.domain_root", diagnostics) or ""

    tunnel_mode = DEFAULT_TUNNEL_MODE
    if "tunnel_mode" not in raw:
        diagnostics.append(Diagnostic("network.tunnel_mode", "tunnel_mode is required"))
    else:
        resolved = expect_enum(
            raw.get("tunnel_mode"), "network.tunnel_mode", diagnostics, allowed=TUNNEL_MODES
        )
        if resolved:
            tunnel_mode = resolved

    return NetworkConfig(
        domain_root=domain_root,
        subdomain_prefixes=_parse_prefixes(raw.get("subdomain_prefixes"), diagnostics),
        tunnel_mode=tunnel_mode,
        protocols=_parse_protocols(raw.get("protocols"), diagnostics),
        routing=_parse_routing(raw.get("routing"), diagnostics),
        dns=_parse_dns(raw.get("dns"), diagnostics),
    )


def _parse_prefixes(value: Any, diagnostics: List[Diagnostic]) -> dict:
    if value is None:
        diagnostics.append(Diagnostic("network.subdomain_prefixes", "subdomain_prefixes is required"))
        return {}
    mapping = expect_mapping(value, "network.subdomain_prefixes", diagnostics)
    if mapping is None:
        return {}
    prefixes: dict = {}
    for key, item in mapping.items():
        text = expect_string(item, f"network.subdomain_prefixes.{key}", diagnostics)
        if text is not None:
            prefixes[str(key)] = text
    return prefixes


def _parse_protocols(value: Any, diagnostics: List[Diagnostic]) -> List[ProtocolConfig]:
    if value is None:
        diagnostics.append(Diagnostic("network.protocols", "protocols is required"))
        return []
    if not isinstance(value, list):
        diagnostics.append(
            Diagnostic("network.protocols", f"protocols must be a list, got {_describe(value)}")
        )
        return []
    if not value:
        diagnostics.append(Diagnostic("network.protocols", "protocols must contain at least one entry"))
        return []

    protocols: List[ProtocolConfig] = []
    for index, item in enumerate(value):
        path = f"network.protocols.{index}"
        if not isinstance(item, Mapping):
            diagnostics.append(Diagnostic(path, f"protocol must be a mapping, got {_describe(item)}"))
            continue
        resolved_type = expect_enum(
            item.get("type"), f"{path}.type", diagnostics, allowed=protocol_types()
        )
        enabled = True
        if "enabled" in item:
            raw_enabled = item["enabled"]
            if not isinstance(raw_enabled, bool):
                diagnostics.append(
                    Diagnostic(
                        f"{path}.enabled",
                        f"enabled must be a boolean, got {_describe(raw_enabled)}",
                    )
                )
            else:
                enabled = raw_enabled
        port = None
        if "port" in item:
            port = expect_integer(item["port"], f"{path}.port", diagnostics, minimum=1, maximum=65535)

        protocols.append(
            ProtocolConfig(
                type=resolved_type or str(item.get("type") or "").strip().lower(),
                enabled=enabled,
                port=port,
                raw=dict(item),
                path=path,
            )
        )

    enabled = [cfg for cfg in protocols if cfg.enabled]
    if protocols and not enabled:
        diagnostics.append(Diagnostic("network.protocols", "at least one protocol must be enabled"))
    for cfg in enabled:
        plugin = get_plugin(cfg.type)
        if plugin is not None:
            plugin.validate(cfg, diagnostics)
    return protocols


def _parse_routing(value: Any, diagnostics: List[Diagnostic]) -> dict:
    if value is None:
        return {}
    mapping = expect_mapping(value, "network.routing", diagnostics)
    if mapping is None:
        return {}
    result = dict(mapping)

    if "rules_source" in mapping:
        resolved = expect_enum(
            mapping["rules_source"],
            "network.routing.rules_source",
            diagnostics,
            allowed=RULES_SOURCES,
        )
        if resolved:
            result["rules_source"] = resolved

    if "geoip_cn" in mapping:
        geoip = mapping["geoip_cn"]
        if not isinstance(geoip, bool):
            diagnostics.append(
                Diagnostic(
                    "network.routing.geoip_cn",
                    f"geoip_cn must be a boolean, got {_describe(geoip)}",
                )
            )
        else:
            result["geoip_cn"] = geoip

    if "custom_rules" in mapping:
        custom = mapping["custom_rules"]
        if not isinstance(custom, Mapping):
            diagnostics.append(
                Diagnostic(
                    "network.routing.custom_rules",
                    f"custom_rules must be a mapping, got {_describe(custom)}",
                )
            )
        else:
            result["custom_rules"] = _parse_custom_rules(custom, diagnostics)

    return result


def _parse_custom_rules(custom: Mapping, diagnostics: List[Diagnostic]) -> dict:
    cleaned: dict = {}
    for key, items in custom.items():
        path = f"network.routing.custom_rules.{key}"
        if key not in REQUIRED_BUCKETS:
            diagnostics.append(
                Diagnostic(
                    path,
                    f"unknown rule bucket {key!r}; expected one of {', '.join(REQUIRED_BUCKETS)}",
                )
            )
            continue
        if not isinstance(items, list):
            diagnostics.append(Diagnostic(path, f"custom rule bucket must be a list, got {_describe(items)}"))
            continue
        cleaned[key] = list(items)
    return cleaned


def _parse_dns(value: Any, diagnostics: List[Diagnostic]) -> dict:
    if value is None:
        return {}
    mapping = expect_mapping(value, "network.dns", diagnostics)
    if mapping is None:
        return {}
    result = dict(mapping)

    if "direct_servers" in mapping:
        servers = mapping["direct_servers"]
        if not isinstance(servers, list) or not servers:
            diagnostics.append(
                Diagnostic(
                    "network.dns.direct_servers",
                    f"direct_servers must be a non-empty list, got {_describe(servers)}",
                )
            )
        else:
            cleaned: list = []
            for index, item in enumerate(servers):
                text = expect_string(item, f"network.dns.direct_servers.{index}", diagnostics)
                if text is not None:
                    cleaned.append(text)
            result["direct_servers"] = cleaned

    if "remote_server" in mapping:
        text = expect_string(mapping["remote_server"], "network.dns.remote_server", diagnostics)
        if text is not None:
            result["remote_server"] = text

    return result


def _parse_client(value: Any, diagnostics: List[Diagnostic]) -> ClientConfig:
    if value is None:
        return ClientConfig()
    mapping = expect_mapping(value, "client", diagnostics)
    if mapping is None:
        return ClientConfig()

    server_ip = None
    if "server_ip" in mapping:
        server_ip = expect_string(mapping["server_ip"], "client.server_ip", diagnostics)

    fingerprint = DEFAULT_FINGERPRINT
    if "fingerprint" in mapping:
        resolved = expect_string(mapping["fingerprint"], "client.fingerprint", diagnostics)
        if resolved:
            fingerprint = resolved

    return ClientConfig(server_ip=server_ip, fingerprint=fingerprint)


def _build_hosts(network: NetworkConfig, diagnostics: List[Diagnostic]) -> dict:
    if not network.domain_root:
        return {}
    root = network.domain_root.strip().lower().rstrip(".")
    hosts: dict = {}
    for cfg in network.protocols:
        if not cfg.enabled:
            continue
        plugin = get_plugin(cfg.type)
        if plugin is None:
            continue
        key = plugin.host_key
        if key in hosts:
            continue
        prefix = network.subdomain_prefixes.get(key)
        if not prefix:
            diagnostics.append(
                Diagnostic(
                    f"network.subdomain_prefixes.{key}",
                    f"{key} subdomain prefix is required",
                )
            )
            continue
        hosts[key] = f"{prefix}.{root}"
    return hosts


def _describe(value: Any) -> str:
    if isinstance(value, str):
        return f"string {value!r}"
    if value is None:
        return "null"
    if isinstance(value, bool):
        return f"boolean {value}"
    return f"{type(value).__name__} {value!r}"
