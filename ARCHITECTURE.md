# Architecture

This document describes how DevConfig-Gen is put together and the decisions
behind its boundaries.

## Goal

Turn a structured input document (JSON or YAML) into a validated, normalized
structured configuration document (JSON or YAML), driven by an extensible
provider. The engine is provider-neutral; providers own schemas,
normalization, and validation.

## Layers

```text
CLI (`providers`/`schema`/`generate`/`validate`)
        |
        v
engine.py  ---- build_request / generate_pipeline / generate_from_file
  |            diagnose_request / describe_provider
  |            (the single shared pipeline, with multi-source deep_merge)
  v
ProviderRegistry -> ConfigProvider (`custom`, `json`, `env`, `singbox`)
  |
  v
formats.py  (JSON/YAML load, dump, detection, media types, deep_merge, coerce_scalar)
validation.py (path-aware Diagnostic helpers)
```

### Data contracts (`models.py`)

- `GenerationRequest` — immutable `context` (the input document) plus
  `options` (provider configuration such as `format` and `name`).
- `Diagnostic` — a structured validation result: `field` (dotted path),
  `message` (rendered text), and `severity` (`error` / `warning`).
- `GeneratedArtifact` — an output file: `name`, `content` (a data structure or
  a pre-rendered string), and `media_type`.
- `GenerationResult` — the provider name plus the artifacts it produced.
- `ProviderField` / `ProviderStep` — declarative field metadata for
  documentation and the `schema` command. Both accept an optional `i18n`
  mapping (`{"zh": {"title": ..., "description": ...}}`) so clients can render
  localized labels while the canonical English strings stay the default.
- `ConfigProvider` — the protocol providers implement.

### Engine (`engine.py`)

`generate()` is the single execution point: it looks up the provider, runs
`validate`, runs `generate`, and optionally persists artifacts. Higher-level
helpers (`generate_pipeline`, `generate_from_file`, `validate_request`,
`diagnose_request`, `describe_provider`) only build a request and delegate. The
CLI calls these helpers and adds no logic.

`build_request()` assembles the request context from an in-memory mapping,
multiple input files (deep-merged left to right via `formats.deep_merge`), and
dotted-path `overrides` applied last.

Persistence maps `media_type` to a serializer (`application/json`,
`application/yaml`); pre-rendered string artifacts such as `.env` are written
verbatim. Artifact names that escape the output directory are refused.

### Multi-source data pipeline (`deep_merge` and overrides)

When multiple input documents are provided to `build_request` or `generate_pipeline`:

1. Each input path is read and parsed via `formats.load_file` with automatic
   JSON/YAML format detection.
2. Documents are merged left to right using `formats.deep_merge`:
   - Nested mappings are merged recursively (nested keys combine).
   - Non-mapping values (scalars, lists) overwrite prior values.
   - Neither input dictionary is mutated.
3. Dotted-path overrides (e.g. `--set app.port=9090`) are coerced via
   `formats.coerce_scalar` (preserving booleans, numbers, and null) and applied
   last via `_set_nested`, guaranteeing command-line precedence.

### Formats (`formats.py`)

- `loads` / `load_file` / `load_data` for input;
- `dumps` / `dump_data` / `dump_file` for output;
- `detect_format` / `resolve_format` for format selection;
- `media_type_for` / `format_from_media_type` for artifact metadata;
- `deep_merge` for multi-source input merging;
- `coerce_scalar` to interpret CLI/`--set` strings as JSON literals.

JSON uses the standard library. YAML uses PyYAML when installed and otherwise
a bundled subset parser/serializer with no external dependencies. See the
README for the exact support boundary. Both JSON and YAML preserve insertion
order so the provider's semantic field order is deterministic across formats.

### Validation (`validation.py`)

Small primitives (`expect_string`, `expect_integer`, `expect_enum`,
`expect_mapping`, `expect_string_mapping`) collect every problem in one pass as
`Diagnostic` objects instead of raising on the first failure. Messages use the
leaf field name (for example `port must be between 1 and 65535, got 99999`)
while `Diagnostic.field` keeps the full dotted path for tooling.

### Providers (`providers/`)

- `custom` — a schema-free provider for arbitrary documents. It accepts any
  nesting of mappings, sequences, and scalars with no required fields, and the
  studio renders its `tree` field as a recursive editor where nodes can be
  added, removed, retyped, or cleared at any depth.
