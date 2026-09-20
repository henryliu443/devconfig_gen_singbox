"""TUIC variant plugin.

All TUIC field names live here. Upstream sing-box renames are absorbed by
editing this module only.
"""

from __future__ import annotations

from urllib.parse import urlencode

from ..models import BuildContext, ProtocolConfig
from .base import domain_resolver, require_string

DEFAULT_PORT = 9443


class TuicPlugin:
    protocol_type = "tuic"
    host_key = "tuic"
    inbound_tag = "tuic-in"
    outbound_tag = "tuic-out"
    default_port = DEFAULT_PORT
    sniff_inbound = False

    def validate(self, cfg: ProtocolConfig, errors: list) -> None:
        require_string(cfg, "auth.uuid", errors)
        require_string(cfg, "auth.password", errors)
        require_string(cfg, "tls.cert_path", errors)
        require_string(cfg, "tls.key_path", errors)

    def _port(self, cfg: ProtocolConfig) -> int:
        return cfg.port if cfg.port is not None else DEFAULT_PORT

    def build_server_inbound(self, cfg: ProtocolConfig, ctx: BuildContext) -> dict:
        uuid = require_string(cfg, "auth.uuid", [], default="")
        password = require_string(cfg, "auth.password", [], default="")
        cert_path = require_string(cfg, "tls.cert_path", [], default="")
        key_path = require_string(cfg, "tls.key_path", [], default="")
        return {
            "type": "tuic",
            "tag": self.inbound_tag,
            "listen": "::",
            "listen_port": self._port(cfg),
            "users": [{"uuid": uuid, "password": password}],
            "congestion_control": "bbr",
            "zero_rtt_handshake": False,
            "heartbeat": "10s",
            "tls": {
                "enabled": True,
                "server_name": ctx.host(self.host_key),
                "alpn": ["h3"],
                "certificate_path": cert_path,
                "key_path": key_path,
            },
        }

    def build_client_outbound(self, cfg: ProtocolConfig, ctx: BuildContext) -> dict:
        uuid = require_string(cfg, "auth.uuid", [], default="")
        password = require_string(cfg, "auth.password", [], default="")
        return {
            "type": "tuic",
            "tag": self.outbound_tag,
            "server": ctx.host(self.host_key),
            "domain_resolver": domain_resolver(),
            "server_port": self._port(cfg),
            "uuid": uuid,
            "password": password,
            "congestion_control": "bbr",
            "udp_relay_mode": "native",
            "zero_rtt_handshake": False,
            "heartbeat": "10s",
            "tls": {
                "enabled": True,
                "server_name": ctx.host(self.host_key),
                "alpn": ["h3"],
            },
        }

    def build_share_link(self, cfg: ProtocolConfig, ctx: BuildContext) -> str:
        uuid = require_string(cfg, "auth.uuid", [], default="")
        password = require_string(cfg, "auth.password", [], default="")
        host = ctx.host(self.host_key)
        params = urlencode(
            {
                "congestion_control": "bbr",
                "udp_relay_mode": "quic",
                "sni": host,
            }
        )
        return f"tuic://{uuid}:{password}@{host}:{self._port(cfg)}?{params}#TUIC"
