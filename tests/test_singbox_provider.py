import json
import tempfile
import unittest
from pathlib import Path

from devconfig_gen import formats, generate
from devconfig_gen.engine import diagnose_request, generate_pipeline
from devconfig_gen.models import GenerationRequest
from devconfig_gen.providers.singbox import SingBoxProvider
from devconfig_gen.providers.singbox import route as singbox_route
from devconfig_gen.providers.singbox.models import BuildContext, ClientConfig, NetworkConfig, ProtocolConfig
from devconfig_gen.providers.singbox.plugins import get_plugin, protocol_types
from devconfig_gen.providers.singbox.plugins.anytls import AnyTlsPlugin
from devconfig_gen.providers.singbox.plugins.hysteria2 import Hysteria2Plugin
from devconfig_gen.providers.singbox.plugins.tuic import TuicPlugin
from tests._support import run_cli

HOSTS = {
    "reality": "a1b2.example.com",
    "tuic": "c3d4.example.com",
    "hy2": "e5f6.example.com",
}


def valid_context():
    return {
        "network": {
            "domain_root": "example.com",
            "subdomain_prefixes": {"reality": "a1b2", "tuic": "c3d4", "hy2": "e5f6"},
            "tunnel_mode": "proxy",
            "protocols": [
                {
                    "type": "anytls",
                    "enabled": True,
                    "port": 23244,
                    "auth": {"password": "pwd-anytls"},
                    "reality": {
                        "private_key": "priv",
                        "public_key": "pub",
                        "short_id": "sid",
                    },
                },
                {
                    "type": "tuic",
                    "enabled": True,
                    "port": 9443,
                    "auth": {"uuid": "uuid-1", "password": "pwd-tuic"},
                    "tls": {"cert_path": "/certs/tuic.crt", "key_path": "/certs/tuic.key"},
                },
                {
                    "type": "hysteria2",
                    "enabled": True,
                    "port": 7443,
                    "auth": {"password": "pwd-hy2", "obfs_password": "pwd-obfs"},
                    "tls": {"cert_path": "/certs/hy2.crt", "key_path": "/certs/hy2.key"},
                },
            ],
        },
        "client": {"server_ip": "1.2.3.4", "fingerprint": "chrome"},
        "options": {"target": "both", "format": "json"},
    }


def build_ctx():
    network = NetworkConfig(
        domain_root="example.com",
        subdomain_prefixes={"reality": "a1b2", "tuic": "c3d4", "hy2": "e5f6"},
        tunnel_mode="proxy",
    )
    return BuildContext(
        network=network,
        client=ClientConfig(server_ip="1.2.3.4", fingerprint="chrome"),
        hosts=dict(HOSTS),
        options={},
    )


class TestRegistration(unittest.TestCase):
    def test_provider_registered(self):
        from devconfig_gen.registry import default_registry

        provider = default_registry.get("singbox")
        self.assertIsInstance(provider, SingBoxProvider)
        self.assertEqual(provider.name, "singbox")

    def test_plugin_registry_order(self):
        self.assertEqual(protocol_types(), ("anytls", "tuic", "hysteria2"))
        self.assertIsInstance(get_plugin("hysteria2"), Hysteria2Plugin)
        self.assertIsNone(get_plugin("wireguard"))


