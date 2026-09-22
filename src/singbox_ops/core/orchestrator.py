"""The deploy / destroy orchestrator.

The orchestrator is deliberately thin: it sequences adapters, assembles the
context, calls the pure engine, and records what it did. All side effects live
in the adapters; all config knowledge lives in ``devconfig_gen``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Optional, Sequence, Tuple

from devconfig_gen import formats

from ..adapters.acme.cloudflare_dns01 import CloudflareDNS01ACME
from ..adapters.dns.cloudflare import CloudflareDNS
from ..adapters.export.local_files import LocalFilesExport
from ..adapters.runtime.auto_update import AutoUpdateRuntime
from ..adapters.runtime.nftables import NftablesFirewall
from ..adapters.runtime.packages import DebianPackagesRuntime
from ..adapters.runtime.systemd import SystemdRuntime
from ..adapters.runtime.warp_watchdog import WarpWatchdogRuntime
from ..adapters.secrets.python_secrets import PythonSecrets
from ..adapters.secrets.singbox_subprocess import SingboxSubprocessSecrets
from ..adapters.secrets.static import StaticSecrets
from ..adapters.state.local_json import LocalJsonState
from .command import CommandRunner, LocalCommandRunner, RecordingRunner
from .context_builder import build_context
from .exceptions import PlanError
from .network import detect_public_ipv4
from .plan import DeployPlan
from .protocols import build_protocol_hosts

DRY_RUN_IP = "198.51.100.1"

SECRET_FACTORIES = {
    "singbox-subprocess": SingboxSubprocessSecrets,
    "python-secrets": PythonSecrets,
    "static": StaticSecrets,
}
DNS_FACTORIES = {"cloudflare": CloudflareDNS}
ACME_FACTORIES = {"cloudflare-dns01": CloudflareDNS01ACME}
RUNTIME_FACTORIES = {
    "debian": DebianPackagesRuntime,
    "systemd": SystemdRuntime,
    "nftables-basic": NftablesFirewall,
    "warp": WarpWatchdogRuntime,
    "auto-update": AutoUpdateRuntime,
}
STATE_FACTORIES = {"local-json": LocalJsonState}


@dataclass
class AdapterSuite:
    secrets: Any
    dns: Any
    acme: Optional[Any] = None
    state: Optional[Any] = None
    export: Any = None
    packages: Optional[Any] = None
    systemd: Optional[Any] = None
    firewall: Optional[Any] = None
    watchdog: Optional[Any] = None
    auto_update: Optional[Any] = None


@dataclass
class DeployReport:
    action: str
    domain_root: str
    server_ip: Optional[str]
    hosts: Mapping[str, str] = field(default_factory=dict)
    record_ids: Mapping[str, str] = field(default_factory=dict)
    certificates: Mapping[str, Tuple[str, str]] = field(default_factory=dict)
    outputs: Mapping[str, str] = field(default_factory=dict)
    steps: Sequence[str] = field(default_factory=tuple)
    dry_run: bool = False

    def as_dict(self) -> dict:
        return {
            "action": self.action,
            "domain_root": self.domain_root,
            "server_ip": self.server_ip,
            "hosts": dict(self.hosts),
            "record_ids": dict(self.record_ids),
            "certificates": {key: list(value) for key, value in self.certificates.items()},
            "outputs": dict(self.outputs),
            "steps": list(self.steps),
            "dry_run": self.dry_run,
        }


def build_suite(plan: DeployPlan, runner: CommandRunner) -> AdapterSuite:
    """Construct the adapter suite named by ``plan``."""

    if plan.credentials_input:
        data = formats.load_data(plan.credentials_input)
        secrets = StaticSecrets(data if isinstance(data, Mapping) else {})
    else:
        name = plan.adapter_name("secrets") or "python-secrets"
        if name not in SECRET_FACTORIES:
            raise PlanError(f"unknown secrets adapter: {name!r}")
        if name == "python-secrets":
            secrets = PythonSecrets()
        elif name == "static":
            secrets = StaticSecrets()
        else:
            secrets = SingboxSubprocessSecrets(runner=runner)

    dns_name = plan.adapter_name("dns")
    if not dns_name:
        raise PlanError("a DNS adapter is required; set adapters.dns")
    if dns_name not in DNS_FACTORIES:
        raise PlanError(f"unknown dns adapter: {dns_name!r}")
    dns = DNS_FACTORIES[dns_name](http=None)

    acme_name = plan.adapter_name("acme")
    if acme_name and acme_name not in ACME_FACTORIES:
        raise PlanError(f"unknown acme adapter: {acme_name!r}")
    acme = ACME_FACTORIES[acme_name](runner=runner) if acme_name else None

    state_name = plan.adapter_name("state")
    if state_name and state_name not in STATE_FACTORIES:
        raise PlanError(f"unknown state adapter: {state_name!r}")
    state = STATE_FACTORIES[state_name](plan.state_path, runner=runner) if state_name else None

    runtime_kwargs = {"runner": runner}
    packages = _runtime(plan, "packages", runtime_kwargs)
    systemd = _runtime(plan, "systemd", runtime_kwargs)
    firewall = _runtime(plan, "firewall", runtime_kwargs)
    watchdog = _runtime(plan, "watchdog", runtime_kwargs)
    auto_update = _runtime(plan, "auto_update", runtime_kwargs)

    return AdapterSuite(
        secrets=secrets,
        dns=dns,
        acme=acme,
        state=state,
        export=LocalFilesExport(runner=runner),
        packages=packages,
        systemd=systemd,
        firewall=firewall,
        watchdog=watchdog,
        auto_update=auto_update,
    )


def _runtime(plan: DeployPlan, key: str, kwargs: Mapping[str, Any]):
    name = plan.runtime_adapter_name(key)
    if not name:
        return None
    factory = RUNTIME_FACTORIES.get(name)
    if factory is None:
        raise PlanError(f"unknown runtime adapter for {key}: {name!r}")
    return factory(**kwargs)


def _resolve_server_ip(plan: DeployPlan, dry_run: bool) -> Optional[str]:
    if plan.server_ip:
        return plan.server_ip
    if dry_run:
        return DRY_RUN_IP
    return detect_public_ipv4()


def deploy(
    plan: DeployPlan,
    suite: AdapterSuite,
    *,
    dry_run: bool = False,
    generate: Optional[Callable[..., Any]] = None,
) -> DeployReport:
    """Run the full deployment sequence."""

    generate = generate or _default_generate
    steps = []

    generated = suite.secrets.generate(plan, dry_run=dry_run)
    prefixes = dict(generated.subdomain_prefixes)
    hosts = build_protocol_hosts(plan.domain_root, prefixes)
    steps.append("secrets")

    server_ip = _resolve_server_ip(plan, dry_run)

    record_ids = suite.dns.apply(hosts, server_ip, dry_run=dry_run)
    steps.append("dns")

    certificates: dict = {}
    if suite.acme is not None and plan.tls_protocols():
        certificates = dict(
            suite.acme.apply(hosts, plan.tls_protocols(), dry_run=dry_run)
        )
        steps.append("acme")

    context = build_context(
        plan,
        generated.credentials,
        server_ip,
        subdomain_prefixes=prefixes,
    )
    result = generate(plan, context)
    steps.append("generate")

    written = dict(suite.export.write(result.artifacts, plan.outputs, dry_run=dry_run))
    steps.append("export")

    for key, adapter in (
        ("packages", suite.packages),
        ("systemd", suite.systemd),
        ("firewall", suite.firewall),
        ("watchdog", suite.watchdog),
        ("auto_update", suite.auto_update),
    ):
        if adapter is None:
            continue
        adapter.apply(plan, hosts, dry_run=dry_run)
        steps.append(key)

    if suite.state is not None:
        suite.state.save(
            {
                "domain_root": plan.domain_root,
                "protocols": list(plan.protocols),
                "tunnel_mode": plan.tunnel_mode,
                "server_ip": server_ip,
                "subdomain_prefixes": prefixes,
                "protocol_hosts": dict(hosts),
                "dns_record_ids": dict(record_ids),
                "certificates": {key: list(value) for key, value in certificates.items()},
                "outputs": dict(plan.outputs),
            },
            dry_run=dry_run,
        )
        steps.append("state")

    return DeployReport(
        action="deploy",
        domain_root=plan.domain_root,
        server_ip=server_ip,
        hosts=hosts,
        record_ids=record_ids,
        certificates=certificates,
        outputs=written,
        steps=tuple(steps),
        dry_run=dry_run,
    )


def destroy(
    plan: DeployPlan,
    suite: AdapterSuite,
    *,
    dry_run: bool = False,
) -> DeployReport:
    """Tear down what :func:`deploy` created, in reverse order."""

    steps = []
    state = suite.state.load() if suite.state is not None else None
    state = state or {}
    record_ids = dict(state.get("dns_record_ids") or {})
    prefixes = dict(state.get("subdomain_prefixes") or plan.subdomain_prefixes or {})
    hosts = build_protocol_hosts(plan.domain_root, prefixes) if prefixes else {}

    for key, adapter in (
        ("watchdog", suite.watchdog),
        ("auto_update", suite.auto_update),
        ("firewall", suite.firewall),
        ("systemd", suite.systemd),
        ("packages", suite.packages),
    ):
        if adapter is None:
            continue
        adapter.destroy(plan, hosts, dry_run=dry_run)
        steps.append(key)

    if record_ids:
        suite.dns.destroy(record_ids, dry_run=dry_run)
        steps.append("dns")

    return DeployReport(
        action="destroy",
        domain_root=plan.domain_root,
        server_ip=state.get("server_ip") or plan.server_ip,
        hosts=hosts,
        record_ids=record_ids,
        steps=tuple(steps),
        dry_run=dry_run,
    )


def _default_generate(plan: DeployPlan, context: Mapping[str, Any]):
    from devconfig_gen.engine import generate_pipeline

    return generate_pipeline("singbox", context=dict(context))


def make_runner(dry_run: bool) -> CommandRunner:
    return RecordingRunner() if dry_run else LocalCommandRunner()
