"""Command-line interface for the generic generation engine."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__, formats
from .engine import describe_provider, diagnose_request, generate_pipeline
from .registry import default_registry


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="devconfig_gen_singbox",
        description="Generate and validate structured JSON/YAML configuration.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    providers = sub.add_parser("providers", help="List available providers")
    providers.set_defaults(handler=_list_providers)

    generate_cmd = sub.add_parser("generate", help="Generate configuration from structured input")
    generate_cmd.add_argument("--provider", default="json", help="Provider name (default: json)")
    generate_cmd.add_argument(
        "--input",
        required=True,
        action="append",
        type=Path,
        help="JSON or YAML input file (repeatable; merged left to right)",
    )
    generate_cmd.add_argument("--output-dir", required=True, type=Path, help="Directory for artifacts")
    generate_cmd.add_argument("--format", choices=("json", "yaml"), help="Output format")
    generate_cmd.add_argument("--name", help="Output file name (default: provider-specific)")
    generate_cmd.add_argument(
        "--set",
        action="append",
        default=[],
        dest="overrides",
        metavar="KEY=VALUE",
        help="Override a value by dotted path, e.g. app.port=9090 (repeatable)",
    )
    generate_cmd.set_defaults(handler=_generate)

    validate_cmd = sub.add_parser("validate", help="Validate input without generating output")
    validate_cmd.add_argument("--provider", default="json", help="Provider name (default: json)")
    validate_cmd.add_argument(
        "--input",
        required=True,
        action="append",
        type=Path,
        help="JSON or YAML input file (repeatable; merged left to right)",
    )
    validate_cmd.add_argument("--format", choices=("json", "yaml"), help="Input format override")
    validate_cmd.add_argument(
        "--set",
        action="append",
        default=[],
        dest="overrides",
        metavar="KEY=VALUE",
        help="Override a value by dotted path before validating (repeatable)",
    )
    validate_cmd.add_argument(
        "--json", action="store_true", help="Print structured diagnostics as JSON"
    )
    validate_cmd.set_defaults(handler=_validate)

    schema_cmd = sub.add_parser(
        "schema", help="Print a provider's declarative field schema as JSON"
    )
    schema_cmd.add_argument("--provider", default="json", help="Provider name (default: json)")
    schema_cmd.set_defaults(handler=_schema)

    init_cmd = sub.add_parser(
        "init",
        help="Run interactive terminal wizard to create configuration",
        description="Run interactive terminal wizard to create configuration.",
    )
    init_cmd.add_argument("--provider", default="custom", help="Provider name (default: custom)")
    init_cmd.add_argument("--input", type=Path, help="Optional existing config file to pre-fill wizard")
    init_cmd.add_argument("--output-dir", default=".", type=Path, help="Directory for generated artifact")
    init_cmd.add_argument("--format", choices=("json", "yaml"), help="Output format override")
    init_cmd.set_defaults(handler=_init)

    ui_cmd = sub.add_parser(
        "ui",
        help="Launch local configuration studio WebUI",
        description="Launch local configuration studio WebUI.",
    )
    ui_cmd.add_argument("--host", default="127.0.0.1", help="Host address (default: 127.0.0.1)")
    ui_cmd.add_argument("--port", default=8848, type=int, help="Port to bind (default: 8848)")
    ui_cmd.add_argument("--no-browser", action="store_true", help="Do not automatically open browser")
    ui_cmd.add_argument(
        "--workspace",
        default=None,
        help="Directory the studio may export into (default: current directory)",
    )
    ui_cmd.set_defaults(handler=_ui)

    _register_ops_subparsers(sub)

    return parser


def _register_ops_subparsers(sub) -> None:
    """Graft the optional ``singbox_ops`` subcommands onto this single CLI.

    ``singbox_ops`` is imported lazily, so importing ``devconfig_gen`` stays
    side-effect free and the pure engine works even without the ops package.
    """

    try:
        from singbox_ops.cli import add_subparsers
    except Exception:  # pragma: no cover - ops layer is optional
        return
    add_subparsers(sub)


def _list_providers(args) -> int:
    for name in default_registry.names():
        print(name)
    return 0


def _parse_overrides(pairs) -> dict:
    overrides = {}
    for item in pairs or ():
        if "=" not in item:
            raise ValueError(f"--set expects KEY=VALUE, got {item!r}")
        key, value = item.split("=", 1)
        key = key.strip()
        if not key:
            raise ValueError(f"--set expects a non-empty key, got {item!r}")
        overrides[key] = formats.coerce_scalar(value)
    return overrides


def _generate(args) -> int:
    options = {"name": args.name} if args.name else None
    try:
        overrides = _parse_overrides(args.overrides)
        result = generate_pipeline(
            args.provider,
            input_path=[str(path) for path in args.input],
            output_dir=str(args.output_dir),
            output_format=args.format,
            options=options,
            overrides=overrides,
        )
    except (OSError, formats.FormatError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    for artifact in result.artifacts:
        print(f"generated {args.output_dir / artifact.name}")
    return 0


def _validate(args) -> int:
    try:
        overrides = _parse_overrides(args.overrides)
        diagnostics = diagnose_request(
            args.provider,
            input_path=[str(path) for path in args.input],
            input_format=args.format,
            overrides=overrides,
        )
    except (OSError, formats.FormatError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps([item.as_dict() for item in diagnostics], indent=2))

    errors = [item for item in diagnostics if item.severity == "error"]
    if errors:
        if not args.json:
            for item in errors:
                print(f"invalid: {item.message}", file=sys.stderr)
        return 1
    if not args.json:
        sources = ", ".join(str(path) for path in args.input)
        print(f"{sources}: valid")
    return 0


def _schema(args) -> int:
    try:
        steps = describe_provider(args.provider)
    except (OSError, formats.FormatError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps([step.as_dict() for step in steps], indent=2))
    return 0


def _init(args) -> int:
    from .interactive import run_interactive_wizard

    input_path = str(args.input) if args.input else None
    return run_interactive_wizard(
        args.provider,
        input_path=input_path,
        output_dir=str(args.output_dir),
        output_format=args.format,
    )


def _ui(args) -> int:
    from .web_ui import run_web_ui

    run_web_ui(
        host=args.host,
        port=args.port,
        open_browser=not args.no_browser,
        workspace_root=args.workspace,
    )
    return 0


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