- `json` — a pass-through provider that normalizes/re-serializes an arbitrary
  document. It proves the pipeline without imposing a schema.
- `env` — flattens a nested mapping into `UPPER_SNAKE_CASE` `.env` text,
  demonstrating a non-JSON output format and a provider-driven schema step.
- `singbox` — a rich-domain provider (child fork only) that turns a structured
  context into sing-box `server` / `client` configs plus a share-link list. It
  follows `PROVIDER_STANDARD.md`: variant detail lives in
  `providers/singbox/plugins/<variant>.py` (one module per protocol), the
  neutral layers (`provider.py` / `schema.py` / `route.py`) never mention a
  protocol field name, and credentials/subdomain prefixes are explicit inputs
  (no environment reads, no subprocesses, no state).

  `providers/singbox/data/rules.json` is the first provider data file. It is
  loaded with `Path(__file__).parent / "data" / "rules.json"` so the provider
  works from an installed package with no external files; `network.routing`
  selects `embedded` or `custom` rules and may extend the embedded buckets via
  `custom_rules`.

### Operations layer (`singbox_ops`)

`src/singbox_ops/` is a **separate top-level package** that owns every side
effect the engine deliberately avoids. It is not a provider and is not part of
`devconfig_gen`'s import graph; it depends on `devconfig_gen`, never the other
way around.

```text
singbox-ops CLI (context / deploy / redeploy / destroy)
        |
        v
core.plan -> core.context_builder -> devconfig_gen.engine.generate_pipeline
        |                                      |
        v                                      v
adapter suite                          pure server/client/links artifacts
  secrets · dns · acme · state · export · runtime(packages/systemd/nftables/watchdog)
```

- **Isolation:** the pure package keeps its zero-side-effect contract. Adding a
  deployment feature means adding an adapter, never touching the engine.
- **Adapters are plain classes:** a name -> factory mapping (`SECRET_FACTORIES`,
  `DNS_FACTORIES`, ...) instead of setuptools entry points, so there is exactly
  one plugin system in the project (providers), not two competing ones.
- **Injectable runner:** every adapter goes through a `CommandRunner`. `--dry-run`
  swaps in a `RecordingRunner`, and tests never touch a real system.
- **Explicit inputs:** secret generation lives here (the engine still receives
  only explicit credentials); the provider context is assembled by
  `core.context_builder`.
- **Optional state:** `adapters/state/local_json.py` persists non-secret
  deployment metadata (record IDs, prefixes, output paths) so `redeploy` /
  `destroy` can reuse it; setting `adapters.state: null` makes a run stateless.

### Clients

This repository ships thin clients only: the **CLI** (`cli.py`, argument parsing
plus calls into `engine`), the **interactive terminal wizard** (`interactive.py`,
`devconfig-gen init`), the **local Web studio** (`web_ui.py`, `devconfig-gen ui`),
and the **Python API** (`engine` helpers). They all consume the same declarative
metadata (`steps` / `diagnose`) and the same pipeline; none contains generation,
validation, or serialization logic of its own. The wizard and studio work for
every registered provider, including `singbox`.

## Design decisions

1. `models.py` is the only stable core data contract.
2. `registry.py` is the extension seam; adding a provider is registering an
   object with a lowercase `name`.
3. The engine never imports a specific provider directly; it works through the
   registry.
4. The CLI and the Python API share one code path, so their output is
   byte-for-byte identical.
5. Importing the package has no side effects. File output only happens when an
   explicit `output_dir` is supplied.
6. Provider metadata (`diagnose`, `steps`, `describe_schema`) is optional;
   minimal providers work with `name`, `validate`, and `generate` alone.
7. Serialization is deterministic: JSON and YAML both preserve insertion order,
   so output is byte-for-byte stable across runs and formats.
8. No remote operation, system mutation, credential handling, or deployment is
   part of the core engine. The only filesystem writes are explicit
   `output_dir` writes.

## Out of scope

The `devconfig_gen` engine and its providers do not perform deployment, remote
repository operations, service management, credential storage, or automatic
migration of machine state. Those concerns live in the separate `singbox_ops`
package, which is a *consumer* of the engine: it assembles a context, calls the
pure pipeline, and carries out side effects through adapters. The terminal
wizard and the local Web studio remain thin clients over the same pure pipeline,
so they add no side effects to the engine.
