import json
import unittest

from devconfig_gen import (
    Diagnostic,
    ProviderField,
    ProviderStep,
    describe_provider,
    diagnose_request,
)
from devconfig_gen.providers import CustomProvider, EnvProvider, JsonProvider, SingBoxProvider


class TestProviderMetadata(unittest.TestCase):
    def test_describe_provider_returns_steps(self):
        steps = describe_provider("custom")
        self.assertTrue(all(isinstance(step, ProviderStep) for step in steps))
        step_ids = [step.id for step in steps]
        self.assertEqual(step_ids, ["document"])

    def test_provider_fields_expose_constraints(self):
        fields = {
            field.name: field
            for step in describe_provider("env")
            for field in step.fields
        }
        variables = fields["variables"]
        self.assertEqual(variables.type, "mapping")
        self.assertTrue(variables.required)

    def test_step_and_field_serialize_to_json_ready_dicts(self):
        step = ProviderStep(
            id="s",
            title="S",
            description="d",
            fields=(ProviderField("x", type="string", required=True, default="a"),),
        )
        data = step.as_dict()
        self.assertEqual(data["id"], "s")
        self.assertEqual(data["fields"][0]["name"], "x")
        self.assertTrue(data["fields"][0]["required"])
        json.dumps(data)

    def test_field_title_defaults_to_name(self):
        field = ProviderField("app.port")
        self.assertEqual(field.as_dict()["title"], "app.port")

    def test_i18n_metadata_round_trips(self):
        field = ProviderField(
            "app.port",
            title="Port",
            description="TCP port.",
            i18n={"zh": {"title": "端口", "description": "TCP 端口。"}},
        )
        step = ProviderStep(
            id="runtime",
            title="Runtime",
            description="Where it runs.",
            fields=(field,),
            i18n={"zh": {"title": "运行时", "description": "运行位置。"}},
        )
        data = step.as_dict()
        self.assertEqual(data["i18n"]["zh"]["title"], "运行时")
        self.assertEqual(data["fields"][0]["i18n"]["zh"]["title"], "端口")
        json.dumps(data)

    def test_i18n_omitted_when_empty(self):
        step = ProviderStep(id="s", title="S")
        self.assertNotIn("i18n", step.as_dict())
        self.assertNotIn("i18n", ProviderField("x").as_dict())

    def test_builtin_providers_expose_chinese_metadata(self):
        for provider in ("custom", "env", "json"):
            for step in describe_provider(provider):
                self.assertIn("zh", step.i18n, f"{provider} step {step.id}")
                self.assertIn("title", step.i18n["zh"])
                for field in step.fields:
                    self.assertIn("zh", field.i18n, f"{provider} field {field.name}")
                    self.assertIn("title", field.i18n["zh"])
                    self.assertIn("description", field.i18n["zh"])

    def test_json_provider_has_schema(self):
        steps = JsonProvider().describe_schema()
        self.assertEqual(steps[0].id, "document")

    def test_diagnose_request_uses_structured_provider_output(self):
        diagnostics = diagnose_request("env", context={})
        self.assertTrue(all(isinstance(item, Diagnostic) for item in diagnostics))
        fields = {item.field for item in diagnostics}
        self.assertIn("variables", fields)
        self.assertEqual(diagnostics[0].severity, "error")

    def test_diagnose_request_falls_back_to_messages(self):
        class Minimal:
            name = "minimal"

            def validate(self, request):
                return ("something is wrong",)

            def generate(self, request):  # pragma: no cover - not used here
                raise NotImplementedError

        from devconfig_gen.registry import ProviderRegistry

        registry = ProviderRegistry((Minimal(),))
        diagnostics = diagnose_request("minimal", registry=registry)
        self.assertEqual(diagnostics[0].message, "something is wrong")
        self.assertEqual(diagnostics[0].field, "")

    def test_builtin_providers_registered(self):
        from devconfig_gen.registry import default_registry

        self.assertEqual(default_registry.names(), ("custom", "env", "json", "singbox"))
        self.assertIsInstance(default_registry.get("custom"), CustomProvider)
        self.assertIsInstance(default_registry.get("json"), JsonProvider)
        self.assertIsInstance(default_registry.get("env"), EnvProvider)
        self.assertIsInstance(default_registry.get("singbox"), SingBoxProvider)


if __name__ == "__main__":
    unittest.main()
