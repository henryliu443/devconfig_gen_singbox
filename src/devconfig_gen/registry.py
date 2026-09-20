"""Provider registration and lookup."""

from __future__ import annotations

from typing import Dict, Iterable

from .models import ConfigProvider
from .providers import CustomProvider, EnvProvider, JsonProvider
from .providers.singbox import SingBoxProvider


class ProviderRegistry:
    def __init__(self, providers: Iterable[ConfigProvider] = ()):
        self._providers: Dict[str, ConfigProvider] = {}
        for provider in providers:
            self.register(provider)

    def register(self, provider: ConfigProvider) -> None:
        name = str(provider.name).strip().lower()
        if not name or name != provider.name:
            raise ValueError("provider names must be non-empty lowercase strings")
        if name in self._providers:
            raise ValueError(f"provider already registered: {name}")
        self._providers[name] = provider

    def get(self, name: str) -> ConfigProvider:
        try:
            return self._providers[str(name).strip().lower()]
        except KeyError as exc:
            available = ", ".join(self.names()) or "none"
            raise ValueError(f"unknown provider {name!r}; available: {available}") from exc

    def names(self):
        return tuple(sorted(self._providers))


default_registry = ProviderRegistry(
    (CustomProvider(), JsonProvider(), EnvProvider(), SingBoxProvider())
)
