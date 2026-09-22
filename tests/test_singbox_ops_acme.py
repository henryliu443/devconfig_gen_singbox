import unittest

from singbox_ops.adapters.acme.cloudflare_dns01 import CloudflareDNS01ACME
from singbox_ops.adapters.acme.prune import plan_prune, prune_certs
from singbox_ops.core.command import CommandResult
from singbox_ops.core.exceptions import AdapterError
from tests._ops_support import FakeRunner

HOSTS = {"tuic": "c3d4.example.com", "hysteria2": "e5f6.example.com"}
TUIC_CERT = "/etc/sing-box-tuic/certs/tuic.crt"


def openssl_handler(san_host):
    def handler(args, env):
        if "-ext" in args:
            return CommandResult(args, 0, f"X509v3 Subject Alternative Name:\n    DNS:{san_host}\n", "")
        return CommandResult(args, 0, "certificate will not expire\n", "")

    return handler


class ACMETests(unittest.TestCase):
    def test_cert_is_valid_when_unexpired_and_matching(self):
        runner = FakeRunner(
            existing=[TUIC_CERT], handler=openssl_handler("c3d4.example.com")
        )
        acme = CloudflareDNS01ACME(runner=runner, token="t", zone_id="z")
        self.assertTrue(acme.cert_is_valid(TUIC_CERT, "c3d4.example.com"))

    def test_cert_invalid_when_host_mismatch(self):
        runner = FakeRunner(existing=[TUIC_CERT], handler=openssl_handler("other.example.com"))
        acme = CloudflareDNS01ACME(runner=runner, token="t", zone_id="z")
        self.assertFalse(acme.cert_is_valid(TUIC_CERT, "c3d4.example.com"))

    def test_cert_invalid_when_missing(self):
        runner = FakeRunner(handler=openssl_handler("c3d4.example.com"))
        acme = CloudflareDNS01ACME(runner=runner, token="t", zone_id="z")
        self.assertFalse(acme.cert_is_valid(TUIC_CERT, "c3d4.example.com"))

    def test_apply_skips_when_cert_already_valid(self):
        runner = FakeRunner(existing=[TUIC_CERT], handler=openssl_handler("c3d4.example.com"))
        acme = CloudflareDNS01ACME(runner=runner, token="t", zone_id="z")
        result = acme.apply(HOSTS, ["tuic"])
        self.assertEqual(result, {"tuic": (TUIC_CERT, "/etc/sing-box-tuic/certs/tuic.key")})
        issued = [cmd for cmd in runner.commands if cmd[0] == "run" and "--issue" in cmd[1]]
        self.assertEqual(issued, [])

    def test_apply_issues_when_missing(self):
        runner = FakeRunner(handler=openssl_handler("c3d4.example.com"))
        acme = CloudflareDNS01ACME(runner=runner, token="t", zone_id="z")
        acme.apply(HOSTS, ["tuic"])
        issued = [cmd for cmd in runner.commands if cmd[0] == "run" and "--issue" in cmd[1]]
        self.assertEqual(len(issued), 1)
        self.assertIn("--dns", issued[0][1])
        self.assertEqual(issued[0][1][issued[0][1].index("--dns") + 1], "dns_cf")
        # credentials are passed through the environment, not argv
        self.assertEqual(issued[0][2].get("CF_Token"), "t")

    def test_dry_run_returns_paths_without_commands(self):
        runner = FakeRunner(handler=openssl_handler("c3d4.example.com"))
        acme = CloudflareDNS01ACME(runner=runner, token="t", zone_id="z")
        result = acme.apply(HOSTS, ["tuic", "hysteria2"], dry_run=True)
        self.assertEqual(set(result), {"tuic", "hysteria2"})
        self.assertEqual(runner.commands, [])


class PruneTests(unittest.TestCase):
    def _runner(self, entries):
        return FakeRunner(dirs={"/root/.acme.sh": entries})

    def test_plan_keep_and_remove(self):
        runner = self._runner(["a.example.com_ecc", "b.example.com_ecc", "ca", "account.conf"])
        keep, remove = plan_prune(runner, "/root/.acme.sh", ["a.example.com"])
        self.assertEqual(keep, ["a.example.com_ecc"])
        self.assertEqual(remove, ["b.example.com_ecc"])

    def test_refuses_empty_keep(self):
        runner = self._runner(["a.example.com_ecc"])
        with self.assertRaises(AdapterError):
            plan_prune(runner, "/root/.acme.sh", [])

    def test_dry_run_does_not_delete(self):
        runner = self._runner(["a.example.com_ecc", "b.example.com_ecc"])
        result = prune_certs(runner, "/root/.acme.sh", ["a.example.com"], dry_run=True)
        self.assertEqual(result["remove"], ["b.example.com_ecc"])
        self.assertEqual(runner.commands, [])

    def test_apply_deletes_only_stale(self):
        runner = self._runner(["a.example.com_ecc", "b.example.com_ecc"])
        prune_certs(runner, "/root/.acme.sh", ["a.example.com"], dry_run=False)
        runs = [cmd[1] for cmd in runner.commands if cmd[0] == "run"]
        self.assertEqual(runs, [("rm", "-rf", "/root/.acme.sh/b.example.com_ecc")])


if __name__ == "__main__":
    unittest.main()
