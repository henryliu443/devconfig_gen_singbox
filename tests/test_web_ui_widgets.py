"""Tests for the WebUI widget registry and provider-declared widgets."""

import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from devconfig_gen.models import (
    GeneratedArtifact,
    GenerationRequest,
    GenerationResult,
    WebUIWidgets,
)
from devconfig_gen.registry import ProviderRegistry, default_registry
from devconfig_gen.web_ui import WebUIRequestHandler

WIDGET_SOURCE = (
    "(ctx) => { const el = document.createElement('div'); "
    "el.className = 'widget-demo'; return el; }"
)


class _WidgetProvider:
    name = "widgetdemo"

    def validate(self, request):
        return ()

    def generate(self, request: GenerationRequest) -> GenerationResult:
        return GenerationResult(
            provider=self.name,
            artifacts=(
                GeneratedArtifact(name="out.txt", content="ok", media_type="text/plain"),
            ),
        )

    def web_ui_widgets(self):
        return {"tree": WIDGET_SOURCE}


class _PlainProvider:
    name = "plain"

    def validate(self, request):
        return ()

    def generate(self, request: GenerationRequest) -> GenerationResult:
        return GenerationResult(
            provider=self.name,
            artifacts=(
                GeneratedArtifact(name="plain.json", content={}, media_type="application/json"),
            ),
        )


class _WidgetHandler(WebUIRequestHandler):
    registry = ProviderRegistry((_WidgetProvider(), _PlainProvider()))


class TestWebUIWidgets(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._workspace = tempfile.TemporaryDirectory()
        cls.workspace = Path(cls._workspace.name)
        _WidgetHandler.workspace_root = cls.workspace
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), _WidgetHandler)
        cls.port = cls.server.server_port
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls._workspace.cleanup()

    def _url(self, path: str) -> str:
        return f"http://127.0.0.1:{self.port}{path}"

    def _get(self, path):
        with urllib.request.urlopen(self._url(path)) as resp:
            return resp.status, resp.read().decode("utf-8")

    def test_web_ui_widgets_protocol_is_exported(self):
        self.assertTrue(hasattr(WebUIWidgets, "web_ui_widgets"))

    def test_default_providers_declare_no_widgets(self):
        for name in default_registry.names():
            provider = default_registry.get(name)
            self.assertFalse(callable(getattr(provider, "web_ui_widgets", None)))

    def test_api_widgets_returns_provider_widgets(self):
        status, body = self._get("/api/widgets?provider=widgetdemo")
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertEqual(data["provider"], "widgetdemo")
        self.assertEqual(data["widgets"]["tree"], WIDGET_SOURCE)

    def test_api_widgets_empty_for_provider_without_widgets(self):
        status, body = self._get("/api/widgets?provider=plain")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["widgets"], {})

    def test_api_widgets_unknown_provider_returns_400(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self._get("/api/widgets?provider=missing")
        self.assertEqual(ctx.exception.code, 400)
        try:
            self.assertIn("unknown provider", ctx.exception.read().decode("utf-8"))
        finally:
            ctx.exception.close()

    def test_api_schema_and_widgets_share_provider(self):
        status, body = self._get("/api/schema?provider=widgetdemo")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body), [])
        status, body = self._get("/api/widgets?provider=widgetdemo")
        self.assertEqual(status, 200)
        self.assertIn("tree", json.loads(body)["widgets"])

    def test_index_embeds_widget_registry(self):
        status, body = self._get("/")
        self.assertEqual(status, 200)
        self.assertIn("WidgetRegistry", body)
        self.assertIn("DEFAULT_WIDGET_FACTORIES", body)
        self.assertIn("loadProviderWidgets", body)
        self.assertIn("/api/widgets", body)
        for field_type in ("string", "integer", "boolean", "mapping", "document", "tree"):
            self.assertIn(f"{field_type}:", body)

    def test_index_embeds_sidebar_links(self):
        status, body = self._get("/")
        self.assertEqual(status, 200)
        self.assertIn("sidebar", body)
        self.assertIn("btnSidebar", body)
        self.assertIn("https://github.com/henryliu443/devconfig_gen_singbox", body)
        self.assertIn("https://henryliu443.github.io/DevConfig-Gen/", body)
        self.assertIn("mailto:henryliu443@gmail.com", body)


if __name__ == "__main__":
    unittest.main()
