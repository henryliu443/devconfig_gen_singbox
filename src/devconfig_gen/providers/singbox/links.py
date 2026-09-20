"""Share-link aggregation.

Links are derived output: one line per enabled protocol, in input order, so the
result is deterministic and stable.
"""

from __future__ import annotations

from typing import Sequence

from .models import BuildContext, ProtocolConfig
from .plugins import get_plugin


def build_links(protocols: Sequence[ProtocolConfig], ctx: BuildContext) -> str:
    lines = []
    for cfg in protocols:
        plugin = get_plugin(cfg.type)
        if plugin is None:
            continue
        lines.append(plugin.build_share_link(cfg, ctx))
    if not lines:
        return ""
    return "\n".join(lines) + "\n"
