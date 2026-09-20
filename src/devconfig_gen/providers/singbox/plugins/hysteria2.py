"""Hysteria2 variant plugin.

All Hysteria2 field names live here. Upstream sing-box renames are absorbed by
editing this module only.
"""

from __future__ import annotations

from urllib.parse import urlencode

from ..models import BuildContext, ProtocolConfig
from .base import domain_resolver, optional_integer, optional_string, require_string

DEFAULT_PORT = 7443
DEFAULT_MASQUERADE = "https://www.cloudflare.com"
DEFAULT_SERVER_UP_MBPS = 500
DEFAULT_SERVER_DOWN_MBPS = 500
DEFAULT_CLIENT_UP_MBPS = 50
DEFAULT_CLIENT_DOWN_MBPS = 200


class Hysteria2Plugin:
    protocol_type = "hysteria2"
    host_key = "hy2"
    inbound_tag = "hy2-in"
    outbound_tag = "hy2-out"
    default_port = DEFAULT_PORT
    sniff_inbound = False

    def validate(self, cfg: ProtocolConfig, errors: list) -> None:
        require_string(cfg, "auth.password", errors)
        require_string(cfg, "auth.obfs_password", errors)
        require_string(cfg, "tls.cert_path", errors)
        require_string(cfg, "tls.key_path", errors)
        optional_integer(cfg, "bandwidth.up_mbps", errors, minimum=1)
        optional_integer(cfg, "bandwidth.down_mbps", errors, minimum=1)
        optional_string(cfg, "masquerade", errors, default=DEFAULT_MASQUERADE)

    def _port(self, cfg: ProtocolConfig) -> int:
        return cfg.port if cfg.port is not None else DEFAULT_PORT

    def _obfs(self, cfg: ProtocolConfig) -> dict:
        return {
            "type": "salamander",
            "password": require_string(cfg, "auth.obfs_password", [], default=""),
        }

    def build_server_inbound(self, cfg: ProtocolConfig, ctx: BuildContext) -> dict:
        up = optional_integer(cfg, "bandwidth.up_mbps", [], default=DEFAULT_SERVER_UP_MBPS, minimum=1)
        down = optional_integer(
            cfg, "bandwidth.down_mbps", [], default=DEFAULT_SERVER_DOWN_MBPS, minimum=1
        )
        cert_path = require_string(cfg, "tls.cert_path", [], default="")
        key_path = require_string(cfg, "tls.key_path", [], default="")
        masquerade = optional_string(cfg, "masquerade", [], default=DEFAULT_MASQUERADE)
        return {
            "type": "hysteria2",
            "tag": self.inbound_tag,
            "listen": "::",
            "listen_port": self._port(cfg),
            "users": [{"password": require_string(cfg, "auth.password", [], default="")}],
            "ignore_client_bandwidth": False,
            "up_mbps": up,
            "down_mbps": down,
            "obfs": self._obfs(cfg),
            "masquerade": masquerade,
            "tls": {
                "enabled": True,
                "server_name": ctx.host(self.host_key),
                "alpn": ["h3"],
                "certificate_path": cert_path,
                "key_path": key_path,
            },
        }

    def build_client_outbound(self, cfg: ProtocolConfig, ctx: BuildContext) -> dict:
        up = optional_integer(cfg, "bandwidth.up_mbps", [], default=DEFAULT_CLIENT_UP_MBPS, minimum=1)
        down = optional_integer(
            cfg, "bandwidth.down_mbps", [], default=DEFAULT_CLIENT_DOWN_MBPS, minimum=1
        )
        return {
            "type": "hysteria2",
            "tag": self.outbound_tag,
            "server": ctx.host(self.host_key),
            "domain_resolver": domain_resolver(),
            "server_port": self._port(cfg),
            "up_mbps": up,
            "down_mbps": down,
            "obfs": self._obfs(cfg),
            "password": require_string(cfg, "auth.password", [], default=""),
            "tls": {
                "enabled": True,
                "server_name": ctx.host(self.host_key),
                "alpn": ["h3"],
            },
        }

    def build_share_link(self, cfg: ProtocolConfig, ctx: BuildContext) -> str:
        host = ctx.host(self.host_key)
        params = urlencode(
            {
                "obfs": "salamander",
                "obfs-password": require_string(cfg, "auth.obfs_password", [], default=""),
                "sni": host,
            }
        )
        return (
            f"hy2://{require_string(cfg, 'auth.password', [], default='')}"
            f"@{host}:{self._port(cfg)}?{params}#Hysteria2"
        )
