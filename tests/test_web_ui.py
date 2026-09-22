import http.client
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from devconfig_gen import generate_from_file, load_file
from devconfig_gen.web_ui import WebUIRequestHandler

from tests._support import EXAMPLES

SAMPLE_YAML = EXAMPLES / "custom.yaml"


class TestWebUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._workspace = tempfile.TemporaryDirectory()
        cls.workspace = Path(cls._workspace.name)
        WebUIRequestHandler.workspace_root = cls.workspace
        # Bind to port 0 for an ephemeral OS-assigned free port
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), WebUIRequestHandler)
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

    def _post(self, path, payload):
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self._url(path), data=data, headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(req) as resp:
                return resp.status, json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            try:
                body = json.loads(exc.read().decode("utf-8"))
            finally:
                exc.close()
            return exc.code, body

    def test_get_index_html(self):
        status, body = self._get("/")
        self.assertEqual(status, 200)
        self.assertIn("DevConfig-Gen", body)
        self.assertIn("Live Generated Configuration", body)
        self.assertIn("fmtXml", body)
        self.assertIn("doc-dropzone", body)
        self.assertIn("doc-editor-textarea", body)
        self.assertIn("btnClearAll", body)
        self.assertIn("renderTreeEditor", body)
        self.assertIn("tree-children", body)
        self.assertIn("tree-bulk", body)
        self.assertIn("treeBulkAdd", body)

    def test_index_is_not_cached(self):
        with urllib.request.urlopen(self._url("/")) as resp:
            cache = resp.headers.get("Cache-Control", "")
        self.assertIn("no-store", cache)

    def test_get_api_providers_includes_custom(self):
        status, body = self._get("/api/providers")
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertIn("custom", data["providers"])

    def test_get_api_schema_custom_uses_tree_field(self):
        status, body = self._get("/api/schema?provider=custom")
        self.assertEqual(status, 200)
        steps = json.loads(body)
        self.assertEqual(steps[0]["fields"][0]["type"], "tree")

    def test_get_api_providers(self):
        status, body = self._get("/api/providers")
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertIn("custom", data["providers"])
        self.assertIn("json", data["providers"])
        self.assertIn("env", data["providers"])

    def test_get_api_schema(self):
        status, body = self._get("/api/schema?provider=custom")
        self.assertEqual(status, 200)
        steps = json.loads(body)
        self.assertGreaterEqual(len(steps), 1)
        self.assertEqual(steps[0]["id"], "document")

    def test_get_api_schema_includes_i18n(self):
        status, body = self._get("/api/schema?provider=custom")
        self.assertEqual(status, 200)
        steps = json.loads(body)
        self.assertIn("zh", steps[0]["i18n"])
        self.assertIn("title", steps[0]["fields"][0]["i18n"]["zh"])

    def test_get_api_schema_unknown_provider_returns_400(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self._get("/api/schema?provider=missing")
        self.assertEqual(ctx.exception.code, 400)
        try:
            self.assertIn("unknown provider", ctx.exception.read().decode("utf-8"))
        finally:
            ctx.exception.close()

    def test_post_api_validate(self):
        status, res = self._post("/api/validate", {"provider": "env", "context": {}})
        self.assertEqual(status, 200)
        self.assertFalse(res["valid"])
        self.assertGreater(len(res["diagnostics"]), 0)

        status, res = self._post(
            "/api/validate",
            {"provider": "custom", "context": {"document": {"app": {"name": "test-svc"}}}},
        )
        self.assertEqual(status, 200)
        self.assertTrue(res["valid"])
        self.assertEqual(res["diagnostics"], [])

    def test_post_api_validate_unknown_provider_returns_400(self):
        status, res = self._post("/api/validate", {"provider": "missing", "context": {}})
        self.assertEqual(status, 400)
        self.assertIn("unknown provider", res["error"])

    def test_post_api_generate(self):
        status, res = self._post(
            "/api/generate",
            {
                "provider": "custom",
                "context": {"document": {"app": {"name": "test-svc", "port": 8080}}},
                "format": "yaml",
            },
        )
        self.assertEqual(status, 200)
        artifact = res["artifacts"][0]
        self.assertEqual(artifact["name"], "custom.yaml")
        self.assertIn("name: test-svc", artifact["content"])

    def test_post_api_generate_invalid_returns_400(self):
        status, res = self._post(
            "/api/generate", {"provider": "env", "context": {}, "format": "yaml"}
        )
        self.assertEqual(status, 400)
        self.assertIn("error", res)

    def test_webui_generate_matches_engine_byte_for_byte(self):
        context = load_file(SAMPLE_YAML)
        with tempfile.TemporaryDirectory() as directory:
            generate_from_file(
                "custom", str(SAMPLE_YAML), output_dir=directory, output_format="yaml"
            )
            expected = (Path(directory) / "custom.yaml").read_text(encoding="utf-8")

        status, res = self._post(
            "/api/generate", {"provider": "custom", "context": context, "format": "yaml"}
        )
        self.assertEqual(status, 200)
        self.assertEqual(res["artifacts"][0]["content"], expected)

    def test_post_api_export(self):
        payload = {
            "provider": "custom",
            "context": {"document": {"app": {"name": "export-svc", "port": 3000}}},
            "format": "json",
            "output_dir": ".",
        }
        status, res = self._post("/api/export", payload)
        self.assertEqual(status, 200)
        self.assertTrue(res["success"])
        saved_file = self.workspace / "custom.json"
        self.assertTrue(saved_file.exists())
        data = json.loads(saved_file.read_text(encoding="utf-8"))
        self.assertEqual(data["app"]["name"], "export-svc")

    def test_post_api_export_rejects_path_escape(self):
        payload = {
            "provider": "custom",
            "context": {"document": {"app": {"name": "escape-svc", "port": 3000}}},
            "format": "json",
            "output_dir": "../outside",
        }
        status, res = self._post("/api/export", payload)
        self.assertEqual(status, 400)
        self.assertIn("workspace root", res["error"])

    def test_forbidden_host_is_rejected(self):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            conn.request("GET", "/api/providers", headers={"Host": "evil.example.com"})
            response = conn.getresponse()
            self.assertEqual(response.status, 403)
        finally:
            conn.close()

    def test_post_api_parse(self):
        status, res = self._post(
            "/api/parse", {"content": "app:\n  name: parsed-svc\n  port: 8080\n"}
        )
        self.assertEqual(status, 200)
        self.assertEqual(res["context"]["app"]["name"], "parsed-svc")

    def test_post_api_parse_invalid_returns_400(self):
        status, res = self._post("/api/parse", {"content": "{not valid"})
        self.assertEqual(status, 400)
        self.assertIn("error", res)


if __name__ == "__main__":
    unittest.main()
