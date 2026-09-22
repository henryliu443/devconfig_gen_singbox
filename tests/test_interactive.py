import io
import tempfile
import unittest
from pathlib import Path

from devconfig_gen import Diagnostic, GeneratedArtifact, GenerationResult
from devconfig_gen.interactive import (
    _get_dotted_path,
    _set_dotted_path,
    prompt_field,
    run_interactive_wizard,
)
from devconfig_gen.models import ProviderField, ProviderStep
from devconfig_gen.registry import ProviderRegistry


class _StrictProvider:
    """A minimal validating provider used to exercise the retry loop."""

    name = "strict"

    steps = (
        ProviderStep(
            id="main",
            title="Main",
            fields=(
                ProviderField("app.name", type="string", required=True),
                ProviderField("app.path", type="string", required=True),
            ),
        ),
    )

    def describe_schema(self):
        return self.steps

    def diagnose(self, request):
        diagnostics = []
        if not _get_dotted_path(request.context, "app.name"):
            diagnostics.append(Diagnostic("app.name", "missing required field: 'app.name'"))
        path = _get_dotted_path(request.context, "app.path")
        if not path or not str(path).startswith("/"):
            diagnostics.append(Diagnostic("app.path", "app.path must start with '/'"))
        return tuple(diagnostics)

    def validate(self, request):
        return tuple(item.message for item in self.diagnose(request))

    def generate(self, request):
        errors = self.validate(request)
        if errors:
            raise ValueError("; ".join(errors))
        return GenerationResult(
            provider=self.name,
            artifacts=(
                GeneratedArtifact(name="strict.json", content=dict(request.context)),
            ),
        )


