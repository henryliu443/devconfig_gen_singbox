#!/usr/bin/env python3
"""Repeatable smoke harness for DevConfig-Gen_SingBox.

Each round verifies two independent things:

  1. the full unittest suite (fresh interpreter);
  2. end-to-end business parity between the Python API and the CLI for every
     built-in provider x format, byte-for-byte, including the multi-artifact
     ``singbox`` provider (server / client / links).

Usage:
    python3 scripts/smoke_rounds.py [rounds]   # default: 8

Exit code is 0 only if every round passes.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
EXAMPLES = ROOT / "examples"
sys.path.insert(0, str(SRC))

from devconfig_gen import formats, generate, load_file  # noqa: E402
from devconfig_gen.models import GenerationRequest  # noqa: E402

CASES = [
    ("custom", EXAMPLES / "custom.yaml"),
    ("json", EXAMPLES / "custom.json"),
    ("env", EXAMPLES / "vars.yaml"),
]
SINGBOX_EXAMPLE = EXAMPLES / "singbox.yaml"
FORMATS = ["yaml", "json"]


def run_suite() -> tuple:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(SRC)
    proc = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests"],
        capture_output=True, text=True, cwd=str(ROOT), env=env,
    )
    out = proc.stderr + proc.stdout
    match = re.search(r"Ran (\d+) tests", out)
    return proc.returncode == 0, (int(match.group(1)) if match else -1), out


def _rendered(artifact, fmt: str) -> str:
    if isinstance(artifact.content, str):
        return artifact.content
    return formats.dumps(artifact.content, fmt)


def api_artifacts(provider: str, context, fmt: str) -> dict:
    result = generate(provider, GenerationRequest(context=context, options={"format": fmt}))
    return {artifact.name: _rendered(artifact, fmt) for artifact in result.artifacts}


def cli_artifacts(provider: str, path, fmt: str, workdir) -> dict:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(SRC)
    outdir = Path(workdir) / f"{provider}_{fmt}"
    proc = subprocess.run(
        [sys.executable, "-m", "devconfig_gen.cli", "generate",
         "--provider", provider, "--input", str(path),
         "--output-dir", str(outdir), "--format", fmt],
        capture_output=True, text=True, cwd=str(ROOT), env=env,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"CLI failed for {provider}/{fmt}: {proc.stderr}")
    return {item.name: item.read_text(encoding="utf-8") for item in outdir.iterdir() if item.is_file()}


def parity_round() -> list:
    checks = []
    with tempfile.TemporaryDirectory() as work:
        for provider, path in CASES:
            context = load_file(path)
            for fmt in FORMATS:
                api = api_artifacts(provider, context, fmt)
                cli = cli_artifacts(provider, path, fmt, work)
                checks.append((f"{provider}/{fmt}", api == cli))
        context = load_file(SINGBOX_EXAMPLE)
        for fmt in FORMATS:
            api = api_artifacts("singbox", context, fmt)
            cli = cli_artifacts("singbox", SINGBOX_EXAMPLE, fmt, work)
            checks.append((f"singbox/{fmt}", api == cli))
    return checks


def main() -> int:
    rounds = int(sys.argv[1]) if len(sys.argv) > 1 else 8
    all_ok = True
    for round_number in range(1, rounds + 1):
        suite_ok, count, out = run_suite()
        try:
            checks = parity_round()
            parity_ok = all(name_ok[1] for name_ok in checks)
        except Exception as exc:  # noqa: BLE001
            checks, parity_ok = [], False
            print(f"round {round_number}: parity error: {exc}")
        status = "OK" if (suite_ok and parity_ok) else "FAIL"
        all_ok = all_ok and suite_ok and parity_ok
        detail = " ".join(f"{name}{'' if ok else '!'}" for name, ok in checks)
        print(f"round {round_number}: {status}  suite={count}  parity=[{detail}]")
        if not suite_ok:
            print(out)
    print("=" * 60)
    print("SMOKE", "PASS" if all_ok else "FAIL", f"({rounds} rounds)")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
