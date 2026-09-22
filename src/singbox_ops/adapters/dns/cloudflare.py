"""Cloudflare DNS A-record management.

Only records carrying :data:`MANAGED_COMMENT` are ever created or removed, so a
shared zone never loses the operator's own records. The HTTP transport is
injectable for tests and dry-runs.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Callable, Mapping, Optional

from ...core.exceptions import AdapterError

CF_API_BASE = "https://api.cloudflare.com/client/v4"
CF_TOKEN_ENV = "CF_Token"
CF_ZONE_ID_ENV = "CF_Zone_ID"
MANAGED_COMMENT = "managed:sing-box-deploy"

HttpFn = Callable[..., Mapping[str, Any]]


def default_http(method: str, path: str, token: str, data: Optional[Mapping[str, Any]] = None) -> Mapping[str, Any]:
    url = f"{CF_API_BASE}{path}"
    body = json.dumps(data).encode("utf-8") if data is not None else None
    request = urllib.request.Request(url, data=body, method=method)
    request.add_header("Authorization", f"Bearer {token}")
    request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:  # pragma: no cover - network path
        detail = exc.read().decode("utf-8", errors="replace")
        raise AdapterError(f"Cloudflare API {method} {path} -> {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:  # pragma: no cover - network path
        raise AdapterError(f"Cloudflare API {method} {path} unreachable: {exc}") from exc

    if not payload.get("success"):
        messages = "; ".join(
            str(item.get("message", item)) for item in payload.get("errors", [])
        )
        raise AdapterError(f"Cloudflare API {method} {path} failed: {messages}")
    return payload


class CloudflareDNS:
    def __init__(
        self,
        token: Optional[str] = None,
        zone_id: Optional[str] = None,
        http: Optional[HttpFn] = None,
        comment: str = MANAGED_COMMENT,
    ):
        self.token = token
        self.zone_id = zone_id
        self.http = http or default_http
        self.comment = comment

    # -- credentials -----------------------------------------------------
    def _credentials(self) -> tuple:
        token = (self.token or os.environ.get(CF_TOKEN_ENV, "")).strip()
        zone_id = (self.zone_id or os.environ.get(CF_ZONE_ID_ENV, "")).strip()
        if not token or not zone_id:
            raise AdapterError(
                "Cloudflare credentials missing; set CF_Token and CF_Zone_ID "
                "or pass token/zone_id explicitly"
            )
        return token, zone_id

    # -- low-level API ---------------------------------------------------
    def _list_a_records(self) -> list:
        token, zone_id = self._credentials()
        records: list = []
        page = 1
        while True:
            path = f"/zones/{zone_id}/dns_records?type=A&page={page}&per_page=100"
            payload = self.http("GET", path, token)
            records.extend(payload.get("result", []))
            info = payload.get("result_info", {})
            if page >= int(info.get("total_pages", 1)):
                break
            page += 1
        return records

    def _create(self, fqdn: str, ip: str) -> str:
        token, zone_id = self._credentials()
        data = {
            "type": "A",
            "name": fqdn,
            "content": ip,
            "ttl": 1,
            "proxied": False,
            "comment": self.comment,
        }
        payload = self.http("POST", f"/zones/{zone_id}/dns_records", token, data)
        return payload["result"]["id"]

    def _delete(self, record_id: str) -> None:
        token, zone_id = self._credentials()
        self.http("DELETE", f"/zones/{zone_id}/dns_records/{record_id}", token)

    # -- adapter contract ------------------------------------------------
    def apply(
        self, hosts: Mapping[str, str], ip: str, *, dry_run: bool = False
    ) -> Mapping[str, str]:
        desired = sorted(set(hosts.values()))
        if dry_run:
            return {fqdn: f"dry-run:{fqdn}" for fqdn in desired}

        managed = {
            record["name"]: record
            for record in self._list_a_records()
            if record.get("comment") == self.comment
        }
        record_ids: dict = {}
        for fqdn in desired:
            existing = managed.pop(fqdn, None)
            if existing and existing.get("content") == ip:
                record_ids[fqdn] = existing["id"]
                continue
            if existing:
                self._delete(existing["id"])
            record_ids[fqdn] = self._create(fqdn, ip)

        for leftover in managed.values():
            self._delete(leftover["id"])
        return record_ids

    def destroy(self, record_ids: Mapping[str, str], *, dry_run: bool = False) -> None:
        if dry_run:
            return
        for record_id in record_ids.values():
            if record_id.startswith("dry-run:"):
                continue
            self._delete(record_id)
