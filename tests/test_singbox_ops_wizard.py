import io
import unittest

from singbox_ops.cli import interactive_plan
from singbox_ops.core.ui import UI


def run_wizard(inputs):
    reader = io.StringIO(inputs)
    writer = io.StringIO()
    return interactive_plan(reader=reader, writer=writer, ui=UI(writer))


class WizardTests(unittest.TestCase):
    def test_dns_is_always_cloudflare_and_creds_are_collected(self):
        inputs = (
            "example.com\n"   # domain
            "\n"              # protocols (default)
            "none\n"          # tunnel mode
            "\n"              # server ip (auto)
            "tok123\n"        # CF token
            "zone456\n"       # CF zone
            "y\n"             # acme
            "y\n"             # runtime adapters
            "\n\n\n"          # output paths
        )
        plan, env = run_wizard(inputs)
        self.assertEqual(plan["domain_root"], "example.com")
        self.assertEqual(plan["tunnel_mode"], "none")
        # DNS is mandatory, never optional
        self.assertEqual(plan["adapters"]["dns"], "cloudflare")
        self.assertEqual(env["CF_Token"], "tok123")
        self.assertEqual(env["CF_Zone_ID"], "zone456")
        self.assertEqual(plan["adapters"]["acme"], "cloudflare-dns01")

    def test_acme_can_be_skipped_but_dns_cannot(self):
        inputs = (
            "example.com\n\nnone\n\n"
            "tok\nzone\n"
            "n\n"             # no acme
            "y\n"             # runtime
            "\n\n\n"
        )
        plan, env = run_wizard(inputs)
        self.assertEqual(plan["adapters"]["dns"], "cloudflare")
        self.assertIsNone(plan["adapters"]["acme"])
        self.assertEqual(plan["adapters"]["runtime"]["auto_update"], "auto-update")

    def test_domain_is_required(self):
        inputs = (
            "\n"              # empty domain -> rejected
            "example.com\n"
            "\n"              # protocols
            "\n"              # tunnel (default proxy)
            "\n"              # ip
            "tok\nzone\n"
            "n\nn\n"          # no acme, no runtime
            "\n\n\n"
        )
        plan, env = run_wizard(inputs)
        self.assertEqual(plan["domain_root"], "example.com")
        self.assertEqual(plan["tunnel_mode"], "proxy")
        self.assertIsNone(plan["adapters"]["runtime"]["systemd"])


if __name__ == "__main__":
    unittest.main()
