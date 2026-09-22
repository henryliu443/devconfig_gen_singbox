import io
import unittest

from singbox_ops.cli import interactive_plan
from singbox_ops.core.ui import UI


def run_wizard(inputs):
    reader = io.StringIO(inputs)
    writer = io.StringIO()
    return interactive_plan(reader=reader, writer=writer, ui=UI(writer))


class WizardTests(unittest.TestCase):
    def test_collects_dns_creds_and_protocol_params(self):
        inputs = (
            "example.com\n"          # domain
            "\n"                     # protocols (default: all)
            "none\n"                 # tunnel mode
            "\n"                     # server ip (auto)
            "react.dev\n"            # anytls decoy server
            "443\n"                  # anytls decoy port
            "https://react.dev\n"    # hy2 masquerade
            "tok123\n"               # CF token
            "zone456\n"              # CF zone
            "y\n"                    # acme
            "y\n"                    # runtime
            "\n\n\n"                 # outputs
        )
        plan, env = run_wizard(inputs)
        self.assertEqual(plan["domain_root"], "example.com")
        self.assertEqual(plan["adapters"]["dns"], "cloudflare")
        self.assertEqual(env["CF_Token"], "tok123")
        self.assertEqual(plan["protocol_params"]["anytls"]["decoy_server"], "react.dev")
        self.assertEqual(plan["protocol_params"]["anytls"]["decoy_port"], "443")
        self.assertEqual(plan["protocol_params"]["hysteria2"]["masquerade"], "https://react.dev")

    def test_acme_can_be_skipped_but_dns_cannot(self):
        inputs = (
            "example.com\n\nnone\n\n"
            "\n443\n\n"              # decoy defaults, masquerade default
            "tok\nzone\n"
            "n\n"                    # no acme
            "y\n"                    # runtime
            "\n\n\n"
        )
        plan, env = run_wizard(inputs)
        self.assertEqual(plan["adapters"]["dns"], "cloudflare")
        self.assertIsNone(plan["adapters"]["acme"])
        self.assertEqual(plan["protocol_params"]["anytls"]["decoy_server"], "www.cloudflare.com")

    def test_domain_is_required(self):
        inputs = (
            "\n"                     # empty domain -> rejected
            "example.com\n"
            "\n"                     # protocols
            "\n"                     # tunnel (default proxy)
            "\n"                     # ip
            "\n443\n\n"              # protocol params defaults
            "tok\nzone\n"
            "n\nn\n"                 # no acme, no runtime
            "\n\n\n"
        )
        plan, env = run_wizard(inputs)
        self.assertEqual(plan["domain_root"], "example.com")
        self.assertEqual(plan["tunnel_mode"], "proxy")
        self.assertIsNone(plan["adapters"]["runtime"]["systemd"])


if __name__ == "__main__":
    unittest.main()
