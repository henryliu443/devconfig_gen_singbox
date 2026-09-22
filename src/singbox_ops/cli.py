"""Operations subcommands, registered into the single ``devconfig_gen_singbox`` CLI.

There is exactly **one** command name in this project: the PyPI name
``devconfig_gen_singbox``. ``add_subparsers()`` is what ``devconfig_gen.cli``
calls to graft these subcommands onto that single command, so the ops layer
never introduces a second CLI name.

A-repo style: running ``deploy`` without ``--plan`` starts an interactive
wizard (with colour, per-field help, credential capture and live progress).
"""

from __future__ import annotations

import argparse
import getpass
import io
import json
import os
import sys
from typing import Optional

from devconfig_gen import formats

from .core.context_builder import build_context
from .core.exceptions import OpsError
from .core.plan import DeployPlan, load_plan
from .core.orchestrator import DRY_RUN_IP, build_suite, deploy, destroy, make_runner
from .core.protocols import PROTOCOLS
from .core.ui import UI

PROG = "devconfig_gen_singbox"
__version__ = "0.1.0"

DEFAULT_SERVER_OUT = "/etc/sing-box/config.json"
DEFAULT_CLIENT_OUT = "/root/singbox-client.json"
DEFAULT_LINKS_OUT = "/root/singbox-links.txt"

STEP_LABELS = {
    "secrets": "生成凭据 / 子域前缀",
    "dns": "同步 Cloudflare DNS A 记录",
    "acme": "签发 TLS 证书 (acme.sh DNS-01)",
    "generate": "用引擎生成 server / client / links",
    "export": "写出配置产物",
    "packages": "安装依赖 (sing-box / WARP)",
    "systemd": "写入 systemd 单元并重启服务",
    "firewall": "应用 nftables 防火墙",
    "watchdog": "部署 / 取消 WARP watchdog",
    "auto_update": "安装每日自动升级任务",
    "state": "保存部署状态",
}

