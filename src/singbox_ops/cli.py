"""Command-line interface for the operations layer.

    singbox-ops context --plan plan.yaml
    singbox-ops deploy  --plan plan.yaml [--dry-run]
    singbox-ops redeploy --plan plan.yaml
    singbox-ops destroy --plan plan.yaml [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Optional

from devconfig_gen import formats

from .core.context_builder import build_context
from .core.exceptions import OpsError
from .core.plan import load_plan
from .core.orchestrator import (
    DRY_RUN_IP,
    build_suite,
    deploy,
    destroy,
    make_runner,
)

__version__ = "0.1.0"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="singbox-ops",
        description="Deploy and manage sing-box using the DevConfig-Gen engine.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    for name, help_text in (
        ("context", "Assemble and print the sing-box context (no side effects)"),
        ("deploy", "Deploy sing-box using the plan"),
        ("redeploy", "Regenerate credentials and redeploy"),
        ("destroy", "Tear down what a previous deploy created"),
    ):
        command = sub.add_parser(name, help=help_text)
        command.add_argument("--plan", required=True, help="Path to a JSON/YAML plan")
        if name != "context":
            command.add_argument(
                "--dry-run",
                action="store_true",
                help="Print intended actions without touching the system",
            )
        if name == "context":
            command.add_argument("--format", choices=("json", "yaml"), help="Output format")
        command.set_defaults(handler=_run)
    return parser


def _detect_or_placeholder(plan) -> str:
    try:
        from .core.network import detect_public_ipv4

        return detect_public_ipv4()
    except OpsError:
        return DRY_RUN_IP


def _run(args) -> int:
    try:
        plan = load_plan(args.plan)
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


def main(argv: Optional[list] = None) -> int:
    args = build_parser().parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
