"""acme.sh + Cloudflare DNS-01 certificate issuance.

Renewal is intentionally *not* handled here: the adapter only makes sure a valid
certificate exists. A systemd timer / cron job can call this adapter again, which
is idempotent (a valid, host-matching certificate is left untouched).
"""

from __future__ import annotations

import os
from typing import Mapping, Optional, Sequence, Tuple

from ...core.command import CommandRunner, LocalCommandRunner
from ...core.exceptions import AdapterError
from ...core.protocols import CERT_PATHS, TLS_PROTOCOLS

ACME_SH_PATH = "/root/.acme.sh/acme.sh"
ACME_INSTALL_URL = "https://get.acme.sh"
ACME_CA = "letsencrypt"
CERT_VALIDITY_WINDOW = 30 * 24 * 3600
CF_TOKEN_ENV = "CF_Token"
CF_ZONE_ID_ENV = "CF_Zone_ID"
RELOAD_CMD = "systemctl try-restart sing-box >/dev/null 2>&1 || true"

SUPPORTED_PROTOCOLS = TLS_PROTOCOLS


class CloudflareDNS01ACME:
    def __init__(
        self,
        runner: Optional[CommandRunner] = None,
        acme_sh: str = ACME_SH_PATH,
        ca: str = ACME_CA,
        token: Optional[str] = None,
        zone_id: Optional[str] = None,
        cert_paths: Optional[Mapping[str, Tuple[str, str]]] = None,
        reload_cmd: str = RELOAD_CMD,
    ):
        self.runner = runner or LocalCommandRunner()
        self.acme_sh = acme_sh
        self.ca = ca
        self.token = token
        self.zone_id = zone_id
        self.cert_paths = dict(cert_paths or CERT_PATHS)
        self.reload_cmd = reload_cmd

    # -- helpers ---------------------------------------------------------
    def _dns_env(self) -> Mapping[str, str]:
        token = (self.token or os.environ.get(CF_TOKEN_ENV, "")).strip()
        zone_id = (self.zone_id or os.environ.get(CF_ZONE_ID_ENV, "")).strip()
        if not token or not zone_id:
            raise AdapterError(
                "Cloudflare DNS-01 credentials missing; set CF_Token and CF_Zone_ID"
            )
        return {CF_TOKEN_ENV: token, CF_ZONE_ID_ENV: zone_id}

    def cert_is_valid(self, cert_path: str, host: str) -> bool:
        if not self.runner.exists(cert_path):
            return False
        check = self.runner.run(
            ["openssl", "x509", "-in", cert_path, "-noout", "-checkend", str(CERT_VALIDITY_WINDOW)],
            check=False,
        )
        if check.returncode != 0:
            return False
        san = self.runner.run(
            ["openssl", "x509", "-in", cert_path, "-noout", "-ext", "subjectAltName"],
            check=False,
        )
        return f"DNS:{host}" in (san.stdout or "")

    def _ensure_acme_sh(self) -> str:
        if self.runner.exists(self.acme_sh):
            return self.acme_sh
        self.runner.shell(f"curl -fsSL {ACME_INSTALL_URL} | sh", check=True)
        if not self.runner.exists(self.acme_sh):
            # Fall back to PATH lookup; the caller's runner may report a stub.
            return "acme.sh"
        return self.acme_sh

    def _issue_and_install(self, host: str, cert_path: str, key_path: str) -> None:
        env = self._dns_env()
        if self.cert_is_valid(cert_path, host):
            return
        acme_sh = self._ensure_acme_sh()
        self.runner.run([acme_sh, "--set-default-ca", "--server", self.ca], check=True)
        self.runner.run(
            [acme_sh, "--issue", "--dns", "dns_cf", "-d", host, "--keylength", "ec-256", "--server", self.ca],
            check=True,
            env=env,
        )
        self.runner.run(
            [
                acme_sh,
                "--install-cert",
                "-d",
                host,
                "--ecc",
                "--fullchain-file",
                cert_path,
                "--key-file",
                key_path,
                "--reloadcmd",
                self.reload_cmd,
            ],
            check=True,
        )
        self.runner.chmod(key_path, 0o600)

    # -- adapter contract ------------------------------------------------
    def apply(
        self,
        hosts: Mapping[str, str],
        protocols: Sequence[str],
        *,
        dry_run: bool = False,
    ) -> Mapping[str, Tuple[str, str]]:
        wanted = [protocol for protocol in protocols if protocol in SUPPORTED_PROTOCOLS]
        result: dict = {}
        for protocol in wanted:
            host = hosts.get(protocol)
            if not host:
                raise AdapterError(f"missing hostname for TLS protocol {protocol!r}")
            cert_path, key_path = self.cert_paths[protocol]
            if not dry_run:
                self.runner.mkdir(os.path.dirname(cert_path), mode=0o700)
                self.runner.mkdir(os.path.dirname(key_path), mode=0o700)
                self._issue_and_install(host, cert_path, key_path)
            result[protocol] = (cert_path, key_path)
        return result