SUBCOMMANDS = (
    ("context", "Assemble and print the sing-box context (no side effects)"),
    ("plan", "Interactive wizard: write a plan.yaml, do not deploy"),
    ("deploy", "Deploy sing-box (interactive wizard when --plan is omitted)"),
    ("redeploy", "Regenerate credentials and redeploy"),
    ("destroy", "Tear down what a previous deploy created"),
    ("certs", "Prune stale acme.sh certificate dirs (dry-run unless --apply)"),
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
        if name == "certs":
            command.add_argument("--keep", required=True, help="Comma-separated hosts to keep")
            command.add_argument("--acme-home", default="/root/.acme.sh", help="acme.sh home dir")
            command.add_argument("--apply", action="store_true", help="Actually delete (default: dry run)")
        if name == "context":
            command.add_argument("--format", choices=("json", "yaml"), help="Output format")
        if name in ("deploy", "redeploy", "destroy"):
            command.add_argument("--dry-run", action="store_true",
                                 help="Print intended actions without touching the system")
            command.add_argument("--yes", action="store_true",
                                 help="Skip the interactive confirmation before a real run")
            command.add_argument("--json", action="store_true",
                                 help="Emit the machine-readable report as JSON (implies --yes for real runs)")
        command.set_defaults(handler=_run)


# --------------------------------------------------------------------------
# interactive wizard
# --------------------------------------------------------------------------
def _ask(ui: UI, prompt, desc=None, required=False, default=None, reader=None, writer=None):
    reader = reader or sys.stdin
    writer = writer or sys.stdout
    ui.field(prompt, desc, required=required)
    suffix = f" [{default}]" if default else ""
    writer.write(f"    ? {prompt}{suffix}: ")
    writer.flush()
    line = reader.readline()
    if line == "":
        return default
    line = line.strip()
    return line if line else default


def _ask_yes_no(ui: UI, prompt, desc=None, default=True, reader=None, writer=None):
    hint = "[Y/n]" if default else "[y/N]"
    ui.field(prompt + f" {hint}", desc)
    writer = writer or sys.stdout
    reader = reader or sys.stdin
    writer.write("    ? ")
    writer.flush()
    line = reader.readline()
    if line == "":
        return default
    line = line.strip().lower()
    if not line:
        return default
    return line in ("y", "yes", "true", "1")


def _ask_secret(ui: UI, prompt, desc=None, reader=None, writer=None) -> str:
    ui.field(prompt, desc)
    reader = reader or sys.stdin
    writer = writer or sys.stdout
    if reader is not sys.stdin or not sys.stdin.isatty():
        # Piped input / tests: read a plain line so nothing echoes weirdly.
        line = reader.readline()
        return line.strip() if line else ""
    writer.write("    ? ")
    writer.flush()
    try:
        return getpass.getpass("")
    except Exception:
        line = sys.stdin.readline()
        return line.strip() if line else ""


def interactive_plan(domain=None, protocols=None, reader=None, writer=None, ui=None):
    """Prompt for a full deployment spec.

    Returns ``(plan_mapping, env)`` where ``env`` carries any credentials to be
    placed into the process environment (never written to disk).
    """

    ui = ui or UI(writer)
    ui.banner(f"{PROG} · 交互式部署向导", "逐项回答；回车使用默认值。Ctrl-C 可随时退出。")

    ui.section("1/4 基础")
    while not domain:
        domain = _ask(ui, "主域名", "例如 example.com；协议主机名 = <前缀>.<主域名>",
                      required=True, reader=reader, writer=writer)
        if not domain:
            ui.error("域名必填")
    protocols = protocols or _ask(
        ui, "启用协议", "可选 anytls / tuic / hysteria2，逗号分隔",
        default=",".join(PROTOCOLS), reader=reader, writer=writer,
    )
    tunnel_mode = _ask(
        ui, "出站模式", "none=全部直连；proxy=走本机 WARP socks(127.0.0.1:40000)；tun=WARP 系统隧道",
        default="proxy", reader=reader, writer=writer,
    )
    server_ip = _ask(ui, "服务器公网 IP", "留空=自动探测", reader=reader, writer=writer)

    ui.section("2/4 外部资源")
    use_dns = _ask_yes_no(
        ui, "用 Cloudflare 管理 DNS A 记录？",
        "Y：自动创建/更新 <前缀>.<域名> 的 A 记录（需要 CF 凭据）",
        default=True, reader=reader, writer=writer,
    )
    use_acme = _ask_yes_no(
        ui, "用 acme.sh 自动签发 TLS 证书？",
        "TUIC / Hysteria2 需要证书；Y 会走 Cloudflare DNS-01 签发",
        default=True, reader=reader, writer=writer,
    )

    env = {}
    if use_dns or use_acme:
        ui.section("3/4 Cloudflare 凭据（仅本次内存使用，不写盘）")
        env["CF_Token"] = _ask_secret(
            ui, "Cloudflare API Token", "Zone.DNS 编辑权限",
            reader=reader, writer=writer,
        )
        env["CF_Zone_ID"] = _ask(
            ui, "Cloudflare Zone ID", "域名的 Zone ID",
            reader=reader, writer=writer,
        )
    else:
        ui.section("3/4 Cloudflare 凭据")
        ui.warn("已跳过 DNS 与证书：你需要自己解析域名并准备证书文件")

    use_runtime = _ask_yes_no(
        ui, "启用运行时适配器？",
        "systemd / nftables / watchdog / 每日自动升级（生产建议 Y）",
        default=True, reader=reader, writer=writer,
    )

    ui.section("4/4 产物路径")
    server_out = _ask(ui, "服务端配置", "sing-box 主配置", default=DEFAULT_SERVER_OUT, reader=reader, writer=writer)
    client_out = _ask(ui, "客户端配置", "可导入 GUI 的完整客户端配置", default=DEFAULT_CLIENT_OUT, reader=reader, writer=writer)
    links_out = _ask(ui, "分享链接", "anytls:// tuic:// hy2:// 文本", default=DEFAULT_LINKS_OUT, reader=reader, writer=writer)

    plan = {
        "domain_root": domain,
        "protocols": [item.strip() for item in str(protocols).split(",") if item.strip()],
        "tunnel_mode": tunnel_mode,
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
    return plan, env


def _confirm(ui: UI, plan, dry_run: bool, reader=None, writer=None) -> bool:
    adapters = plan.adapters
    runtime = adapters.get("runtime") or {}
    ui.section("即将执行")
    ui.kv("域名", plan.domain_root)
    ui.kv("协议", ", ".join(plan.protocols))
    ui.kv("出站模式", plan.tunnel_mode)
    ui.kv("服务器 IP", plan.server_ip or "自动探测")
    ui.kv("DNS", adapters.get("dns") or "跳过（自己管理）")
    ui.kv("证书", adapters.get("acme") or "跳过（自己管理）")
    ui.kv("运行时", ", ".join(f"{k}={v}" for k, v in runtime.items() if v) or "关闭")
    ui.kv("服务端配置", plan.outputs.get("server_config", "?"))
    if dry_run:
        ui.warn("DRY-RUN：只打印将执行的步骤，不改动系统")
        return True
    prefix = ui.red("这会覆盖 /etc/sing-box 并重启 sing-box")
    ui.warn(prefix)
    reader = reader or sys.stdin
    writer = writer or sys.stdout
    writer.write("    确认执行？[y/N] ")
    writer.flush()
    line = reader.readline()
    return line.strip().lower() in ("y", "yes")


def _load_or_prompt(args, ui):
    """Return ``(plan, env)`` from ``--plan`` or the interactive wizard."""

    if getattr(args, "plan", None):
        return load_plan(args.plan), {}
    plan_mapping, env = interactive_plan(
        domain=getattr(args, "domain", None),
        protocols=getattr(args, "protocols", None),
        ui=ui,
    )
    return DeployPlan.from_mapping(plan_mapping), env


def _detect_or_placeholder(plan) -> str:
    try:
        from .core.network import detect_public_ipv4

        return detect_public_ipv4()
    except OpsError:
        return DRY_RUN_IP


def _run(args) -> int:
    json_mode = bool(getattr(args, "json", False))
    ui = UI(io.StringIO()) if json_mode else UI()
    try:
        if getattr(args, "command", None) == "certs":
            from .adapters.acme.prune import DEFAULT_ACME_HOME, prune_certs
            from .core.command import LocalCommandRunner

            keep = [item for item in (getattr(args, "keep", "") or "").split(",") if item.strip()]
            dry_run = not bool(getattr(args, "apply", False))
            runner = LocalCommandRunner()
            result = prune_certs(
                runner,
                acme_home=getattr(args, "acme_home", DEFAULT_ACME_HOME),
                keep_hosts=keep,
                dry_run=dry_run,
            )
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 0

        if getattr(args, "command", None) == "destroy" and not getattr(args, "plan", None):
            raise OpsError("destroy requires --plan")

        if args.command == "plan":
            plan_mapping, _ = interactive_plan(
                domain=getattr(args, "domain", None),
                protocols=getattr(args, "protocols", None),
                ui=ui,
            )
            output = getattr(args, "output", "plan.yaml") or "plan.yaml"
            with open(output, "w", encoding="utf-8") as handle:
                handle.write(formats.dumps(plan_mapping, "yaml"))
            ui.success(f"已写出 {output}（凭据不写盘；部署时请 export CF_Token/CF_Zone_ID）")
            return 0

        plan, env = _load_or_prompt(args, ui)
        for key, value in (env or {}).items():
            if value:
                os.environ[key] = value

        dry_run = True if args.command == "context" else bool(getattr(args, "dry_run", False))
        runner = make_runner(dry_run)
        suite = build_suite(plan, runner)

        if args.command == "context":
            generated = suite.secrets.generate(plan, dry_run=True)
            server_ip = plan.server_ip or _detect_or_placeholder(plan)
            context = build_context(
                plan, generated.credentials, server_ip,
                subdomain_prefixes=generated.subdomain_prefixes,
            )
            print(formats.dumps(context, getattr(args, "format", None) or plan.output_format))
            return 0

        if json_mode and not dry_run and not getattr(args, "yes", False):
            raise OpsError("--json with a real run requires --yes")
        if not json_mode and not getattr(args, "yes", False) and not _confirm(ui, plan, dry_run):
            ui.warn("已取消")
            return 0

        def progress(step):
            ui.step(STEP_LABELS.get(step, step))

        if args.command in ("deploy", "redeploy"):
            ui.banner(f"{PROG} · 开始部署" + ("（dry-run）" if dry_run else ""))
            report = deploy(plan, suite, dry_run=dry_run, progress=progress)
        else:
            ui.banner(f"{PROG} · 开始卸载")
            report = destroy(plan, suite, dry_run=dry_run, progress=progress)
    except OpsError as exc:
        ui.error(str(exc))
        if json_mode:
            print(f"error: {exc}", file=sys.stderr)
        if "Cloudflare credentials" in str(exc):
            ui.warn("向导里填 CF 凭据，或先 export CF_Token / CF_Zone_ID")
        return 1
    except (OSError, formats.FormatError, ValueError) as exc:
        ui.error(str(exc))
        if json_mode:
            print(f"error: {exc}", file=sys.stderr)
        return 2

    if json_mode:
        print(json.dumps(report.as_dict(), indent=2, ensure_ascii=False))
        return 0

    ui.section("结果")
    ui.kv("action", report.action)
    ui.kv("server_ip", report.server_ip or "-")
    ui.kv("steps", ", ".join(report.steps))
    if report.outputs:
        for key, path in report.outputs.items():
            ui.success(f"{key} -> {path}")
    if report.dry_run:
        ui.warn("dry-run 结束，未改动系统")
    else:
        ui.success("部署完成")
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
