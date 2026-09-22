import io
import unittest

from singbox_ops.cli import interactive_plan
from singbox_ops.core.ui import UI


def run_wizard(inputs):
    reader = io.StringIO(inputs)
    writer = io.StringIO()
    return interactive_plan(reader=reader, writer=writer, ui=UI(writer))


class WizardTests(unittest.TestCase):
    def test_collects_cf_credentials_when_dns_enabled(self):
        inputs = (
            "example.com\n"   # domain
            "\n"              # protocols (default)
            "none\n"          # tunnel mode
            "\n"              # server ip (auto)
            "y\n"             # use cloudflare dns
            "y\n"             # use acme
            "tok123\n"        # CF token
            "zone456\n"       # CF zone
            "y\n"             # runtime adapters
            "\n\n\n"          # output paths (defaults)
        )
        plan, env = run_wizard(inputs)
        self.assertEqual(plan["domain_root"], "example.com")
        self.assertEqual(plan["tunnel_mode"], "none")
        self.assertEqual(plan["adapters"]["dns"], "cloudflare")
        self.assertEqual(env["CF_Token"], "tok123")
        self.assertEqual(env["CF_Zone_ID"], "zone456")

    def test_skips_cf_credentials_when_no_dns_and_no_acme(self):
        inputs = (
            "example.com\n\nnone\n\n"
            "n\nn\n"
            "y\n"
            "\n\n\n"
        )
        plan, env = run_wizard(inputs)
        self.assertEqual(env, {})
        self.assertIsNone(plan["adapters"]["dns"])
        self.assertIsNone(plan["adapters"]["acme"])
        self.assertEqual(plan["adapters"]["runtime"]["auto_update"], "auto-update")

    def test_domain_is_required(self):
        inputs = (
            "\n"              # empty domain -> rejected
            "example.com\n"
            "\n"              # protocols
            "\n"              # tunnel (default proxy)
            "\n"              # ip
            "n\nn\n"          # no dns, no acme
            "n\n"             # no runtime
            "\n\n\n"
        )
        plan, env = run_wizard(inputs)
        self.assertEqual(plan["domain_root"], "example.com")
        self.assertEqual(plan["tunnel_mode"], "proxy")
        self.assertIsNone(plan["adapters"]["runtime"]["systemd"])


if __name__ == "__main__":
    unittest.main()
