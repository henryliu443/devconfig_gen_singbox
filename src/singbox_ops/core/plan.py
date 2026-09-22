"""The declarative deployment plan.

A plan is a plain JSON/YAML mapping. It says *what* to deploy; the orchestrator
and its adapters decide *how*. Unknown keys are preserved so forward-compatible
plans do not silently lose data.
"""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Sequence, Tuple

from devconfig_gen import formats

from .exceptions import PlanError
from .protocols import (
    DEFAULT_FORMAT,
    DEFAULT_FINGERPRINT,
    DEFAULT_TUNNEL_MODE,
    PROTOCOLS,
    TLS_PROTOCOLS,
)

DOMAIN_RE = re.compile(
    r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$"
)
TUNNEL_MODES = ("none", "proxy", "tun")
TARGETS = ("server", "client", "both")
FORMATS = ("json", "yaml")

DEFAULT_ADAPTERS: Mapping[str, Any] = {
    "secrets": "singbox-subprocess",
    "dns": "cloudflare",
    "acme": "cloudflare-dns01",
    "state": "local-json",
    "runtime": {
        "packages": "debian",
        "systemd": "systemd",
        "firewall": "nftables-basic",
        "watchdog": "warp",
        "auto_update": "auto-update",
    },
}

DEFAULT_OUTPUTS: Mapping[str, str] = {
    "server_config": "/etc/sing-box/config.json",
    "client_config": "/root/singbox-client.json",
    "links": "/root/singbox-links.txt",
}

DEFAULT_STATE_PATH = "/etc/sing-box-deploy/state.json"

_AUTO_TOKENS = {"", "auto", "detect"}


