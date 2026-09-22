import unittest

from singbox_ops.adapters.secrets.python_secrets import PythonSecrets
from singbox_ops.adapters.secrets.singbox_subprocess import SingboxSubprocessSecrets
from singbox_ops.adapters.secrets.static import StaticSecrets
from singbox_ops.core.command import CommandResult
from singbox_ops.core.exceptions import AdapterError
from singbox_ops.core.plan import DeployPlan
from tests._ops_support import FakeRunner, static_secrets


def plan_for(protocols=("anytls", "tuic", "hysteria2")):
    return DeployPlan.from_mapping({"domain_root": "example.com", "protocols": list(protocols)})


class PythonSecretsTests(unittest.TestCase):
    def test_generates_all_credentials_and_prefixes(self):
        generated = PythonSecrets().generate(plan_for())
        self.assertEqual(set(generated.credentials), {"anytls", "tuic", "hysteria2"})
        self.assertEqual(set(generated.subdomain_prefixes), {"reality", "tuic", "hy2"})
        anytls = generated.credentials["anytls"]
        self.assertTrue(anytls["private_key"])
        self.assertTrue(anytls["public_key"])
        self.assertNotEqual(anytls["private_key"], anytls["public_key"])
        self.assertTrue(generated.credentials["tuic"]["uuid"])
        self.assertTrue(generated.credentials["hysteria2"]["obfs_password"])
        # prefixes must be unique
        self.assertEqual(len(set(generated.subdomain_prefixes.values())), 3)

    def test_plan_prefixes_win(self):
        plan = plan_for(("anytls",))
        plan = DeployPlan.from_mapping(
            {"domain_root": "example.com", "protocols": ["anytls"], "subdomain_prefixes": {"reality": "deadbeef"}}
        )
        generated = PythonSecrets().generate(plan)
        self.assertEqual(generated.subdomain_prefixes, {"reality": "deadbeef"})

    def test_only_enabled_protocols(self):
        generated = PythonSecrets().generate(plan_for(("tuic",)))
        self.assertEqual(set(generated.credentials), {"tuic"})


class StaticSecretsTests(unittest.TestCase):
    def test_accepts_full_document(self):
        generated = StaticSecrets(static_secrets()).generate(plan_for())
        self.assertEqual(generated.credentials["tuic"]["password"], "pwd-tuic")
        self.assertEqual(generated.subdomain_prefixes["hy2"], "e5f6")

    def test_missing_credentials_raises(self):
        with self.assertRaises(AdapterError):
            StaticSecrets({"credentials": {"tuic": {}}, "subdomain_prefixes": {"tuic": "x"}}).generate(
                plan_for(("anytls", "tuic"))
            )


class SingboxSubprocessSecretsTests(unittest.TestCase):
    def test_prefers_binary_output(self):
        def handler(args, env):
            if args[1:3] == ["generate", "uuid"]:
                return CommandResult(args, 0, "11111111-2222-3333-4444-555555555555\n", "")
            if args[1:3] == ["generate", "reality-keypair"]:
                return CommandResult(args, 0, "PrivateKey: PRIVKEY\nPublicKey: PUBKEY\n", "")
            return CommandResult(args, 1, "", "unknown")

        runner = FakeRunner(handler=handler)
        generated = SingboxSubprocessSecrets(runner=runner).generate(plan_for())
        self.assertEqual(generated.credentials["tuic"]["uuid"], "11111111-2222-3333-4444-555555555555")
        self.assertEqual(generated.credentials["anytls"]["private_key"], "PRIVKEY")
        self.assertEqual(generated.credentials["anytls"]["public_key"], "PUBKEY")

    def test_falls_back_when_binary_missing(self):
        runner = FakeRunner(handler=lambda args, env: CommandResult(args, 127, "", "not found"))
        generated = SingboxSubprocessSecrets(runner=runner).generate(plan_for())
        self.assertTrue(generated.credentials["tuic"]["uuid"])
        self.assertTrue(generated.credentials["anytls"]["private_key"])


if __name__ == "__main__":
    unittest.main()
