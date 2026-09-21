"""The sing-box provider: validation, variant dispatch, and assembly.

This module orchestrates plugins, route assembly, and share-link aggregation.
It never mentions a protocol field name; adding or changing a variant is a
plugin-only change.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from ... import formats
from ...models import (
    Diagnostic,
    GeneratedArtifact,
    GenerationRequest,
    GenerationResult,
    ProviderField,
    ProviderStep,
)
from ...validation import ValidationError
from . import links, route, schema
from .models import BuildContext
from .plugins import get_plugin
from .schema import ParsedContext

CLIENT_TUN_INBOUND_TAG = "tun-in"
CLIENT_TUN_ADDRESSES = ["172.19.0.1/30"]
CLIENT_TUN_STACK = "gvisor"
URLTEST_URL = "https://cp.cloudflare.com/generate_204"
CLIENT_PROXY_BEST_TAG = "global"
CLIENT_PROXY_AUTO_TAG = "proxy-auto"
CLIENT_ROUTE_MODE_TAG = "route-mode"
CLIENT_ROUTE_TAG = "route"
DIRECT_DOMAIN_RESOLVER = {"server": "dns-direct", "strategy": "prefer_ipv4"}
TUN_EXCLUDED_ROUTES = [
    # Android VpnService already excludes loopback/link-local; excluding them
    # explicitly makes `configure tun interface: Bad address` (sing-box #2030).
    "10.0.0.0/8",
    # Parallels Desktop Shared Network (host 10.211.55.1, DHCP/DNS/NAT for
    # guest VMs). Listed explicitly so macOS strict_route does not capture
    # VM NAT/DNS traffic into the sing-box TUN.
    "10.211.55.0/24",
    "10.211.55.1/32",
    "100.64.0.0/10",
    "172.16.0.0/12",
    "192.168.0.0/16",
]


class SingBoxProvider:
    """Generate sing-box server/client configs and share links."""

    name = "singbox"

    steps: Sequence[ProviderStep] = (
        ProviderStep(
            id="network",
            title="Network",
            description="Domain, subdomain prefixes, tunnel mode, and protocols.",
            i18n={"zh": {"title": "网络", "description": "域名、子域前缀、隧道模式与协议。"}},
            fields=(
                ProviderField(
                    "network.domain_root",
                    type="string",
                    required=True,
                    title="Domain root",
                    description="Base domain; protocol hosts are <prefix>.<domain_root>.",
                    i18n={"zh": {"title": "根域名", "description": "基础域名；协议主机为 <前缀>.<根域名>。"}},
                ),
                ProviderField(
                    "network.subdomain_prefixes",
                    type="mapping",
                    required=True,
                    title="Subdomain prefixes",
                    description="Explicit prefixes keyed by reality / tuic / hy2.",
                    i18n={"zh": {"title": "子域前缀", "description": "显式前缀，键为 reality / tuic / hy2。"}},
                ),
                ProviderField(
                    "network.tunnel_mode",
                    type="string",
                    required=True,
                    default="proxy",
                    choices=("none", "proxy", "tun"),
                    title="Tunnel mode",
                    description="Server outbound mode.",
                    i18n={"zh": {"title": "隧道模式", "description": "服务端出站模式。"}},
                ),
                ProviderField(
                    "network.protocols",
                    type="document",
                    required=True,
                    title="Protocols",
                    description="One entry per protocol (anytls / tuic / hysteria2).",
                    i18n={"zh": {"title": "协议", "description": "每个协议一个条目（anytls / tuic / hysteria2）。"}},
                ),
            ),
        ),
        ProviderStep(
            id="routing",
            title="Routing",
            description="Embedded or custom rules and DNS servers.",
            i18n={"zh": {"title": "路由", "description": "内嵌或自定义规则与 DNS 服务器。"}},
            fields=(
                ProviderField(
                    "network.routing",
                    type="document",
                    title="Routing",
                    description="rules_source (embedded/custom), geoip_cn, custom_rules.",
                    i18n={"zh": {"title": "路由规则", "description": "rules_source（embedded/custom）、geoip_cn、custom_rules。"}},
                ),
                ProviderField(
                    "network.dns",
                    type="document",
                    title="DNS",
                    description="direct_servers and remote_server.",
                    i18n={"zh": {"title": "DNS", "description": "direct_servers 与 remote_server。"}},
                ),
            ),
        ),
        ProviderStep(
            id="client",
            title="Client",
            description="Client-only options.",
            i18n={"zh": {"title": "客户端", "description": "仅客户端使用的选项。"}},
            fields=(
                ProviderField(
                    "client.server_ip",
                    type="string",
                    title="Server IP",
                    description="Excluded from the TUN route.",
                    i18n={"zh": {"title": "服务器 IP", "description": "从 TUN 路由中排除。"}},
                ),
                ProviderField(
                    "client.fingerprint",
                    type="string",
                    default="chrome",
                    title="uTLS fingerprint",
                    description="uTLS fingerprint for client outbounds.",
                    i18n={"zh": {"title": "uTLS 指纹", "description": "客户端出站的 uTLS 指纹。"}},
                ),
            ),
        ),
        ProviderStep(
            id="output",
            title="Output",
            description="Which artifacts to emit and in which format.",
            i18n={"zh": {"title": "输出", "description": "生成哪些产物以及格式。"}},
            fields=(
                ProviderField(
                    "options.target",
                    type="string",
                    default="both",
                    choices=("server", "client", "both"),
                    title="Target",
                    description="server, client, or both.",
                    i18n={"zh": {"title": "目标", "description": "server、client 或 both。"}},
                ),
                ProviderField(
                    "options.format",
                    type="string",
                    default="json",
                    choices=("json", "yaml"),
                    title="Format",
                    description="Artifact format.",
                    i18n={"zh": {"title": "格式", "description": "产物格式。"}},
                ),
            ),
        ),
    )

    def describe_schema(self) -> Sequence[ProviderStep]:
        return self.steps

    def diagnose(self, request: GenerationRequest) -> Sequence[Diagnostic]:
        _, diagnostics = schema.parse(request.context, request.options)
        return tuple(diagnostics)

    def validate(self, request: GenerationRequest):
        return tuple(item.message for item in self.diagnose(request))

    def generate(self, request: GenerationRequest) -> GenerationResult:
        parsed, diagnostics = schema.parse(request.context, request.options)
        if diagnostics:
            raise ValidationError(diagnostics)

        fmt = str(parsed.options.get("format", "json"))
        target = str(parsed.options.get("target", "both"))
        media_type = formats.media_type_for(fmt)
        ctx = _build_context(parsed)
        enabled = parsed.enabled_protocols()

        artifacts = []
        if target != "client":
            artifacts.append(
                GeneratedArtifact(
                    name=f"sing-box.server.{fmt}",
                    content=_build_server(parsed, ctx),
                    media_type=media_type,
                )
            )
        if target != "server":
            artifacts.append(
                GeneratedArtifact(
                    name=f"sing-box.client.{fmt}",
                    content=_build_client(parsed, ctx),
                    media_type=media_type,
                )
            )
            artifacts.append(
                GeneratedArtifact(
                    name="sing-box-links.txt",
                    content=links.build_links(enabled, ctx),
                    media_type="text/plain",
                )
            )
        return GenerationResult(provider=self.name, artifacts=tuple(artifacts))


def _build_context(parsed: ParsedContext) -> BuildContext:
    return BuildContext(
        network=parsed.network,
        client=parsed.client,
        hosts=parsed.hosts,
        options=parsed.options,
    )


def _server_outbounds(tunnel_mode: str) -> Mapping[str, Any]:
    if tunnel_mode == "proxy":
        return {
            "tag": "warp-out",
            "outbounds": [
                {
                    "type": "socks",
                    "tag": "warp-out",
                    "server": "127.0.0.1",
                    "server_port": 40000,
                    "version": "5",
                },
                {"type": "direct", "tag": "direct"},
            ],
        }
    if tunnel_mode == "tun":
        return {
            "tag": "warp-out",
            "outbounds": [
                {"type": "direct", "tag": "warp-out"},
                {"type": "direct", "tag": "direct"},
            ],
        }
    return {"tag": "direct", "outbounds": [{"type": "direct", "tag": "direct"}]}


def _build_server(parsed: Any, ctx: BuildContext) -> dict:
    network = parsed.network
    inbounds = []
    inbound_tags = []
    sniff_inbounds = []
    for cfg in parsed.enabled_protocols():
        plugin = get_plugin(cfg.type)
        if plugin is None:
            continue
        inbounds.append(plugin.build_server_inbound(cfg, ctx))
        inbound_tags.append(plugin.inbound_tag)
        if getattr(plugin, "sniff_inbound", False):
            sniff_inbounds.append(plugin.inbound_tag)

    outbounds = _server_outbounds(network.tunnel_mode)
    return {
        "log": {"disabled": True},
        "dns": route.build_server_dns(network),
        "inbounds": inbounds,
        "outbounds": outbounds["outbounds"],
        "route": route.build_server_route(
            network, inbound_tags, outbounds["tag"], sniff_inbounds
        ),
    }


def _protocol_domains(parsed: Any, ctx: BuildContext) -> list:
    domains = []
    for cfg in parsed.enabled_protocols():
        plugin = get_plugin(cfg.type)
        if plugin is None:
            continue
        host = ctx.host(plugin.host_key)
        if host:
            domains.append(host)
    return domains


def _client_outbounds(parsed: Any, ctx: BuildContext) -> list:
    outbound_tags = []
    variant_outbounds = []
    for cfg in parsed.enabled_protocols():
        plugin = get_plugin(cfg.type)
        if plugin is None:
            continue
        outbound_tags.append(plugin.outbound_tag)
        variant_outbounds.append(plugin.build_client_outbound(cfg, ctx))

    result = [
        {
            "type": "selector",
            "tag": CLIENT_ROUTE_MODE_TAG,
            "outbounds": [CLIENT_ROUTE_TAG, CLIENT_PROXY_BEST_TAG, "direct"],
            "default": CLIENT_ROUTE_TAG,
            "interrupt_exist_connections": True,
        },
        {
            "type": "selector",
            "tag": CLIENT_PROXY_BEST_TAG,
            "outbounds": [CLIENT_PROXY_AUTO_TAG, *outbound_tags, CLIENT_ROUTE_TAG],
            "default": CLIENT_PROXY_AUTO_TAG,
            "interrupt_exist_connections": True,
        },
        {
            "type": "urltest",
            "tag": CLIENT_PROXY_AUTO_TAG,
            "outbounds": outbound_tags,
            "url": URLTEST_URL,
            "interval": "5m",
            "tolerance": 150,
            "interrupt_exist_connections": True,
        },
    ]
    result.extend(variant_outbounds)
    result.append({"type": "direct", "tag": CLIENT_ROUTE_TAG})
    result.append({"type": "direct", "tag": "direct", "domain_resolver": dict(DIRECT_DOMAIN_RESOLVER)})
    result.append({"type": "block", "tag": "block"})
    return result


def _tun_route_exclude(server_ip: Any) -> list:
    routes = list(TUN_EXCLUDED_ROUTES)
    if not server_ip:
        return routes
    ip = str(server_ip).strip()
    if not ip:
        return routes
    routes.append(f"{ip}/128" if ":" in ip else f"{ip}/32")
    return routes


def _build_client(parsed: Any, ctx: BuildContext) -> dict:
    network = parsed.network
    return {
        "log": {"level": "debug", "timestamp": True},
        "http_clients": [{"tag": "direct-client", "detour": "direct"}],
        "dns": route.build_client_dns(network, _protocol_domains(parsed, ctx)),
        "inbounds": [
            {
                "type": "tun",
                "tag": CLIENT_TUN_INBOUND_TAG,
                # Android expects the tun addresses as an array.
                "address": list(CLIENT_TUN_ADDRESSES),
                "auto_route": True,
                "strict_route": True,
                "route_exclude_address": _tun_route_exclude(parsed.client.server_ip),
                "stack": CLIENT_TUN_STACK,
                "mtu": 1280,
            }
        ],
        "outbounds": _client_outbounds(parsed, ctx),
        "route": route.build_client_route(network, CLIENT_TUN_INBOUND_TAG),
    }