class TestInteractiveWizard(unittest.TestCase):
    def test_dotted_path_helpers(self):
        data = {}
        _set_dotted_path(data, "app.name", "my-api")
        _set_dotted_path(data, "app.networking.port", 8080)
        self.assertEqual(data["app"]["name"], "my-api")
        self.assertEqual(data["app"]["networking"]["port"], 8080)

        self.assertEqual(_get_dotted_path(data, "app.name"), "my-api")
        self.assertEqual(_get_dotted_path(data, "app.networking.port"), 8080)
        self.assertIsNone(_get_dotted_path(data, "app.missing"))

    def test_prompt_field_string_with_default(self):
        field = ProviderField("app.name", type="string", default="default-app")
        reader = io.StringIO("\n")  # press enter
        writer = io.StringIO()
        val = prompt_field(field, None, reader, writer)
        self.assertEqual(val, "default-app")

    def test_prompt_field_integer_bounds(self):
        field = ProviderField("app.port", type="integer", minimum=1, maximum=65535, default=8080)
        # First enters invalid string, then out of bounds, then valid port
        reader = io.StringIO("not_a_num\n99999\n8081\n")
        writer = io.StringIO()
        val = prompt_field(field, None, reader, writer)
        self.assertEqual(val, 8081)
        output = writer.getvalue()
        self.assertIn("Expected integer", output)
        self.assertIn("Value must be <=", output)

    def test_prompt_field_choices(self):
        field = ProviderField(
            "app.env",
            type="string",
            choices=("dev", "staging", "production"),
            default="dev",
        )
        # Select choice 2 (staging)
        reader = io.StringIO("2\n")
        writer = io.StringIO()
        val = prompt_field(field, None, reader, writer)
        self.assertEqual(val, "staging")

    def test_prompt_field_boolean(self):
        field = ProviderField("app.tls", type="boolean", default=False)
        reader = io.StringIO("y\n")
        writer = io.StringIO()
        val = prompt_field(field, None, reader, writer)
        self.assertTrue(val)

    def test_prompt_field_document_from_file(self):
        with tempfile.NamedTemporaryFile("w+", suffix=".json", delete=False) as f:
            f.write('{"key": "value_from_file"}')
            f.flush()
            temp_path = f.name
        try:
            field = ProviderField("document", type="document")
            reader = io.StringIO(f"{temp_path}\n")
            writer = io.StringIO()
            val = prompt_field(field, None, reader, writer)
            self.assertEqual(val, {"key": "value_from_file"})
            self.assertIn("Loaded document", writer.getvalue())
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_prompt_field_document_fallback_to_mapping(self):
        field = ProviderField("document", type="document")
        # Enter empty line for file path, then key=value, then empty line to finish
        reader = io.StringIO("\napp=web\n\n")
        writer = io.StringIO()
        val = prompt_field(field, None, reader, writer)
        self.assertEqual(val, {"app": "web"})

    def test_prompt_field_tree_from_file(self):
        with tempfile.NamedTemporaryFile("w+", suffix=".json", delete=False) as f:
            f.write('{"app": {"nested": {"deep": [1, 2, 3]}}}')
            f.flush()
            temp_path = f.name
        try:
            field = ProviderField("document", type="tree")
            reader = io.StringIO(f"{temp_path}\n")
            writer = io.StringIO()
            val = prompt_field(field, None, reader, writer)
            self.assertEqual(val, {"app": {"nested": {"deep": [1, 2, 3]}}})
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_run_interactive_wizard_full_flow(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # The custom provider has a single 'document' tree field. Skip the
            # file path and enter key=value pairs instead.
            inputs = "\n".join([
                "",          # no file path -> key=value entry
                "name=web",  # document entry
                "port=8080",
                "",          # finish the mapping
            ]) + "\n"

            reader = io.StringIO(inputs)
            writer = io.StringIO()

            code = run_interactive_wizard(
                "custom",
                output_dir=tmpdir,
                output_format="yaml",
                reader=reader,
                writer=writer,
            )
            self.assertEqual(code, 0, writer.getvalue())

            out_file = Path(tmpdir) / "custom.yaml"
            self.assertTrue(out_file.exists())
            content = out_file.read_text(encoding="utf-8")
            self.assertIn("name: web", content)

    def test_run_interactive_wizard_unknown_provider(self):
        reader = io.StringIO("")
        writer = io.StringIO()
        code = run_interactive_wizard("unknown_provider", reader=reader, writer=writer)
        self.assertEqual(code, 1)
        self.assertIn("Error: unknown provider", writer.getvalue())

    def test_wizard_preserves_answers_when_retrying(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # 'healthz' fails validation (missing leading slash), so the wizard
            # offers to re-run. The second pass keeps 'auth-svc' pre-filled and
            # only corrects the path.
            inputs = "\n".join([
                "auth-svc",  # app.name
                "healthz",   # app.path INVALID
                "y",         # re-run to correct
                "",          # app.name (pre-filled)
                "/healthz",  # app.path corrected
            ]) + "\n"

            writer = io.StringIO()
            code = run_interactive_wizard(
                "strict",
                output_dir=tmpdir,
                output_format="json",
                registry=ProviderRegistry((_StrictProvider(),)),
                reader=io.StringIO(inputs),
                writer=writer,
            )
            self.assertEqual(code, 0, writer.getvalue())
            self.assertIn("pre-filled", writer.getvalue())
            content = (Path(tmpdir) / "strict.json").read_text(encoding="utf-8")
            self.assertIn("auth-svc", content)

    def test_wizard_retry_can_be_declined(self):
        inputs = "auth-svc\nhealthz\nn\n"
        writer = io.StringIO()
        with tempfile.TemporaryDirectory() as tmpdir:
            code = run_interactive_wizard(
                "strict",
                output_dir=tmpdir,
                output_format="json",
                registry=ProviderRegistry((_StrictProvider(),)),
                reader=io.StringIO(inputs),
                writer=writer,
            )
        self.assertEqual(code, 1)
        self.assertIn("Aborted", writer.getvalue())

    def test_wizard_aborts_cleanly_on_end_of_input(self):
        writer = io.StringIO()
        code = run_interactive_wizard(
            "strict",
            output_format="json",
            registry=ProviderRegistry((_StrictProvider(),)),
            reader=io.StringIO(""),  # immediate EOF
            writer=writer,
        )
        self.assertEqual(code, 1)
        self.assertIn("Input ended", writer.getvalue())


if __name__ == "__main__":
    unittest.main()
