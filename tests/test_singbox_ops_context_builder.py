import unittest

from devconfig_gen.engine import generate_pipeline
from devconfig_gen.providers.singbox import schema as singbox_schema

from singbox_ops.core.context_builder import build_context, needed_certificates
from singbox_ops.core.plan import DeployPlan
from tests._ops_support import static_secrets


class ContextBuilderTests(unittest.TestCase):
    def setUp(self):
        self.plan = DeployPlan.from_mapping(
            {
                "domain_root": "example.com",
                "protocols": ["anytls", "tuic", "hysteria2"],
            }
        )
        self.secrets = static_secrets()

    def test_context_is_valid_provider_input(self):
        context = build_context(
            self.plan,
            self.secrets["credentials"],
            "203.0.113.10",
            subdomain_prefixes=self.secrets["subdomain_prefixes"],
        )
        parsed, diagnostics = singbox_schema.parse(context, None)
        self.assertEqual([item.message for item in diagnostics], [])
        self.assertEqual(len(parsed.enabled_protocols()), 3)
        self.assertEqual(context["client"]["server_ip"], "203.0.113.10")
        self.assertEqual(context["options"]["target"], "both")

    def test_generated_context_produces_artifacts(self):
        context = build_context(
            self.plan,
            self.secrets["credentials"],
            "203.0.113.10",
            subdomain_prefixes=self.secrets["subdomain_prefixes"],
        )
        result = generate_pipeline("singbox", context=context)
        names = [artifact.name for artifact in result.artifacts]
        self.assertEqual(
            names,
            ["sing-box.server.json", "sing-box.client.json", "sing-box-links.txt"],
        )

    def test_needed_certificates(self):
        needed = needed_certificates(self.plan)
        self.assertEqual(needed, {"tuic": "tuic", "hysteria2": "hy2"})

    def test_missing_prefix_raises(self):
        from singbox_ops.core.exceptions import AdapterError

        with self.assertRaises(AdapterError):
            build_context(self.plan, self.secrets["credentials"], "1.2.3.4", subdomain_prefixes={})


if __name__ == "__main__":
    unittest.main()
