# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [2.1.1] - 2026-09-22

### Added

- **Interactive terminal wizard restored**: `devconfig-gen init`
  (`interactive.py`). Ported from the parent repository; driven entirely by a
  provider's declarative `steps` / `diagnose` metadata, so it works for
  `singbox` and every built-in provider with no per-provider code.
- **Local Web studio restored**: `devconfig-gen ui` (`web_ui.py`). Ported from
  the parent repository; zero-build (stdlib `http.server`), live preview, split
  editor, and export into a workspace root.
- **`WebUIWidgets` protocol restored** (`devconfig_gen.models.WebUIWidgets`):
  providers may implement the optional `web_ui_widgets()` hook, served over
  `GET /api/widgets`, to render a field type with a custom widget. Purely
  additive; providers without it render exactly as before.
- `docs/wizard.md` and `docs/web-ui.md`, wired into the docs navigation.

## [2.1.0] - 2026-09-22

### Added

- **`singbox_ops` deployment layer** (`src/singbox_ops/`): a sibling package
  that owns every side effect the pure engine deliberately avoids. It exposes
  the `singbox-ops` CLI (`context` / `deploy` / `redeploy` / `destroy`) and a
  suite of pluggable adapters: Cloudflare DNS, acme.sh + Cloudflare DNS-01
  certificates, sing-box/WARP package installation, systemd, nftables, the WARP
  watchdog, optional local JSON state, artifact export, and secret generation
  (sing-box subprocess with a pure-Python fallback). It calls
  `devconfig_gen.engine.generate_pipeline("singbox", ...)` as a library and is
  never registered as a `ConfigProvider`.
- `examples/singbox-deploy.yaml` deployment plan sample.
- 58 tests covering the ops layer, all side effects mocked.

### Changed

- PyPI distribution name is now `devconfig_gen_singbox`. The child fork
  previously reused the parent's `devconfig-gen` name, which collided with the
  parent's trusted publisher and made OIDC publishing fail. The import package
  (`devconfig_gen`) and the `devconfig-gen` console script are unchanged.

## [2.0.0]

### Added

- **`singbox` provider** (child-fork domain provider): generates
  `sing-box.server.{json,yaml}`, `sing-box.client.{json,yaml}`, and
  `sing-box-links.txt` from a structured context. Variant detail for `anytls`,
  `tuic`, and `hysteria2` is isolated in `providers/singbox/plugins/` behind a
  plugin contract; the neutral layers (`provider.py` / `schema.py` /
  `route.py`) never mention a protocol field name. Credentials and subdomain
  prefixes are explicit inputs (zero side effects, no environment reads, no
  subprocesses). Routing rules load from the embedded
  `providers/singbox/data/rules.json`, selectable/extendable through
  `network.routing`.
- `examples/singbox.yaml` sample input.

### Removed

- The interactive terminal wizard (`interactive.py`, `devconfig-gen init`) and
  the local Web studio (`web_ui.py`, `devconfig-gen ui`) are removed from this
  child fork, along with their tests and docs. The supported surface is now the
  stable **CLI** (`providers` / `schema` / `generate` / `validate`) and the
  **Python API** only. The `WebUIWidgets` protocol and the `web_ui_widgets()`
  hook are gone with them.
- `docs/wizard.md` and `docs/web-ui.md`, and their navigation/references.
- The static HTML landing page (`landing/index.html`) and its docs-workflow
  publishing step; the repository now contains no HTML.

### Changed

- The README is repositioned around **bounded domain scopes**: it leads with the
  `devconfig_gen_singbox` child identity and the `singbox` domain (domain model,
  validation, transformations, variants, share links), and demotes the inherited
  engine capabilities to an "Inherited DevConfig-Gen Engine" section. The parent
  owns the neutral engine and provider contract; the child owns the domain.
- `default_registry` now registers `singbox` alongside `custom`, `json`, and
  `env`; `devconfig-gen providers` lists four providers.

## [1.1.0]

### Added

- **WebUI widget registry**: field rendering is now table-driven. The six
  built-in field types (`string`, `integer`, `boolean`, `mapping`, `document`,
  `tree`) each map to a registered default widget instead of a hard-coded
  `if`/`else` chain, so the rendering path is pluggable end to end.
