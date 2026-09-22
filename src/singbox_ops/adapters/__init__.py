"""Adapters: the pluggable ports on the ops dock.

Each adapter is an ordinary Python class implementing a small protocol. We do
**not** use setuptools entry points or dynamic discovery here: a plain name ->
factory mapping keeps the two plugin systems (providers vs adapters) from
tangling.
"""

from __future__ import annotations

from .base import (
    ACMEAdapter,
    DNSAdapter,
    ExportAdapter,
    RuntimeAdapter,
    SecretsAdapter,
    StateAdapter,
)

__all__ = [
    "ACMEAdapter",
    "DNSAdapter",
    "ExportAdapter",
    "RuntimeAdapter",
    "SecretsAdapter",
    "StateAdapter",
]
