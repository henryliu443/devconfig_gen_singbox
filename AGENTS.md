# Project Instructions

DevConfig-Gen is a local, provider-based tool for generating and validating
structured JSON/YAML configuration. Keep the core provider-neutral and free of
side effects.

## Repo relationship (父/子)

- **This repo is the CHILD (子仓库 / fork):** `DevConfig-Gen_SingBox` — a private
  integration fork.
- **Parent (父仓库 / upstream):** `DevConfig-Gen`
  (https://github.com/henryliu443/DevConfig-Gen) — owns the neutral core and the
  provider standard (`PROVIDER_STANDARD.md`).
- **Downstream legacy source (not a fork):** `Automated-sing-box-json-generator`
  — scheduled to be **merged/decoupled and retired**. It is **reference only**;
  never a development target. Do not develop there.

Authority flows **parent → child → downstream**:

- The parent owns the neutral core and the provider standard.
- Domain-specific providers (e.g. `providers/singbox/`) live **here**, never in
  the parent.
- Do **not** fork or diverge the neutral core. Core changes are made in the
  parent first and flow down; pull them via the `upstream` remote (see the
  handoff). Never re-implement engine/format/validation logic here.

## Ground rules

- Follow `PROVIDER_STANDARD.md` (the DevConfig-Gen provider iron standard /
  white paper) for any "rich domain" (transformation) provider: zero side
  effects, pluggable variant isolation, no upstream version chasing, and
  explicit credentials-as-input. Read it before adding or changing a provider.
- Do not add network, deployment, service-management, credential, or
  system-mutation behavior to the core engine.
- Keep the CLI and the `init`/`ui` clients thin: they must call the shared
  pipeline in `devconfig_gen.engine`, never re-implement generation logic.
- Keep output deterministic: JSON and YAML preserve insertion order, so
  generated artifacts stay byte-for-byte stable.
- Every behavior change needs a test. Run the suite before finishing:

  ```bash
  PYTHONPATH=src python3 -m unittest discover -s tests -v
  ```

- Keep `README.md` and `ARCHITECTURE.md` accurate when the public API, CLI,
  formats, or provider contract changes.
- Do not publish packages, create releases, or push to a remote repository
  unless explicitly asked.