- **Provider-declared widgets**: an optional `web_ui_widgets()` method lets a
  provider map a `field_type` to a JavaScript factory. The new
  `GET /api/widgets?provider=<name>` endpoint serves them and the client
  registers them into the same table; unknown types fall back to `string`, and
  providers without the method behave exactly as before.
- `WebUIWidgets` protocol in `devconfig_gen.models` (documentation-only; never
  required) and exported from the package root.
- WebUI hamburger sidebar (`☰`) with quick links to the repository, docs site,
  issues, and email.
- Blank-context detection: a stale cleared draft (`{}` or a lone empty
  `document`) no longer hides the provider's starter data.

### Changed

- The `custom` tree editor's bulk add moved from an inline row inside every
  container to a toolbar toggle at the root, reducing clutter at every depth.
- WebUI visual refresh: larger rounded cards, pill-shaped buttons, softer
  shadows, and more generous spacing.
- Complete technical documentation set under `docs/`, covering installation,
  CLI, Python API, providers, formats, input merging, validation, the
  interactive wizard, the Web UI/HTTP API, development, and architecture.
- `mkdocs.yml` (MkDocs + Material) plus a GitHub Pages workflow that publishes
  `docs/` from the dedicated `docs` branch; the Markdown files remain the source
  of truth, and Unicode-preserving heading anchors keep relative links valid.

### Fixed

- `devconfig_gen.__version__` matches `pyproject.toml`; the CLI `--version`
  output reads the package version instead of a hard-coded string, and a test
  guards the two against drifting apart.

## [1.0.0]

### Added

- `custom` provider: a schema-free generic document that accepts any JSON/YAML
  nesting (mapping, sequence, or scalar root) and is editable at any depth.
- WebUI tree editor for `custom` with per-container bulk add and a "nest"
  action, plus a JSON/YAML text mode and a header "Clear All" reset.

### Removed

- The `service` provider and its `examples/service.*` samples. Use `custom` for
  arbitrary documents, `json` for pass-through, and `env` for `.env` output.

### Changed

- `devconfig-gen init` now defaults to `--provider custom`.

## [0.3.0]
### Added

- `env` provider: flattens nested structured data into an `UPPER_SNAKE_CASE`
  `.env` document, including declarative `steps` metadata.
- Multi-source input: `generate_pipeline` / `build_request` accept multiple
  input files and deep-merge them left to right (`formats.deep_merge`).
- CLI `--input` is repeatable and a new `--set KEY=VALUE` option applies dotted
  path overrides after merging.
- `devconfig-gen schema` command and `devconfig-gen validate --json` structured
  diagnostics output.
- CI workflow testing Linux and macOS across Python 3.8–3.14.

### Changed

- JSON output now preserves insertion order (`sort_keys=False`), matching YAML,
  so generated configuration keeps the provider's semantic field order.
- Corrected YAML block scalar chomping (`|`, `|-`, `|+`, `>`, `>-`, `>+`) and
  folded-scalar handling of blank lines.
- Unknown fields in the `service` provider now include a "did you mean" hint.

### Fixed

- Exported `ValidationError` from the package root.
- Imported `Union` in `engine.py` so `typing.get_type_hints` works.
- The interactive wizard preserves previous answers when retrying after a
  validation failure and aborts cleanly on end-of-input.
- The WebUI returns structured JSON errors for bad input/unknown providers,
  rejects non-loopback `Host` headers, and sandboxes disk export to a workspace
  root.

## [0.2.0]

### Added

- Structured `Diagnostic(field, message, severity)` values and declarative
  `ProviderField` / `ProviderStep` metadata.
- `service` provider with normalization, strict validation, and JSON/YAML
  output.
- `devconfig-gen init` terminal wizard and `devconfig-gen ui` local studio.
- Self-contained, dependency-free JSON/YAML load and dump (`formats`).

### Changed

- CLI and Python API share a single pipeline in `devconfig_gen.engine`.

## [0.1.0]

### Added

- Initial provider contract, registry, JSON provider, and CLI skeleton.