class TestSchemaValidation(unittest.TestCase):
    def setUp(self):
        self.provider = SingBoxProvider()

    def _errors(self, context, options=None):
        request = GenerationRequest(context=context, options=options or {})
        return self.provider.validate(request)

    def test_context_must_be_mapping(self):
        errors = self._errors(["not", "a", "mapping"])
        self.assertTrue(any("context must be a mapping" in item for item in errors))

    def test_network_required(self):
        self.assertIn("network is required", self._errors({}))

    def test_domain_root_required(self):
        context = valid_context()
        del context["network"]["domain_root"]
        self.assertTrue(any("domain_root is required" in item for item in self._errors(context)))

    def test_tunnel_mode_enum(self):
        context = valid_context()
        context["network"]["tunnel_mode"] = "carrier-pigeon"
        errors = self._errors(context)
        self.assertTrue(any("tunnel_mode must be one of" in item for item in errors))

    def test_unknown_protocol_type(self):
        context = valid_context()
        context["network"]["protocols"][0]["type"] = "wireguard"
        errors = self._errors(context)
        self.assertTrue(any("type must be one of" in item for item in errors))

    def test_no_enabled_protocol(self):
        context = valid_context()
        for proto in context["network"]["protocols"]:
            proto["enabled"] = False
        self.assertTrue(any("at least one protocol must be enabled" in item for item in self._errors(context)))

    def test_protocol_auth_password_required(self):
        context = valid_context()
        del context["network"]["protocols"][0]["auth"]["password"]
        errors = self._errors(context)
        self.assertTrue(any("password must be a string" in item for item in errors))
        fields = {item.field for item in diagnose_request("singbox", context=context)}
        self.assertIn("network.protocols.0.auth.password", fields)

    def test_tuic_cert_required(self):
        context = valid_context()
        del context["network"]["protocols"][1]["tls"]["cert_path"]
        fields = {item.field for item in diagnose_request("singbox", context=context)}
        self.assertIn("network.protocols.1.tls.cert_path", fields)

    def test_port_range(self):
        context = valid_context()
        context["network"]["protocols"][0]["port"] = 99999
        self.assertTrue(any("port must be between" in item for item in self._errors(context)))

    def test_missing_subdomain_prefix(self):
        context = valid_context()
        del context["network"]["subdomain_prefixes"]["hy2"]
        self.assertTrue(any("hy2 subdomain prefix is required" in item for item in self._errors(context)))

    def test_invalid_target(self):
        context = valid_context()
        context["options"]["target"] = "everything"
        self.assertTrue(any("target must be one of" in item for item in self._errors(context)))

    def test_unknown_custom_rule_bucket(self):
        context = valid_context()
        context["network"]["routing"] = {"custom_rules": {"nope": ["x"]}}
        self.assertTrue(
            any("unknown rule bucket" in item for item in self._errors(context))
        )

    def test_diagnose_uses_dotted_paths(self):
        context = valid_context()
        del context["network"]["protocols"][0]["auth"]["password"]
        diagnostics = diagnose_request("singbox", context=context)
        fields = {item.field for item in diagnostics}
        self.assertIn("network.protocols.0.auth.password", fields)


