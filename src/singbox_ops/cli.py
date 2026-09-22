"""Operations subcommands, registered into the single ``devconfig_gen_singbox`` CLI.

There is exactly **one** command name in this project: the PyPI name
``devconfig_gen_singbox``. ``add_subparsers()`` is what ``devconfig_gen.cli``
calls to graft these subcommands onto that single command, so the ops layer
never introduces a second CLI name.

A-repo style: running ``deploy`` without ``--plan`` starts an interactive
wizard, so one command takes a user from prompts to a deployed server.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Optional

from devconfig_gen import formats

from .core.context_builder import build_context
from .core.exceptions import OpsError
from .core.plan import DeployPlan, load_plan
from .core.orchestrator import DRY_RUN_IP, build_suite, deploy, destroy, make_runner
from .core.protocols import PROTOCOLS

PROG = "devconfig_gen_singbox"
__version__ = "0.1.0"

SUBCOMMANDS = (
    ("context", "Assemble and print the sing-box context (no side effects)"),
    ("plan", "Interactive wizard: write a plan.yaml, do not deploy"),
    ("deploy", "Deploy sing-box (interactive wizard when --plan is omitted)"),
    ("redeploy", "Regenerate credentials and redeploy"),
    ("destroy", "Tear down what a previous deploy created"),
)


def add_subparsers(sub) -> None:
    """Graft the operations subcommands onto the shared root parser."""

    for name, help_text in SUBCOMMANDS:
        command = sub.add_parser(name, help=help_text)
        command.add_argument("--plan", help="Path to a JSON/YAML plan (omit for the wizard)")
        command.add_argument("--domain", help="Domain root (skips that prompt)")
        command.add_argument("--protocols", help="Comma-separated protocols (skips that prompt)")
        if name == "plan":
            command.add_argument("--output", default="plan.yaml", help="Where to write the plan")
        if name == "context":
            command.add_argument("--format", choices=("json", "yaml"), help="Output format")
        if name in ("deploy", "redeploy", "destroy"):
            command.add_argument(
                "--dry-run",
                action="store_true",
                help="Print intended actions without touching the system",
            )
        command.set_defaults(handler=_run)


# --------------------------------------------------------------------------
# interactive wizard (mirrors the legacy A-repo prompt flow)
# --------------------------------------------------------------------------
def _ask(prompt, default=None, reader=None, writer=None):
    reader = reader or sys.stdin
    writer = writer or sys.stdout
    suffix = f" [{default}]" if default else ""
    writer.write(f"? {prompt}{suffix}: ")
    writer.flush()
    line = reader.readline()
    if line == "":
        return default
    line = line.strip()
    return line if line else default


def _ask_yes_no(prompt, default=True, reader=None, writer=None):
    hint = "[Y/n]" if default else "[y/N]"
    value = _ask(f"{prompt} {hint}", None, reader, writer)
    if value is None:
        return default
    return str(value).strip().lower() in ("y", "yes", "true", "1")


def interactive_plan(domain=None, protocols=None, reader=None, writer=None) -> dict:
    writer = writer or sys.stdout
    writer.write("=" * 56 + "\n")
    writer.write(f"  {PROG} 交互式部署向导\n")
    writer.write("=" * 56 + "\n")

    while not domain:
        domain = _ask("主域名 (例: example.com)", None, reader, writer)
        if not domain:
            writer.write("  [!] 域名必填\n")

    protocols = protocols or _ask("启用协议 (逗号分隔)", ",".join(PROTOCOLS), reader, writer)
    mode = _ask("出站模式 none/proxy/tun", "proxy", reader, writer)
    server_ip = _ask("服务器公网 IP (留空=自动探测)", None, reader, writer)
    use_dns = _ask_yes_no("用 Cloudflare 管理 DNS A 记录？", True, reader, writer)
    use_acme = _ask_yes_no("签发 TLS 证书 (acme.sh DNS-01)？", True, reader, writer)
    use_runtime = _ask_yes_no(
        "启用运行时适配器 (packages/systemd/firewall/watchdog)？", True, reader, writer
    )

    server_out = _ask("服务端配置输出路径", "/etc/sing-box/config.json", reader, writer)
    client_out = _ask("客户端配置输出路径", "/root/singbox-client.json", reader, writer)
    links_out = _ask("分享链接输出路径", "/root/singbox-links.txt", reader, writer)

    return {
        "domain_root": domain,
        "protocols": [item.strip() for item in str(protocols).split(",") if item.strip()],
        "tunnel_mode": mode,
        "server_ip": server_ip or "auto",
        "adapters": {
            "secrets": "singbox-subprocess",
            "dns": "cloudflare" if use_dns else None,
            "acme": "cloudflare-dns01" if use_acme else None,
            "state": "local-json" if use_runtime else None,
            "runtime": {
                "packages": "debian" if use_runtime else None,
                "systemd": "systemd" if use_runtime else None,
                "firewall": "nftables-basic" if use_runtime else None,
                "watchdog": "warp" if use_runtime else None,
                "auto_update": "auto-update" if use_runtime else None,
            },
        },
        "outputs": {
            "server_config": server_out,
            "client_config": client_out,
            "links": links_out,
        },
    }


def _detect_or_placeholder(plan) -> str:
    try:
        from .core.network import detect_public_ipv4

        return detect_public_ipv4()
    except OpsError:
        return DRY_RUN_IP


def _run(args) -> int:
    try:
        if getattr(args, "plan", None):
            plan = load_plan(args.plan)
        elif args.command == "destroy":
            raise OpsError("destroy requires --plan")
        else:
            data = interactive_plan(
                domain=getattr(args, "domain", None),
                protocols=getattr(args, "protocols", None),
            )
            if args.command == "plan":
                output = getattr(args, "output", "plan.yaml") or "plan.yaml"
                with open(output, "w", encoding="utf-8") as handle:
                    handle.write(formats.dumps(data, "yaml"))
                print(f"wrote {output}")
                return 0
            plan = DeployPlan.from_mapping(data)

        dry_run = True if args.command == "context" else bool(getattr(args, "dry_run", False))
        runner = make_runner(dry_run)
        suite = build_suite(plan, runner)

        if args.command == "context":
            generated = suite.secrets.generate(plan, dry_run=True)
            server_ip = plan.server_ip or _detect_or_placeholder(plan)
            context = build_context(
                plan,
                generated.credentials,
                server_ip,
                subdomain_prefixes=generated.subdomain_prefixes,
            )
            print(formats.dumps(context, getattr(args, "format", None) or plan.output_format))
            return 0

        if args.command in ("deploy", "redeploy"):
            report = deploy(plan, suite, dry_run=dry_run)
        else:
            report = destroy(plan, suite, dry_run=dry_run)
    except OpsError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except (OSError, formats.FormatError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(json.dumps(report.as_dict(), indent=2, ensure_ascii=False))
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Standalone parser (used by ``python -m singbox_ops.cli``)."""

    parser = argparse.ArgumentParser(prog=PROG, description="sing-box operations.")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    add_subparsers(parser.add_subparsers(dest="command", required=True))
    return parser


def main(argv: Optional[list] = None) -> int:
    args = build_parser().parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
