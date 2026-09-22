import unittest

from singbox_ops.adapters.dns.cloudflare import CloudflareDNS
from singbox_ops.adapters.export.local_files import LocalFilesExport
from singbox_ops.adapters.secrets.static import StaticSecrets
from singbox_ops.adapters.state.local_json import LocalJsonState
from singbox_ops.core.command import RecordingRunner
from singbox_ops.core.exceptions import PlanError
from singbox_ops.core.orchestrator import AdapterSuite, build_suite, deploy, destroy
from singbox_ops.core.plan import DeployPlan
from tests._ops_support import FakeCloudflare, static_secrets


def make_plan():
    return DeployPlan.from_mapping(
        {
            "domain_root": "example.com",
            "server_ip": "203.0.113.10",
            "protocols": ["anytls", "tuic", "hysteria2"],
            "adapters": {"acme": None, "runtime": {}},
            "outputs": {
                "server_config": "/etc/sing-box/config.json",
                "client_config": "/root/singbox-client.json",
                "links": "/root/singbox-links.txt",
            },
        }
    )


def make_suite(runner, http):
    return AdapterSuite(
        secrets=StaticSecrets(static_secrets()),
        dns=CloudflareDNS(token="t", zone_id="z", http=http),
        acme=None,
        state=LocalJsonState("/etc/sing-box-deploy/state.json", runner=runner),
        export=LocalFilesExport(runner=runner),
    )


class BuildSuiteTests(unittest.TestCase):
    def test_builds_named_adapters(self):
        plan = DeployPlan.from_mapping({"domain_root": "example.com", "adapters": {"state": None}})
        suite = build_suite(plan, RecordingRunner())
        self.assertIsNotNone(suite.dns)
        self.assertIsNone(suite.state)
        self.assertIsNotNone(suite.export)

    def test_unknown_adapter_raises_plan_error(self):
        plan = DeployPlan.from_mapping(
            {"domain_root": "example.com", "adapters": {"dns": "route53"}}
        )
        with self.assertRaises(PlanError):
            build_suite(plan, RecordingRunner())


class OrchestratorTests(unittest.TestCase):
    def test_deploy_writes_configs_and_dns(self):
        runner = RecordingRunner()
        http = FakeCloudflare()
        plan = make_plan()
        report = deploy(plan, make_suite(runner, http))

        self.assertEqual(report.action, "deploy")
        self.assertEqual(report.server_ip, "203.0.113.10")
        self.assertEqual(len(report.record_ids), 3)
        self.assertEqual(set(report.outputs), {"server_config", "client_config", "links"})
        self.assertEqual(report.steps[:2], ("secrets", "dns"))
        self.assertIn("generate", report.steps)

        written_paths = [path for path, _, _ in runner.writes]
        self.assertIn("/etc/sing-box/config.json", written_paths)
        # config files are written 0600
        server_write = next(item for item in runner.writes if item[0] == "/etc/sing-box/config.json")
        self.assertEqual(server_write[2], 0o600)
        self.assertIn("inbounds", server_write[1])

    def test_generate_receives_provider_valid_context(self):
        runner = RecordingRunner()
        captured = {}

        def fake_generate(plan, context):
            captured["context"] = context
            from devconfig_gen.engine import generate_pipeline

            return generate_pipeline("singbox", context=dict(context))

        deploy(make_plan(), make_suite(runner, FakeCloudflare()), generate=fake_generate)
        context = captured["context"]
        self.assertEqual(context["network"]["domain_root"], "example.com")
        self.assertEqual(context["client"]["server_ip"], "203.0.113.10")
        self.assertEqual([p["type"] for p in context["network"]["protocols"]], ["anytls", "tuic", "hysteria2"])

    def test_destroy_removes_dns_records_from_state(self):
        runner = RecordingRunner()
        http = FakeCloudflare()
        plan = make_plan()
        suite = make_suite(runner, http)
        deploy(plan, suite)
        self.assertEqual(len(http.records), 3)

        report = destroy(plan, make_suite(runner, http))
        self.assertEqual(report.action, "destroy")
        self.assertEqual(http.records, {})
        self.assertIn("dns", report.steps)

    def test_dry_run_touches_nothing(self):
        runner = RecordingRunner()
        http = FakeCloudflare()
        report = deploy(make_plan(), make_suite(runner, http), dry_run=True)
        self.assertTrue(report.dry_run)
        self.assertEqual(http.records, {})
        # export still records intended writes for inspection
        self.assertEqual(len(report.outputs), 3)


if __name__ == "__main__":
    unittest.main()
