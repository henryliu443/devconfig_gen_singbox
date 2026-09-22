"""Shared fakes for singbox_ops tests (no real system, no network)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Callable, Mapping, Optional, Sequence

from singbox_ops.core.command import CommandResult, RecordingRunner
from singbox_ops.core.exceptions import CommandError

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
EXAMPLES = ROOT / "examples"


def run_ops_cli(*args):
    env = dict(os.environ)
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(SRC) + (os.pathsep + existing if existing else "")
    return subprocess.run(
        [sys.executable, "-m", "singbox_ops.cli", *args],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(ROOT),
    )

CommandHandler = Callable[[Sequence[str], Mapping[str, str]], CommandResult]


class FakeRunner(RecordingRunner):
    """A RecordingRunner that can pre-exist files and answer commands."""

    def __init__(
        self,
        existing: Optional[Sequence[str]] = None,
        files: Optional[Mapping[str, str]] = None,
        handler: Optional[CommandHandler] = None,
    ):
        super().__init__(existing=existing)
        if files:
            self._files.update(dict(files))
        self.handler = handler

    def run(self, args, *, check=True, env=None):
        self.commands.append(("run", tuple(str(item) for item in args), dict(env or {})))
        result = self.handler(args, env or {}) if self.handler else CommandResult(args, 0, "", "")
        if check and result.returncode != 0:
            raise CommandError(args, result.returncode, result.stdout, result.stderr)
        return result


class FakeCloudflare:
    """In-memory Cloudflare DNS API."""

    def __init__(self):
        self.records: dict = {}
        self.next_id = 0

    def __call__(self, method, path, token, data=None):
        if method == "GET":
            return {
                "success": True,
                "result": list(self.records.values()),
                "result_info": {"total_pages": 1},
            }
        if method == "POST":
            self.next_id += 1
            record_id = f"rec{self.next_id}"
            self.records[record_id] = {"id": record_id, "name": data["name"], "content": data["content"], "comment": data.get("comment")}
            return {"success": True, "result": self.records[record_id]}
        if method == "DELETE":
            record_id = path.rsplit("/", 1)[-1]
            self.records.pop(record_id, None)
            return {"success": True, "result": {}}
        raise AssertionError(f"unexpected method {method}")


def static_secrets(protocols=("anytls", "tuic", "hysteria2")) -> dict:
    credentials = {}
    prefixes = {"reality": "a1b2", "tuic": "c3d4", "hy2": "e5f6"}
    for protocol in protocols:
        if protocol == "anytls":
            credentials["anytls"] = {
                "password": "pwd-anytls",
                "private_key": "priv",
                "public_key": "pub",
                "short_id": "sid",
            }
        elif protocol == "tuic":
            credentials["tuic"] = {"uuid": "00000000-0000-0000-0000-000000000000", "password": "pwd-tuic"}
        else:
            credentials["hysteria2"] = {"password": "pwd-hy2", "obfs_password": "pwd-obfs"}
    return {"credentials": credentials, "subdomain_prefixes": prefixes}


def base_plan_mapping() -> dict:
    return {
        "domain_root": "example.com",
        "server_ip": "203.0.113.10",
        "protocols": ["anytls", "tuic", "hysteria2"],
        "tunnel_mode": "proxy",
        "adapters": {
            "secrets": "static",
            "dns": "cloudflare",
            "acme": "cloudflare-dns01",
            "state": "local-json",
            "runtime": {
                "packages": None,
                "systemd": None,
                "firewall": None,
                "watchdog": None,
            },
        },
    }
