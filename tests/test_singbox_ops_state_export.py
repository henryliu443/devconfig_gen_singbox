import json
import unittest

from devconfig_gen.models import GeneratedArtifact

from singbox_ops.adapters.export.local_files import LocalFilesExport, match_output_key
from singbox_ops.adapters.state.local_json import LocalJsonState
from tests._ops_support import FakeRunner

OUTPUTS = {
    "server_config": "/etc/sing-box/config.json",
    "client_config": "/root/singbox-client.json",
    "links": "/root/singbox-links.txt",
}


class StateTests(unittest.TestCase):
    def test_save_then_load(self):
        runner = FakeRunner()
        state = LocalJsonState("/etc/sing-box-deploy/state.json", runner=runner)
        state.save({"domain_root": "example.com", "dns_record_ids": {"a": "1"}})
        loaded = state.load()
        self.assertEqual(loaded["domain_root"], "example.com")
        self.assertEqual(loaded["version"], 1)
        self.assertIn("deployed_at", loaded)
        # state is written 0600
        self.assertEqual(runner.writes[0][2], 0o600)

    def test_load_missing_returns_none(self):
        self.assertIsNone(LocalJsonState("/nope.json", runner=FakeRunner()).load())

    def test_state_is_valid_json(self):
        runner = FakeRunner()
        LocalJsonState("/state.json", runner=runner).save({"x": 1})
        json.loads(runner.writes[0][1])


class ExportTests(unittest.TestCase):
    def test_match_output_key(self):
        self.assertEqual(match_output_key("sing-box.server.json"), "server_config")
        self.assertEqual(match_output_key("sing-box.client.yaml"), "client_config")
        self.assertEqual(match_output_key("sing-box-links.txt"), "links")
        self.assertIsNone(match_output_key("unknown.txt"))

    def test_replaces_symlink_destination(self):
        runner = FakeRunner(links=["/etc/sing-box/config.json"])
        artifacts = [
            GeneratedArtifact("sing-box.server.json", {"a": 1}, "application/json"),
        ]
        LocalFilesExport(runner=runner).write(artifacts, {"server_config": "/etc/sing-box/config.json"})
        # the legacy symlink is removed, then a real file is written
        self.assertIn("/etc/sing-box/config.json", runner.removed)
        self.assertTrue(any(path == "/etc/sing-box/config.json" for path, _, _ in runner.writes))

    def test_writes_artifacts(self):
        runner = FakeRunner()
        artifacts = [
            GeneratedArtifact("sing-box.server.json", {"log": {}}, "application/json"),
            GeneratedArtifact("sing-box.client.json", {"dns": {}}, "application/json"),
            GeneratedArtifact("sing-box-links.txt", "tuic://...\n", "text/plain"),
        ]
        written = LocalFilesExport(runner=runner).write(artifacts, OUTPUTS)
        self.assertEqual(set(written), {"server_config", "client_config", "links"})
        self.assertEqual(len(runner.writes), 3)
        self.assertEqual(runner.writes[2][1], "tuic://...\n")


if __name__ == "__main__":
    unittest.main()
