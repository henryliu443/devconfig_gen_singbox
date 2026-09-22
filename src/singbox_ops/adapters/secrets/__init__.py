"""Secret / context-material adapters."""

from __future__ import annotations

from .base import GeneratedSecrets, SecretsAdapter
from .python_secrets import PythonSecrets
from .singbox_subprocess import SingboxSubprocessSecrets
from .static import StaticSecrets

__all__ = [
    "GeneratedSecrets",
    "PythonSecrets",
    "SecretsAdapter",
    "SingboxSubprocessSecrets",
    "StaticSecrets",
]