def _as_mapping(value: Any, field_name: str) -> Mapping[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise PlanError(f"{field_name} must be a mapping, got {type(value).__name__}")
    return value


def _as_str(value: Any, field_name: str) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise PlanError(f"{field_name} must be a string, got {type(value).__name__}")
    return value.strip()


def _as_str_list(value: Any, field_name: str) -> Tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        items = [part.strip() for part in value.split(",")]
    elif isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        items = [str(item).strip() for item in value]
    else:
        raise PlanError(f"{field_name} must be a list or comma-separated string")
    return tuple(item for item in items if item)


def normalize_domain(raw: str) -> str:
    value = _as_str(raw, "domain_root").lower()
    if "://" in value:
        value = value.split("://", 1)[1]
    value = value.split("/", 1)[0].split(":", 1)[0].strip().strip(".")
    if not value:
        raise PlanError("domain_root is required")
    if not DOMAIN_RE.fullmatch(value):
        raise PlanError(f"domain_root is not a valid domain: {raw!r}")
    return value


@dataclass(frozen=True)
class DeployPlan:
    """A validated, immutable deployment plan."""

    domain_root: str
    protocols: Tuple[str, ...] = PROTOCOLS
    tunnel_mode: str = DEFAULT_TUNNEL_MODE
    server_ip: Optional[str] = None
    subdomain_prefixes: Mapping[str, str] = field(default_factory=dict)
    routing: Mapping[str, Any] = field(default_factory=dict)
    dns: Mapping[str, Any] = field(default_factory=dict)
    fingerprint: str = DEFAULT_FINGERPRINT
    target: str = "both"
    output_format: str = DEFAULT_FORMAT
    adapters: Mapping[str, Any] = field(default_factory=lambda: copy.deepcopy(DEFAULT_ADAPTERS))
    outputs: Mapping[str, str] = field(default_factory=lambda: dict(DEFAULT_OUTPUTS))
    credentials_input: Optional[str] = None
    state_path: str = DEFAULT_STATE_PATH
    raw: Mapping[str, Any] = field(default_factory=dict)

    # -- derived helpers -------------------------------------------------
    def tls_protocols(self) -> Tuple[str, ...]:
        return tuple(item for item in self.protocols if item in TLS_PROTOCOLS)

    def detect_server_ip(self) -> bool:
        return self.server_ip is None

    def adapter_name(self, key: str) -> Optional[str]:
        value = self.adapters.get(key)
        if value is None:
            return None
        if not isinstance(value, str):
            raise PlanError(f"adapters.{key} must be a string or null")
        return value.strip() or None

    def runtime_adapter_name(self, key: str) -> Optional[str]:
        runtime = self.adapters.get("runtime") or {}
        if not isinstance(runtime, Mapping):
            raise PlanError("adapters.runtime must be a mapping")
        value = runtime.get(key)
        if value is None:
            return None
        return str(value).strip() or None

    # -- serialization ---------------------------------------------------
    def to_mapping(self) -> dict:
        data = copy.deepcopy(dict(self.raw)) if self.raw else {}
        data["domain_root"] = self.domain_root
        data["protocols"] = list(self.protocols)
        data["tunnel_mode"] = self.tunnel_mode
        data["server_ip"] = self.server_ip if self.server_ip else "auto"
        if self.subdomain_prefixes:
            data["subdomain_prefixes"] = dict(self.subdomain_prefixes)
        data.setdefault("routing", dict(self.routing))
        data.setdefault("dns", dict(self.dns))
        client = dict(data.get("client") or {})
        client.setdefault("fingerprint", self.fingerprint)
        if self.server_ip:
            client.setdefault("server_ip", self.server_ip)
        data["client"] = client
        options = dict(data.get("options") or {})
        options["target"] = self.target
        options["format"] = self.output_format
        data["options"] = options
        data["adapters"] = copy.deepcopy(dict(self.adapters))
        data["outputs"] = dict(self.outputs)
        if self.credentials_input:
            data["credentials_input"] = self.credentials_input
        return data

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "DeployPlan":
        if not isinstance(data, Mapping):
            raise PlanError(f"plan must be a mapping, got {type(data).__name__}")
        raw = copy.deepcopy(dict(data))

        domain_root = normalize_domain(raw.get("domain_root"))

        protocols = _as_str_list(raw.get("protocols"), "protocols") or PROTOCOLS
        unknown = [item for item in protocols if item not in PROTOCOLS]
        if unknown:
            raise PlanError(
                f"unknown protocol(s): {', '.join(unknown)}; expected one of {', '.join(PROTOCOLS)}"
            )

        tunnel_mode = _as_str(raw.get("tunnel_mode"), "tunnel_mode") or DEFAULT_TUNNEL_MODE
        if tunnel_mode not in TUNNEL_MODES:
            raise PlanError(
                f"tunnel_mode must be one of {', '.join(TUNNEL_MODES)}, got {tunnel_mode!r}"
            )

        server_ip_raw = raw.get("server_ip")
        server_ip: Optional[str] = None
        if isinstance(server_ip_raw, str) and server_ip_raw.strip().lower() not in _AUTO_TOKENS:
            server_ip = server_ip_raw.strip()

        prefixes_raw = _as_mapping(raw.get("subdomain_prefixes"), "subdomain_prefixes")
        prefixes = {str(key): str(value) for key, value in prefixes_raw.items()}

        adapters = copy.deepcopy(dict(DEFAULT_ADAPTERS))
        user_adapters = _as_mapping(raw.get("adapters"), "adapters")
        for key, value in user_adapters.items():
            if key == "runtime" and isinstance(value, Mapping):
                merged = dict(adapters["runtime"])
                merged.update(value)
                adapters["runtime"] = merged
            else:
                adapters[key] = value

        outputs = dict(DEFAULT_OUTPUTS)
        outputs.update({str(k): str(v) for k, v in _as_mapping(raw.get("outputs"), "outputs").items()})

        client = _as_mapping(raw.get("client"), "client")
        options = _as_mapping(raw.get("options"), "options")

        target = _as_str(options.get("target"), "options.target") or "both"
        if target not in TARGETS:
            raise PlanError(f"options.target must be one of {', '.join(TARGETS)}")
        output_format = _as_str(options.get("format"), "options.format") or DEFAULT_FORMAT
        if output_format not in FORMATS:
            raise PlanError(f"options.format must be one of {', '.join(FORMATS)}")

        credentials_input = raw.get("credentials_input")
        if credentials_input is not None:
            credentials_input = str(credentials_input)

        state_path = str(raw.get("state_path") or DEFAULT_STATE_PATH)

        return cls(
            domain_root=domain_root,
            protocols=protocols,
            tunnel_mode=tunnel_mode,
            server_ip=server_ip,
            subdomain_prefixes=prefixes,
            routing=dict(_as_mapping(raw.get("routing"), "routing")),
            dns=dict(_as_mapping(raw.get("dns"), "dns")),
            fingerprint=_as_str(client.get("fingerprint"), "client.fingerprint")
            or DEFAULT_FINGERPRINT,
            target=target,
            output_format=output_format,
            adapters=adapters,
            outputs=outputs,
            credentials_input=credentials_input,
            state_path=state_path,
            raw=raw,
        )


def load_plan(source: Any) -> DeployPlan:
    """Build a :class:`DeployPlan` from a mapping, path, or document text."""

    if isinstance(source, Mapping):
        return DeployPlan.from_mapping(source)
    data = formats.load_data(source)
    if data is None:
        raise PlanError("empty plan")
    return DeployPlan.from_mapping(data)
