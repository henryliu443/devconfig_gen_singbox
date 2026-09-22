import unittest

from singbox_ops.core.exceptions import PlanError
from singbox_ops.core.plan import DeployPlan, load_plan


class PlanParsingTests(unittest.TestCase):
    def test_minimal_plan_defaults(self):
        plan = DeployPlan.from_mapping({"domain_root": "example.com"})
        self.assertEqual(plan.domain_root, "example.com")
        self.assertEqual(plan.protocols, ("anytls", "tuic", "hysteria2"))
        self.assertEqual(plan.tunnel_mode, "proxy")
        self.assertIsNone(plan.server_ip)
        self.assertTrue(plan.detect_server_ip())
        self.assertEqual(plan.adapter_name("dns"), "cloudflare")
        self.assertEqual(plan.adapter_name("state"), "local-json")
        self.assertEqual(plan.runtime_adapter_name("systemd"), "systemd")

    def test_domain_is_normalized(self):
        plan = DeployPlan.from_mapping({"domain_root": "https://Example.COM/"})
        self.assertEqual(plan.domain_root, "example.com")

    def test_protocols_accept_comma_string(self):
        plan = DeployPlan.from_mapping({"domain_root": "example.com", "protocols": "anytls, tuic"})
        self.assertEqual(plan.protocols, ("anytls", "tuic"))

    def test_unknown_protocol_rejected(self):
        with self.assertRaises(PlanError):
            DeployPlan.from_mapping({"domain_root": "example.com", "protocols": ["wireguard"]})

    def test_invalid_domain_rejected(self):
        with self.assertRaises(PlanError):
            DeployPlan.from_mapping({"domain_root": "not a domain"})
        with self.assertRaises(PlanError):
            DeployPlan.from_mapping({})

    def test_invalid_tunnel_mode_rejected(self):
        with self.assertRaises(PlanError):
            DeployPlan.from_mapping({"domain_root": "example.com", "tunnel_mode": "wireguard"})

    def test_adapter_can_be_disabled(self):
        plan = DeployPlan.from_mapping(
            {"domain_root": "example.com", "adapters": {"state": None, "acme": None}}
        )
        self.assertIsNone(plan.adapter_name("state"))
        self.assertIsNone(plan.adapter_name("acme"))

    def test_server_ip_auto_token(self):
        plan = DeployPlan.from_mapping({"domain_root": "example.com", "server_ip": "auto"})
        self.assertIsNone(plan.server_ip)
        self.assertTrue(plan.detect_server_ip())

    def test_tls_protocols(self):
        plan = DeployPlan.from_mapping({"domain_root": "example.com", "protocols": ["anytls", "tuic"]})
        self.assertEqual(plan.tls_protocols(), ("tuic",))

    def test_to_mapping_round_trip(self):
        plan = DeployPlan.from_mapping({"domain_root": "example.com", "server_ip": "1.2.3.4"})
        reparsed = DeployPlan.from_mapping(plan.to_mapping())
        self.assertEqual(reparsed.domain_root, plan.domain_root)
        self.assertEqual(reparsed.protocols, plan.protocols)
        self.assertEqual(reparsed.server_ip, "1.2.3.4")

    def test_load_plan_from_document_text(self):
        plan = load_plan("domain_root: example.com\nprotocols: [anytls]\n")
        self.assertEqual(plan.protocols, ("anytls",))


if __name__ == "__main__":
    unittest.main()
