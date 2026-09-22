"""Deployment/operations layer for the sing-box provider.

``devconfig_gen`` stays a pure, side-effect-free configuration engine. This
sibling package owns everything that touches the outside world: DNS records,
TLS certificates, package installation, systemd, firewall rules, watchdogs and
state files.

The two packages are deliberately isolated:

- ``devconfig_gen``  -> context in, artifacts out. No I/O beyond explicit writes.
- ``singbox_ops``    -> orchestrates side effects and *calls* the engine.

Nothing in this package is registered as a ``ConfigProvider``.
"""

from __future__ import annotations

from .core.exceptions import AdapterError, CommandError, OpsError, PlanError
from .core.plan import DeployPlan, load_plan

__all__ = [
    "AdapterError",
    "CommandError",
    "DeployPlan",
    "OpsError",
    "PlanError",
    "load_plan",
]
__version__ = "0.1.0"
