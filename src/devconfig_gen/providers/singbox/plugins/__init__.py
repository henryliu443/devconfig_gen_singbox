"""Variant plugin registry.

Adding a protocol means adding one module here plus one line in
``_PLUGIN_CLASSES``; nothing in ``provider.py`` / ``schema.py`` / ``route.py``
changes.
"""

from __future__ import annotations

from typing import Optional

from .anytls import AnyTlsPlugin
from .hysteria2 import Hysteria2Plugin
from .tuic import TuicPlugin

_PLUGIN_CLASSES = (AnyTlsPlugin, TuicPlugin, Hysteria2Plugin)

PLUGINS = {cls.protocol_type: cls() for cls in _PLUGIN_CLASSES}


def get_plugin(protocol_type: str) -> Optional[object]:
    """Return the plugin for ``protocol_type`` or ``None`` when unknown."""

    return PLUGINS.get(str(protocol_type).strip().lower())


def protocol_types() -> tuple:
    """Return the registered protocol type names in registry order."""

    return tuple(PLUGINS)


__all__ = ["PLUGINS", "get_plugin", "protocol_types"]
