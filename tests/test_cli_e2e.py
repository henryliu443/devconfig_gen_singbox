import json
import tempfile
import unittest
from pathlib import Path

from devconfig_gen import __version__, load_file

from _support import EXAMPLES, run_cli

SAMPLE_JSON = str(EXAMPLES / "custom.json")
SAMPLE_YAML = str(EXAMPLES / "custom.yaml")


class TestCliEndToEnd(unittest.TestCase):
    def test_version_matches_package_version(self):
        result = run_cli("--version")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), f"devconfig-gen {__version__}")

    def test_providers_lists_builtins(self):
        result = run_cli("providers")
        self.assertEqual(result.returncode, 0, result.stderr)
        names = result.stdout.split()
        self.assertIn("custom", names)
        self.assertIn("json", names)
        self.assertIn("env", names)

    def test_generate_custom_json_end_to_end(self):
        with tempfile.TemporaryDirectory() as directory:
            result = run_cli(
                "generate",
                "--provider",
                "custom",
                "--input",
                SAMPLE_JSON,
                "--output-dir",
                directory,
                "--format",
                "json",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("generated", result.stdout)
            output = Path(directory) / "custom.json"
            data = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(data["app"]["name"], "checkout-api")
            self.assertEqual(data["app"]["port"], 8080)

    def test_generate_custom_yaml_end_to_end(self):
        with tempfile.TemporaryDirectory() as directory:
            result = run_cli(
                "generate",
                "--provider",
                "custom",
                "--input",
                SAMPLE_YAML,
                "--output-dir",
                directory,
                "--format",
                "yaml",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            output = Path(directory) / "custom.yaml"
            data = load_file(output)
            self.assertEqual(data["app"]["environment"], "production")

    def test_generate_infers_format_from_name(self):
        with tempfile.TemporaryDirectory() as directory:
            result = run_cli(
                "generate",
                "--provider",
                "custom",
                "--input",
                SAMPLE_YAML,
                "--output-dir",
                directory,
                "--name",
                "renamed.yaml",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((Path(directory) / "renamed.yaml").exists())

    def test_validate_valid_input_exits_zero(self):
        result = run_cli("validate", "--provider", "custom", "--input", SAMPLE_YAML)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("valid", result.stdout)

    def test_validate_invalid_input_exits_one_with_messages(self):
        with tempfile.TemporaryDirectory() as directory:
            bad = Path(directory) / "bad.yaml"
            bad.write_text("variables: {}\n", encoding="utf-8")
            result = run_cli("validate", "--provider", "env", "--input", str(bad))
            self.assertEqual(result.returncode, 1)
            self.assertIn("variables must not be empty", result.stderr)

    def test_unknown_provider_exits_two(self):
        result = run_cli(
            "generate",
            "--provider",
            "missing",
            "--input",
            SAMPLE_JSON,
            "--output-dir",
            "out",
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("unknown provider", result.stderr)

    def test_missing_input_file_exits_two(self):
        with tempfile.TemporaryDirectory() as directory:
            result = run_cli(
                "generate",
                "--provider",
                "custom",
                "--input",
                str(Path(directory) / "absent.json"),
                "--output-dir",
                directory,
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("error:", result.stderr)

    def test_schema_prints_json_steps(self):
        result = run_cli("schema", "--provider", "custom")
        self.assertEqual(result.returncode, 0, result.stderr)
        steps = json.loads(result.stdout)
        self.assertEqual([step["id"] for step in steps], ["document"])
        field_names = [field["name"] for step in steps for field in step["fields"]]
        self.assertIn("document", field_names)

    def test_validate_json_reports_structured_diagnostics(self):
        with tempfile.TemporaryDirectory() as directory:
            bad = Path(directory) / "bad.yaml"
            bad.write_text("variables: {}\n", encoding="utf-8")
            result = run_cli(
                "validate", "--provider", "env", "--input", str(bad), "--json"
            )
            self.assertEqual(result.returncode, 1)
            diagnostics = json.loads(result.stdout)
            self.assertEqual(diagnostics[0]["field"], "variables")
            self.assertEqual(diagnostics[0]["severity"], "error")

    def test_validate_json_on_valid_input_is_empty(self):
        result = run_cli(
            "validate", "--provider", "custom", "--input", SAMPLE_YAML, "--json"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), [])

    def test_unknown_provider_schema_exits_two(self):
        result = run_cli("schema", "--provider", "missing")
        self.assertEqual(result.returncode, 2)
        self.assertIn("unknown provider", result.stderr)

    def test_generate_multi_input_with_set_overrides(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory) / "base.yaml"
            override = Path(directory) / "prod.json"
            base.write_text(
                "app:\n  name: web\n  port: 80\n  labels:\n    team: core\n",
                encoding="utf-8",
            )
            override.write_text(
                json.dumps({"app": {"port": 9090, "labels": {"tier": "edge"}}}),
                encoding="utf-8",
            )
            out = Path(directory) / "out"
            result = run_cli(
                "generate",
                "--provider",
                "custom",
                "--input",
                str(base),
                "--input",
                str(override),
                "--set",
                "app.environment=production",
                "--output-dir",
                str(out),
                "--format",
                "json",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            data = json.loads((out / "custom.json").read_text(encoding="utf-8"))
            self.assertEqual(data["app"]["port"], 9090)
            self.assertEqual(data["app"]["environment"], "production")
            self.assertEqual(data["app"]["labels"], {"team": "core", "tier": "edge"})

    def test_generate_rejects_malformed_set(self):
        result = run_cli(
            "generate",
            "--provider",
            "custom",
            "--input",
            SAMPLE_JSON,
            "--set",
            "noequals",
            "--output-dir",
            "out",
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("KEY=VALUE", result.stderr)

    def test_set_coerces_json_values(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory) / "base.json"
            base.write_text('{"a": 1}', encoding="utf-8")
            out = Path(directory) / "out"
            result = run_cli(
                "generate",
                "--provider",
                "json",
                "--input",
                str(base),
                "--set",
                "flag=true",
                "--set",
                "count=42",
                "--set",
                "nothing=null",
                "--set",
                "label=web",
                "--output-dir",
                str(out),
                "--format",
                "json",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            data = json.loads((out / "config.json").read_text(encoding="utf-8"))
            self.assertIs(data["flag"], True)
            self.assertEqual(data["count"], 42)
            self.assertIsNone(data["nothing"])
            self.assertEqual(data["label"], "web")

    def test_validate_multi_input(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory) / "base.yaml"
            override = Path(directory) / "override.yaml"
            base.write_text("app:\n  name: web\n  port: 80\n", encoding="utf-8")
            override.write_text("app:\n  port: 9090\n", encoding="utf-8")
            result = run_cli(
                "validate",
                "--provider",
                "custom",
                "--input",
                str(base),
                "--input",
                str(override),
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("valid", result.stdout)

    def test_generate_env_provider_end_to_end(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "vars.yaml"
            source.write_text(
                "database:\n  host: localhost\n  port: 5432\ndebug: true\n",
                encoding="utf-8",
            )
            out = Path(directory) / "out"
            result = run_cli(
                "generate",
                "--provider",
                "env",
                "--input",
                str(source),
                "--output-dir",
                str(out),
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            content = (out / ".env").read_text(encoding="utf-8")
            self.assertIn("DATABASE_HOST=localhost", content)
            self.assertIn("DEBUG=true", content)


if __name__ == "__main__":
    unittest.main()