class TestPlugins(unittest.TestCase):
    def setUp(self):
        self.ctx = build_ctx()

    def test_anytls_builds(self):
        plugin = AnyTlsPlugin()
        cfg = ProtocolConfig(
            type="anytls",
            enabled=True,
            port=23244,
            raw={
                "type": "anytls",
                "auth": {"password": "pwd"},
                "reality": {"private_key": "priv", "public_key": "pub", "short_id": "sid"},
            },
            path="network.protocols.0",
        )
        inbound = plugin.build_server_inbound(cfg, self.ctx)
        self.assertEqual(inbound["type"], "anytls")
        self.assertEqual(inbound["tag"], "anytls-in")
        self.assertEqual(inbound["listen_port"], 23244)
        self.assertEqual(inbound["users"][0]["password"], "pwd")
        self.assertEqual(inbound["tls"]["reality"]["private_key"], "priv")
        self.assertEqual(inbound["tls"]["reality"]["handshake"]["server"], "www.cloudflare.com")

        outbound = plugin.build_client_outbound(cfg, self.ctx)
        self.assertEqual(outbound["server"], HOSTS["reality"])
        self.assertEqual(outbound["tls"]["utls"]["fingerprint"], "chrome")
        self.assertEqual(outbound["tls"]["reality"]["public_key"], "pub")

        link = plugin.build_share_link(cfg, self.ctx)
        self.assertTrue(link.startswith("anytls://pwd@a1b2.example.com:23244?"))
        self.assertIn("pbk=pub", link)
        self.assertTrue(link.endswith("#AnyTLS"))

    def test_tuic_builds(self):
        plugin = TuicPlugin()
        cfg = ProtocolConfig(
            type="tuic",
            enabled=True,
            port=9443,
            raw={
                "type": "tuic",
                "auth": {"uuid": "uuid-1", "password": "pwd"},
                "tls": {"cert_path": "/c/t.crt", "key_path": "/c/t.key"},
            },
            path="network.protocols.1",
        )
        inbound = plugin.build_server_inbound(cfg, self.ctx)
        self.assertEqual(inbound["tag"], "tuic-in")
        self.assertEqual(inbound["users"][0]["uuid"], "uuid-1")
        self.assertEqual(inbound["tls"]["certificate_path"], "/c/t.crt")

        outbound = plugin.build_client_outbound(cfg, self.ctx)
        self.assertEqual(outbound["server"], HOSTS["tuic"])
        self.assertEqual(outbound["udp_relay_mode"], "native")

        link = plugin.build_share_link(cfg, self.ctx)
        self.assertTrue(link.startswith("tuic://uuid-1:pwd@c3d4.example.com:9443?"))
        self.assertTrue(link.endswith("#TUIC"))

    def test_hysteria2_builds_and_defaults(self):
        plugin = Hysteria2Plugin()
        cfg = ProtocolConfig(
            type="hysteria2",
            enabled=True,
            port=None,
            raw={
                "type": "hysteria2",
                "auth": {"password": "pwd", "obfs_password": "obfs"},
                "tls": {"cert_path": "/c/h.crt", "key_path": "/c/h.key"},
            },
            path="network.protocols.2",
        )
        inbound = plugin.build_server_inbound(cfg, self.ctx)
        self.assertEqual(inbound["listen_port"], 7443)
        self.assertEqual(inbound["up_mbps"], 500)
        self.assertEqual(inbound["down_mbps"], 500)
        self.assertEqual(inbound["obfs"], {"type": "salamander", "password": "obfs"})

        outbound = plugin.build_client_outbound(cfg, self.ctx)
        self.assertEqual(outbound["up_mbps"], 50)
        self.assertEqual(outbound["down_mbps"], 200)
        self.assertEqual(outbound["server"], HOSTS["hy2"])

        link = plugin.build_share_link(cfg, self.ctx)
        self.assertTrue(link.startswith("hy2://pwd@e5f6.example.com:7443?"))
        self.assertTrue(link.endswith("#Hysteria2"))

    def test_plugin_validate_reports_messages(self):
        plugin = TuicPlugin()
        cfg = ProtocolConfig(type="tuic", enabled=True, port=None, raw={}, path="network.protocols.0")
        errors = []
        plugin.validate(cfg, errors)
        messages = [item.message for item in errors]
        self.assertTrue(any("uuid must be a string" in item for item in messages))


class TestArtifacts(unittest.TestCase):
    def test_target_server(self):
        context = valid_context()
        context["options"]["target"] = "server"
        result = generate_pipeline("singbox", context=context)
        self.assertEqual([a.name for a in result.artifacts], ["sing-box.server.json"])

    def test_target_client(self):
        context = valid_context()
        context["options"]["target"] = "client"
        result = generate_pipeline("singbox", context=context)
        self.assertEqual(
            [a.name for a in result.artifacts], ["sing-box.client.json", "sing-box-links.txt"]
        )
        self.assertEqual(result.artifacts[1].media_type, "text/plain")

    def test_target_both_and_yaml(self):
        context = valid_context()
        context["options"] = {"target": "both", "format": "yaml"}
        result = generate_pipeline("singbox", context=context)
        self.assertEqual(
            [a.name for a in result.artifacts],
            ["sing-box.server.yaml", "sing-box.client.yaml", "sing-box-links.txt"],
        )
        self.assertEqual(result.artifacts[0].media_type, "application/yaml")

    def test_options_can_come_from_request_options(self):
        context = valid_context()
        del context["options"]
        result = generate_pipeline("singbox", context=context, options={"target": "server"})
        self.assertEqual([a.name for a in result.artifacts], ["sing-box.server.json"])

    def test_server_tunnel_modes(self):
        for mode, expected_tag, outbound_types in (
            ("none", "direct", ["direct"]),
            ("proxy", "warp-out", ["socks", "direct"]),
            ("tun", "warp-out", ["direct", "direct"]),
        ):
            context = valid_context()
            context["network"]["tunnel_mode"] = mode
            context["options"]["target"] = "server"
            result = generate_pipeline("singbox", context=context)
            server = result.artifacts[0].content
            self.assertEqual([item["type"] for item in server["outbounds"]], outbound_types)
            self.assertEqual(server["route"]["final"], expected_tag)

    def test_client_tun_excludes_server_ip(self):
        context = valid_context()
        context["options"]["target"] = "client"
        result = generate_pipeline("singbox", context=context)
        client = result.artifacts[0].content
        tun = client["inbounds"][0]
        self.assertEqual(tun["type"], "tun")
        self.assertIn("1.2.3.4/32", tun["route_exclude_address"])

    def test_links_order_matches_protocol_order(self):
        context = valid_context()
        context["options"]["target"] = "client"
        result = generate_pipeline("singbox", context=context)
        links = result.artifacts[1].content.splitlines()
        self.assertTrue(links[0].startswith("anytls://"))
        self.assertTrue(links[1].startswith("tuic://"))
        self.assertTrue(links[2].startswith("hy2://"))

    def test_persists_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            generate("singbox", GenerationRequest(context=valid_context()), output_dir=directory)
            names = sorted(p.name for p in Path(directory).iterdir())
            self.assertEqual(
                names,
                ["sing-box-links.txt", "sing-box.client.json", "sing-box.server.json"],
            )


