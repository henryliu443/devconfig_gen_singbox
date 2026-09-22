import unittest

from singbox_ops.adapters.acme.cloudflare_dns01 import CloudflareDNS01ACME
from singbox_ops.core.command import CommandResult
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


if __name__ == "__main__":
    unittest.main()
