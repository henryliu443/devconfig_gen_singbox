import json
import unittest

from tests._ops_support import EXAMPLES, run_ops_cli
from tests._support import run_cli

PLAN = str(EXAMPLES / "singbox-deploy.yaml")


class SingleCliNameTests(unittest.TestCase):
    """There is exactly one command, named after the PyPI distribution."""

    def test_ops_subcommands_are_grafted_onto_the_single_cli(self):
        result = run_cli("--help")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("devconfig_gen_singbox", result.stdout)
        for name in ("generate", "init", "ui", "context", "plan", "deploy", "redeploy", "destroy", "certs"):
            self.assertIn(name, result.stdout)
        self.assertNotIn("singbox-ops", result.stdout)


class OpsCliTests(unittest.TestCase):
    def test_context_command_prints_valid_provider_input(self):
        result = run_ops_cli("context", "--plan", PLAN, "--format", "json")
        self.assertEqual(result.returncode, 0, result.stderr)
        context = json.loads(result.stdout)
        self.assertEqual(context["network"]["domain_root"], "example.com")
        self.assertEqual(len(context["network"]["protocols"]), 3)

    def test_deploy_dry_run_reports_steps(self):
        result = run_ops_cli("deploy", "--plan", PLAN, "--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertTrue(report["dry_run"])
        self.assertIn("generate", report["steps"])
        self.assertEqual(report["server_ip"], "198.51.100.1")

    def test_invalid_plan_reports_error(self):
        result = run_ops_cli("context", "--plan", str(EXAMPLES / "missing-plan.yaml"))
        self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