class TestDeterminism(unittest.TestCase):
    def test_json_and_yaml_are_byte_stable(self):
        for fmt in ("json", "yaml"):
            context = valid_context()
            context["options"] = {"target": "both", "format": fmt}
            first = generate_pipeline("singbox", context=context)
            second = generate_pipeline("singbox", context=valid_context(), options={"target": "both", "format": fmt})
            for left, right in zip(first.artifacts, second.artifacts):
                self.assertEqual(left.name, right.name)
                self.assertEqual(
                    formats.dumps(left.content, fmt), formats.dumps(right.content, fmt)
                )


class TestRoutingData(unittest.TestCase):
    def test_embedded_rules_load_from_package(self):
        buckets = singbox_route.load_rules({})
        for key in singbox_route.REQUIRED_BUCKETS:
            self.assertIn(key, buckets)
        self.assertTrue(buckets["proxy_exact"])

    def test_custom_rules_extend_embedded(self):
        buckets = singbox_route.load_rules({"custom_rules": {"proxy_exact": ["example.org"]}})
        self.assertIn("example.org", buckets["proxy_exact"])
        self.assertIn("chatgpt.com", buckets["proxy_exact"])

    def test_custom_source_ignores_embedded(self):
        buckets = singbox_route.load_rules(
            {"rules_source": "custom", "custom_rules": {"direct_exact": ["only.example"]}}
        )
        self.assertEqual(buckets["direct_exact"], ["only.example"])
        self.assertEqual(buckets["proxy_exact"], [])

    def test_geoip_can_be_disabled(self):
        network = NetworkConfig(routing={"geoip_cn": False})
        route = singbox_route.build_client_route(network)
        self.assertNotIn("rule_set", route)


class TestCli(unittest.TestCase):
    def test_cli_generates_three_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            input_path = Path(directory) / "singbox.json"
            input_path.write_text(json.dumps(valid_context()), encoding="utf-8")
            outdir = Path(directory) / "out"
            proc = run_cli(
                "generate",
                "--provider",
                "singbox",
                "--input",
                str(input_path),
                "--output-dir",
                str(outdir),
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            names = sorted(p.name for p in outdir.iterdir())
            self.assertEqual(
                names,
                ["sing-box-links.txt", "sing-box.client.json", "sing-box.server.json"],
            )

    def test_cli_validate_reports_invalid(self):
        with tempfile.TemporaryDirectory() as directory:
            input_path = Path(directory) / "bad.json"
            input_path.write_text(json.dumps({"network": {}}), encoding="utf-8")
            proc = run_cli("validate", "--provider", "singbox", "--input", str(input_path))
            self.assertEqual(proc.returncode, 1)
            self.assertIn("invalid:", proc.stderr)


if __name__ == "__main__":
    unittest.main()
