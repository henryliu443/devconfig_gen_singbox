"""DNS and route assembly for the sing-box provider.

This module is variant-neutral: it receives the inbound tags, the outbound tag,
the protocol host domains, and the routing options, and never mentions a
protocol name. The embedded rule table is loaded from ``data/rules.json`` using
``Path(__file__).parent`` so the provider works from an installed package with
no external files.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

_RULES_PATH = Path(__file__).parent / "data" / "rules.json"

REQUIRED_BUCKETS = (
    "direct_exact",
    "proxy_exact",
    "direct_suffix",
    "proxy_suffix",
    "direct_keyword",
    "proxy_keyword",
    "direct_cidr",
    "proxy_cidr",
)

DNS_DIRECT_SERVER = ["223.5.5.5", "119.29.29.29"]
DNS_REMOTE_SERVER = "1.1.1.1"
DNS_REMOTE_PATH = "/dns-query"
DNS_REMOTE_TLS_SERVER_NAME = "cloudflare-dns.com"

SERVER_DNS_TAG = "dns-server"
CLIENT_DNS_DIRECT_TAG = "dns-direct"
CLIENT_DNS_REMOTE_TAG = "dns-remote"
CLIENT_PROXY_TAG = "global"

GEOIP_CN_RULESET_URL = "https://testingcf.jsdelivr.net/gh/MetaCubeX/meta-rules-dat@sing/geo/geoip/cn.srs"
GEOSITE_CN_RULESET_URL = "https://testingcf.jsdelivr.net/gh/MetaCubeX/meta-rules-dat@sing/geo/geosite/cn.srs"
GEOSITE_GEOLOCATION_NON_CN_RULESET_URL = (
    "https://testingcf.jsdelivr.net/gh/MetaCubeX/meta-rules-dat@sing/geo/geosite/geolocation-!cn.srs"
)

SKIP_PROXY_DOMAINS = ["localhost", "captive.apple.com"]
SKIP_PROXY_SUFFIXES = ["local"]
DNS_DIRECT_ONLY_DOMAINS = ["cp.cloudflare.com", "generate_204"]
DNS_DIRECT_ONLY_SUFFIXES = ["in-addr.arpa", "ip6.arpa"]
APNS_PROXY_SUFFIXES = ["push.apple.com"]
APNS_PROXY_CIDR = [
    "17.0.0.0/8",
    "2403:300:a42::/48",
    "2403:300:a51::/48",
    "2620:149:a44::/48",
    "2a01:b740:a42::/48",
]
APNS_PROXY_PORTS = [443, 5223, 2197]

ROUTE_FINAL = "route-mode"
DIRECT_RULE_OUTBOUND = ROUTE_FINAL


def _merge_unique(*groups: Sequence[Any]) -> list:
    merged: list = []
    for group in groups:
        for item in group:
            if item not in merged:
                merged.append(item)
    return merged


def _load_embedded() -> dict:
    raw = json.loads(_RULES_PATH.read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise ValueError("rules.json must contain a mapping")
    for key in REQUIRED_BUCKETS:
        if key not in raw or not isinstance(raw[key], list):
            raise ValueError(f"rules.json missing required list bucket: {key}")
    return raw


def load_rules(routing: Mapping[str, Any]) -> dict:
    """Return the effective rule buckets for the given ``network.routing``."""

    routing = routing if isinstance(routing, Mapping) else {}
    source = str(routing.get("rules_source") or "embedded").strip().lower()
    custom = routing.get("custom_rules")
    custom = custom if isinstance(custom, Mapping) else {}

    if source == "custom":
        buckets = {key: [] for key in REQUIRED_BUCKETS}
    else:
        embedded = _load_embedded()
        buckets = {key: list(embedded[key]) for key in REQUIRED_BUCKETS}

    for key, value in custom.items():
        if key not in buckets or not isinstance(value, list):
            continue
        buckets[key] = _merge_unique(buckets[key], value)
    return buckets


def _geoip_enabled(routing: Mapping[str, Any]) -> bool:
    if not isinstance(routing, Mapping):
        return True
    return bool(routing.get("geoip_cn", True))


def _dns_direct_servers(dns: Mapping[str, Any]) -> list:
    servers = dns.get("direct_servers") if isinstance(dns, Mapping) else None
    if isinstance(servers, list) and servers:
        return [str(item) for item in servers]
    return list(DNS_DIRECT_SERVER)


def _dns_remote_server(dns: Mapping[str, Any]) -> str:
    server = dns.get("remote_server") if isinstance(dns, Mapping) else None
    if isinstance(server, str) and server.strip():
        return server.strip()
    return DNS_REMOTE_SERVER


def build_server_dns(network: Any) -> dict:
    """Server-side DNS: a single DoH server used for resolution/sniffing."""

    remote = _dns_remote_server(network.dns)
    return {
        "servers": [
            {
                "type": "https",
                "tag": SERVER_DNS_TAG,
                "server": remote,
                "path": DNS_REMOTE_PATH,
                "tls": {
                    "enabled": True,
                    "server_name": DNS_REMOTE_TLS_SERVER_NAME,
                    "alpn": ["h2", "http/1.1"],
                },
            }
        ],
    }


def build_server_route(
    network: Any,
    inbound_tags: Sequence[str],
    outbound_tag: str,
    sniff_inbounds: Sequence[str] = (),
) -> dict:
    """Server route: resolve/sniff selected inbounds, then route them out."""

    rules: list = []
    for tag in sniff_inbounds:
        rules.append(
            {
                "inbound": tag,
                "action": "resolve",
                "server": SERVER_DNS_TAG,
                "strategy": "prefer_ipv4",
            }
        )
        rules.append({"inbound": tag, "action": "sniff", "timeout": "1s"})
    rules.append(
        {
            "inbound": list(inbound_tags),
            "action": "route",
            "outbound": outbound_tag,
        }
    )
    return {
        "rules": rules,
        "final": outbound_tag,
        "default_domain_resolver": SERVER_DNS_TAG,
    }


def build_client_dns(network: Any, protocol_domains: Sequence[str]) -> dict:
    """Client-side split DNS driven by the embedded/custom rule buckets."""

    rules_data = load_rules(network.routing)
    direct_servers = _dns_direct_servers(network.dns)
    remote_server = _dns_remote_server(network.dns)

    dns_rules: list = []
    if protocol_domains:
        dns_rules.append({"domain": list(protocol_domains), "server": CLIENT_DNS_DIRECT_TAG})
    if DNS_DIRECT_ONLY_DOMAINS:
        dns_rules.append({"domain": list(DNS_DIRECT_ONLY_DOMAINS), "server": CLIENT_DNS_DIRECT_TAG})

    direct_exact = _merge_unique(SKIP_PROXY_DOMAINS, rules_data["direct_exact"])
    direct_suffix = _merge_unique(
        SKIP_PROXY_SUFFIXES, DNS_DIRECT_ONLY_SUFFIXES, rules_data["direct_suffix"]
    )
    proxy_suffix = _merge_unique(APNS_PROXY_SUFFIXES, rules_data["proxy_suffix"])

    dns_rules.append({"domain_suffix": list(APNS_PROXY_SUFFIXES), "server": CLIENT_DNS_REMOTE_TAG})
    if direct_exact:
        dns_rules.append({"domain": direct_exact, "server": CLIENT_DNS_DIRECT_TAG})
    if rules_data["proxy_exact"]:
        dns_rules.append({"domain": list(rules_data["proxy_exact"]), "server": CLIENT_DNS_REMOTE_TAG})
    if direct_suffix:
        dns_rules.append({"domain_suffix": direct_suffix, "server": CLIENT_DNS_DIRECT_TAG})
    if proxy_suffix:
        dns_rules.append({"domain_suffix": proxy_suffix, "server": CLIENT_DNS_REMOTE_TAG})
    if rules_data["direct_keyword"]:
        dns_rules.append(
            {"domain_keyword": list(rules_data["direct_keyword"]), "server": CLIENT_DNS_DIRECT_TAG}
        )
    if rules_data["proxy_keyword"]:
        dns_rules.append(
            {"domain_keyword": list(rules_data["proxy_keyword"]), "server": CLIENT_DNS_REMOTE_TAG}
        )

    if _geoip_enabled(network.routing):
        dns_rules.append({"rule_set": "geosite-geolocation-!cn", "server": CLIENT_DNS_REMOTE_TAG})
        dns_rules.append({"rule_set": "geosite-cn", "server": CLIENT_DNS_DIRECT_TAG})

    direct_dns_servers = [
        {
            "type": "udp",
            "tag": CLIENT_DNS_DIRECT_TAG if index == 0 else f"{CLIENT_DNS_DIRECT_TAG}-{index}",
            "server": server_ip,
        }
        for index, server_ip in enumerate(direct_servers)
    ]

    return {
        "servers": [
            *direct_dns_servers,
            {
                "type": "https",
                "tag": CLIENT_DNS_REMOTE_TAG,
                "server": remote_server,
                "path": DNS_REMOTE_PATH,
                "tls": {
                    "enabled": True,
                    "server_name": DNS_REMOTE_TLS_SERVER_NAME,
                    "alpn": ["h2", "http/1.1"],
                },
                "detour": CLIENT_PROXY_TAG,
                "domain_resolver": CLIENT_DNS_DIRECT_TAG,
            },
        ],
        "rules": dns_rules,
        "final": CLIENT_DNS_REMOTE_TAG,
        "strategy": "prefer_ipv4",
    }


def build_client_route(network: Any, sniff_inbound: str = "tun-in") -> dict:
    """Client route rules, APNs exceptions, and the geo rule sets."""

    rules_data = load_rules(network.routing)
    direct_servers = _dns_direct_servers(network.dns)

    rules: list = [
        {"protocol": "dns", "action": "hijack-dns"},
        {"ip_is_private": True, "action": "route", "outbound": "direct"},
        {"ip_cidr": direct_servers, "action": "route", "outbound": "direct"},
    ]

    if sniff_inbound:
        rules.insert(0, {"inbound": sniff_inbound, "action": "sniff", "timeout": "1s"})
        rules.insert(0, {"inbound": sniff_inbound, "action": "resolve", "strategy": "prefer_ipv4"})

    direct_exact = _merge_unique(SKIP_PROXY_DOMAINS, rules_data["direct_exact"])
    direct_suffix = _merge_unique(SKIP_PROXY_SUFFIXES, rules_data["direct_suffix"])
    proxy_suffix = _merge_unique(APNS_PROXY_SUFFIXES, rules_data["proxy_suffix"])

    rules.append({"domain_suffix": list(APNS_PROXY_SUFFIXES), "action": "route", "outbound": CLIENT_PROXY_TAG})
    if direct_exact:
        rules.append({"domain": direct_exact, "action": "route", "outbound": DIRECT_RULE_OUTBOUND})
    if rules_data["proxy_exact"]:
        rules.append(
            {"domain": list(rules_data["proxy_exact"]), "action": "route", "outbound": CLIENT_PROXY_TAG}
        )
    if direct_suffix:
        rules.append(
            {"domain_suffix": direct_suffix, "action": "route", "outbound": DIRECT_RULE_OUTBOUND}
        )

    rules.append(
        {
            "ip_cidr": list(APNS_PROXY_CIDR),
            "port": list(APNS_PROXY_PORTS),
            "action": "route",
            "outbound": CLIENT_PROXY_TAG,
        }
    )

    if proxy_suffix:
        rules.append(
            {"domain_suffix": proxy_suffix, "action": "route", "outbound": CLIENT_PROXY_TAG}
        )
    if rules_data["direct_keyword"]:
        rules.append(
            {
                "domain_keyword": list(rules_data["direct_keyword"]),
                "action": "route",
                "outbound": DIRECT_RULE_OUTBOUND,
            }
        )
    if rules_data["proxy_keyword"]:
        rules.append(
            {
                "domain_keyword": list(rules_data["proxy_keyword"]),
                "action": "route",
                "outbound": CLIENT_PROXY_TAG,
            }
        )
    if rules_data["direct_cidr"]:
        rules.append(
            {
                "ip_cidr": list(rules_data["direct_cidr"]),
                "action": "route",
                "outbound": DIRECT_RULE_OUTBOUND,
            }
        )
    if rules_data["proxy_cidr"]:
        rules.append(
            {
                "ip_cidr": list(rules_data["proxy_cidr"]),
                "action": "route",
                "outbound": CLIENT_PROXY_TAG,
            }
        )

    route = {
        "rules": rules,
        "final": ROUTE_FINAL,
        "auto_detect_interface": True,
        "default_domain_resolver": CLIENT_DNS_DIRECT_TAG,
    }

    if _geoip_enabled(network.routing):
        route["rule_set"] = [
            {
                "type": "remote",
                "tag": "geosite-geolocation-!cn",
                "format": "binary",
                "url": GEOSITE_GEOLOCATION_NON_CN_RULESET_URL,
                "http_client": "direct-client",
            },
            {
                "type": "remote",
                "tag": "geosite-cn",
                "format": "binary",
                "url": GEOSITE_CN_RULESET_URL,
                "http_client": "direct-client",
            },
            {
                "type": "remote",
                "tag": "geoip-cn",
                "format": "binary",
                "url": GEOIP_CN_RULESET_URL,
                "http_client": "direct-client",
            },
        ]
        route["rules"].append(
            {"rule_set": "geosite-geolocation-!cn", "action": "route", "outbound": CLIENT_PROXY_TAG}
        )
        route["rules"].append(
            {"rule_set": "geosite-cn", "action": "route", "outbound": DIRECT_RULE_OUTBOUND}
        )
        route["rules"].append(
            {"rule_set": "geoip-cn", "action": "route", "outbound": DIRECT_RULE_OUTBOUND}
        )

    return route
