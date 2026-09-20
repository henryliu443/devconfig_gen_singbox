"""AnyTLS (REALITY) variant plugin.

All AnyTLS/REALITY field names live here. Upstream sing-box renames are
absorbed by editing this module only.
"""

from __future__ import annotations

from urllib.parse import urlencode

from ..models import BuildContext, ProtocolConfig
from .base import (
    domain_resolver,
    optional_integer,
    optional_string,
    require_string,
)

DEFAULT_PORT = 23244
DEFAULT_DECOY_SERVER = "www.cloudflare.com"
DEFAULT_DECOY_PORT = 443

PADDING_SCHEME = [
    "stop=8",
    "0=30-30",
    "1=100-400",
    "2=400-500,c,500-1000,c,500-1000,c,500-1000,c,500-1000",
    "3=9-9,500-1000",
    "4=500-1000",
    "5=500-1000",
    "6=500-1000",
    "7=500-1000",
]


class AnyTlsPlugin:
    protocol_type = "anytls"
    host_key = "reality"
    inbound_tag = "anytls-in"
    outbound_tag = "anytls-out"
    default_port = DEFAULT_PORT
    sniff_inbound = True

    def validate(self, cfg: ProtocolConfig, errors: list) -> None:
        require_string(cfg, "auth.password", errors)
        require_string(cfg, "reality.private_key", errors)
        require_string(cfg, "reality.public_key", errors)
        require_string(cfg, "reality.short_id", errors)
        optional_string(cfg, "reality.decoy_server", errors, default=DEFAULT_DECOY_SERVER)
        optional_integer(
            cfg, "reality.decoy_port", errors, default=DEFAULT_DECOY_PORT, minimum=1, maximum=65535
        )

    def _port(self, cfg: ProtocolConfig) -> int:
        return cfg.port if cfg.port is not None else DEFAULT_PORT

    def _decoy(self, cfg: ProtocolConfig) -> tuple:
        server = optional_string(cfg, "reality.decoy_server", [], default=DEFAULT_DECOY_SERVER)
        port = optional_integer(
            cfg, "reality.decoy_port", [], default=DEFAULT_DECOY_PORT, minimum=1, maximum=65535
        )
        return server, port

    def build_server_inbound(self, cfg: ProtocolConfig, ctx: BuildContext) -> dict:
        password = require_string(cfg, "auth.password", [], default="")
        private_key = require_string(cfg, "reality.private_key", [], default="")
        short_id = require_string(cfg, "reality.short_id", [], default="")
        decoy_server, decoy_port = self._decoy(cfg)
        return {
            "type": "anytls",
            "tag": self.inbound_tag,
            "listen": "::",
            "listen_port": self._port(cfg),
            "users": [{"name": "user", "password": password}],
            "padding_scheme": list(PADDING_SCHEME),
            "tls": {
                "enabled": True,
                "server_name": decoy_server,
                "reality": {
                    "enabled": True,
                    "handshake": {
                        "server": decoy_server,
                        "server_port": decoy_port,
                    },
                    "private_key": private_key,
                    "short_id": short_id,
                },
            },
        }

    def build_client_outbound(self, cfg: ProtocolConfig, ctx: BuildContext) -> dict:
        password = require_string(cfg, "auth.password", [], default="")
        public_key = require_string(cfg, "reality.public_key", [], default="")
        short_id = require_string(cfg, "reality.short_id", [], default="")
        decoy_server, _ = self._decoy(cfg)
        return {
            "type": "anytls",
            "tag": self.outbound_tag,
            "server": ctx.host(self.host_key),
            "domain_resolver": domain_resolver(),
            "server_port": self._port(cfg),
            "tls": {
                "enabled": True,
                "server_name": decoy_server,
                "utls": {"enabled": True, "fingerprint": ctx.fingerprint},
                "reality": {
                    "enabled": True,
                    "public_key": public_key,
                    "short_id": short_id,
                },
            },
            "password": password,
        }

    def build_share_link(self, cfg: ProtocolConfig, ctx: BuildContext) -> str:
        password = require_string(cfg, "auth.password", [], default="")
        public_key = require_string(cfg, "reality.public_key", [], default="")
        short_id = require_string(cfg, "reality.short_id", [], default="")
        decoy_server, _ = self._decoy(cfg)
        params = urlencode(
            {
                "security": "reality",
                "sni": decoy_server,
                "fp": ctx.fingerprint,
                "pbk": public_key,
                "sid": short_id,
            }
        )
        return f"anytls://{password}@{ctx.host(self.host_key)}:{self._port(cfg)}?{params}#AnyTLS"
