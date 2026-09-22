"""Public IPv4 discovery.

The URL list mirrors the original deployment tool. ``fetch`` is injectable so
tests never hit the network.
"""

from __future__ import annotations

import urllib.request
from typing import Callable, Iterable, Optional

from .exceptions import AdapterError

IP_DETECT_URLS = (
    "https://api.ipify.org",
    "https://ipv4.icanhazip.com",
    "https://checkip.amazonaws.com",
)


def _default_fetch(url: str, timeout: float = 10.0) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "singbox-ops"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8")


def _valid_ipv4(candidate: str) -> bool:
    parts = candidate.split(".")
    if len(parts) != 4:
        return False
    return all(part.isdigit() and 0 <= int(part) <= 255 for part in parts)


def detect_public_ipv4(
    urls: Iterable[str] = IP_DETECT_URLS,
    fetch: Optional[Callable[[str], str]] = None,
) -> str:
    """Return the first valid public IPv4 address found, or raise."""

    fetch = fetch or _default_fetch
    errors = []
    for url in urls:
        try:
            candidate = fetch(url).strip()
        except Exception as exc:  # noqa: BLE001 - report the aggregate below
            errors.append(f"{url}: {exc}")
            continue
        if _valid_ipv4(candidate):
            return candidate
        errors.append(f"{url}: invalid response {candidate!r}")
    detail = "; ".join(errors) if errors else "no URLs configured"
    raise AdapterError(f"could not detect public IPv4 address ({detail})")
