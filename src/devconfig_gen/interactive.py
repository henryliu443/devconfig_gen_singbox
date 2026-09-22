"""Interactive terminal wizard for generating configuration.

Designed for headless environments (e.g. Linux SSH servers or terminal-first
workflows on macOS). Driven entirely by the provider's declarative steps and
schema metadata, so there is no duplication with the core engine or the WebUI.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, Optional, Sequence, TextIO

from . import formats
from .engine import describe_provider, diagnose_request, generate
from .models import GenerationRequest, ProviderField, ProviderStep
from .registry import ProviderRegistry, default_registry


class _EndOfInput(Exception):
    """Raised when the input stream ends before a required answer is given."""

    def __init__(self, field_name: str):
        super().__init__(field_name)
        self.field_name = field_name


def _set_dotted_path(target: Dict[str, Any], path: str, value: Any) -> None:
    """Set a value in a nested dict using a dotted path like 'app.port'."""

    parts = path.split(".")
    current = target
    for part in parts[:-1]:
        if part not in current or not isinstance(current[part], dict):
            current[part] = {}
        current = current[part]
    current[parts[-1]] = value


def _get_dotted_path(source: Any, path: str, default: Any = None) -> Any:
    """Retrieve a value from a nested dict using a dotted path."""

    if not isinstance(source, dict):
        return default
    current: Any = source
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return default
        current = current[part]
    return current


def _read_line(reader: TextIO, writer: TextIO, prompt: str) -> Optional[str]:
    """Write ``prompt`` and read one line.

    Returns the stripped line, or ``None`` when the stream is exhausted. A blank
    line (``"\\n"``) is distinct from end-of-input (``""``).
    """

    writer.write(prompt)
    writer.flush()
    line = reader.readline()
    if line == "":
        return None
    return line.strip()


def _prompt_string(
    field: ProviderField,
    current_value: Any,
    reader: TextIO,
    writer: TextIO,
) -> Any:
    effective_default = current_value if current_value is not None else field.default
    default_str = f" [{effective_default}]" if effective_default is not None else ""
    req_str = " (required)" if field.required and effective_default is None else ""

    if field.choices:
        writer.write(f"? {field.name} - Select option:{req_str}\n")
        for i, choice in enumerate(field.choices, 1):
            writer.write(f"    {i}) {choice}\n")
        lower_choices = {str(c).lower(): c for c in field.choices}
        while True:
            answer = _read_line(reader, writer, f"  Enter choice number or name{default_str}: ")
            if answer is None:
                if effective_default is not None:
                    return effective_default
                raise _EndOfInput(field.name)
            if answer == "":
                if effective_default is not None:
                    return effective_default
                if field.required:
                    writer.write("  [!] Selection is required. Please choose an option.\n")
                    continue
                return None
            if answer.isdigit():
                idx = int(answer) - 1
                if 0 <= idx < len(field.choices):
                    return field.choices[idx]
            if answer.lower() in lower_choices:
                return lower_choices[answer.lower()]
            writer.write(
                f"  [!] Invalid choice: {answer!r}. Please select 1-{len(field.choices)}.\n"
            )

    while True:
        answer = _read_line(reader, writer, f"? {field.name}{req_str}{default_str}: ")
        if answer is None:
            if effective_default is not None:
                return effective_default
            raise _EndOfInput(field.name)
        if answer == "":
            if effective_default is not None:
                return effective_default
            if field.required:
                writer.write("  [!] This field is required.\n")
                continue
            return None
        return answer


def _prompt_integer(
    field: ProviderField,
    current_value: Any,
    reader: TextIO,
    writer: TextIO,
) -> Any:
    effective_default = current_value if current_value is not None else field.default
    default_str = f" [{effective_default}]" if effective_default is not None else ""
    bounds = []
    if field.minimum is not None:
        bounds.append(f"min {int(field.minimum)}")
    if field.maximum is not None:
        bounds.append(f"max {int(field.maximum)}")
    bound_str = f" ({', '.join(bounds)})" if bounds else ""
    req_str = " (required)" if field.required and effective_default is None else ""

    while True:
        answer = _read_line(reader, writer, f"? {field.name}{bound_str}{req_str}{default_str}: ")
        if answer is None:
            if effective_default is not None:
                return effective_default
            raise _EndOfInput(field.name)
        if answer == "":
            if effective_default is not None:
                return effective_default
            if field.required:
                writer.write("  [!] An integer value is required.\n")
                continue
            return None
        try:
            number = int(answer)
        except ValueError:
            writer.write(f"  [!] Expected integer, got {answer!r}.\n")
            continue
        if field.minimum is not None and number < field.minimum:
            writer.write(f"  [!] Value must be >= {int(field.minimum)}.\n")
            continue
        if field.maximum is not None and number > field.maximum:
            writer.write(f"  [!] Value must be <= {int(field.maximum)}.\n")
            continue
        return number


def _prompt_boolean(
    field: ProviderField,
    current_value: Any,
    reader: TextIO,
    writer: TextIO,
) -> bool:
    effective_default = bool(current_value if current_value is not None else field.default)
    prompt_hint = "[Y/n]" if effective_default else "[y/N]"
    while True:
        answer = _read_line(reader, writer, f"? {field.name} {prompt_hint}: ")
        if answer is None or answer == "":
            return effective_default
        lowered = answer.lower()
        if lowered in ("y", "yes", "true", "1"):
            return True
        if lowered in ("n", "no", "false", "0"):
            return False
        writer.write("  [!] Please enter 'y' for yes or 'n' for no.\n")


def _prompt_mapping(
    field: ProviderField,
    current_value: Any,
    reader: TextIO,
    writer: TextIO,
) -> Dict[str, str]:
    mapping: Dict[str, str] = dict(current_value) if isinstance(current_value, dict) else {}
    writer.write(
        f"? {field.name} (enter key=value pairs, press enter on empty line to finish):\n"
    )
    if mapping:
        writer.write(
            "    Current entries: " + ", ".join(f"{k}={v}" for k, v in mapping.items()) + "\n"
        )
    while True:
        answer = _read_line(reader, writer, "    key=val (or empty to finish): ")
        if answer is None or answer == "":
            break
        if "=" not in answer:
            writer.write("    [!] Invalid format. Must be key=value.\n")
            continue
        key, value = answer.split("=", 1)
        mapping[key.strip()] = value.strip()
    return mapping


def _prompt_document(
    field: ProviderField,
    current_value: Any,
    reader: TextIO,
    writer: TextIO,
) -> Any:
    writer.write(f"? {field.name} (load document file or enter entries):\n")
    path_str = _read_line(
        reader, writer, "    Path to JSON/YAML file (or press enter for key=value input): "
    )
    if path_str:
        file_path = Path(path_str).expanduser()
        if file_path.is_file():
            try:
                loaded = formats.load_file(file_path)
                writer.write(f"    [✓] Loaded document from {file_path}\n")
                return loaded
            except Exception as exc:
                writer.write(f"    [!] Error reading {file_path}: {exc}\n")
        else:
            writer.write(f"    [!] File not found: {path_str}\n")
    return _prompt_mapping(field, current_value, reader, writer)


def prompt_field(
    field: ProviderField,
    current_value: Any,
    reader: TextIO,
    writer: TextIO,
) -> Any:
    """Prompt the user for a single field's value based on its type."""

    if field.type == "integer":
        return _prompt_integer(field, current_value, reader, writer)
    if field.type == "boolean":
        return _prompt_boolean(field, current_value, reader, writer)
    if field.type in ("mapping", "dict"):
        return _prompt_mapping(field, current_value, reader, writer)
    if field.type in ("document", "tree"):
        return _prompt_document(field, current_value, reader, writer)
    return _prompt_string(field, current_value, reader, writer)


def run_interactive_wizard(
    provider_name: str,
    *,
    input_path: Optional[str] = None,
    context: Optional[Dict[str, Any]] = None,
    output_dir: Optional[str] = None,
    output_format: Optional[str] = None,
    registry: Optional[ProviderRegistry] = None,
    reader: Optional[TextIO] = None,
    writer: Optional[TextIO] = None,
) -> int:
    """Execute the interactive wizard loop in the terminal.

    ``context`` seeds the wizard with existing answers. ``input_path`` loads a
    document from disk and merges it on top of ``context``. On validation
    failure the wizard offers to re-run while keeping every answer pre-filled.

    Returns ``0`` on successful generation and ``1`` on cancellation or error.
    """

    in_stream = reader or sys.stdin
    out_stream = writer or sys.stdout

    reg = registry or default_registry
    try:
        reg.get(provider_name)
    except ValueError as exc:
        out_stream.write(f"Error: {exc}\n")
        return 1

    steps: Sequence[ProviderStep] = describe_provider(provider_name, registry=reg)
    if not steps:
        out_stream.write(
            f"Provider '{provider_name}' does not define declarative wizard steps.\n"
        )
        return 1

    working: Dict[str, Any] = dict(context) if context else {}
    if input_path:
        try:
            loaded = formats.load_file(input_path)
        except Exception as exc:
            out_stream.write(f"[warn] Could not load initial context: {exc}\n")
        else:
            if isinstance(loaded, dict):
                working.update(loaded)
                out_stream.write(f"[info] Pre-populated wizard with values from {input_path}\n")
            else:
                out_stream.write(
                    f"[warn] {input_path} does not contain a mapping; ignoring it.\n"
                )

    out_stream.write("========================================================\n")
    out_stream.write(f"  DevConfig-Gen Interactive Wizard: '{provider_name}'\n")
    out_stream.write("  Answer the prompts below. Press Enter to use defaults.\n")
    out_stream.write("========================================================\n")

    total_steps = len(steps)
    while True:
        try:
            for step_idx, step in enumerate(steps, 1):
                out_stream.write(f"\n--- [{step_idx}/{total_steps}] {step.title} ---\n")
                if step.description:
                    out_stream.write(f"  {step.description}\n")
                for field in step.fields:
                    existing = _get_dotted_path(working, field.name)
                    value = prompt_field(field, existing, in_stream, out_stream)
                    if value is not None:
                        _set_dotted_path(working, field.name, value)
        except _EndOfInput as exc:
            out_stream.write(
                f"\n[!] Input ended before '{exc.field_name}' was provided. Aborting.\n"
            )
            return 1

        out_stream.write("\nValidating configuration...\n")
        diagnostics = diagnose_request(provider_name, context=working, registry=reg)
        errors = [item for item in diagnostics if item.severity == "error"]
        if not errors:
            break

        out_stream.write("\n[!] Validation found errors:\n")
        for err in errors:
            out_stream.write(f"  - {err.field}: {err.message}\n")

        answer = _read_line(
            in_stream,
            out_stream,
            "Re-run the wizard to correct these? [Y/n]: ",
        )
        if answer is None or answer.lower() in ("n", "no"):
            out_stream.write("Aborted.\n")
            return 1
        out_stream.write("\nRe-running wizard with your previous answers pre-filled...\n")

    out_stream.write("[✓] All validations passed!\n\n")

    selected_format = output_format
    if not selected_format:
        answer = _read_line(
            in_stream,
            out_stream,
            "Select output format (1: YAML [default], 2: JSON): ",
        )
        selected_format = "json" if answer == "2" else "yaml"

    target_dir = output_dir or "."
    out_stream.write(f"Writing configuration to '{target_dir}'...\n")

    try:
        result = generate(
            provider_name,
            GenerationRequest(context=working, options={"format": selected_format}),
            registry=reg,
            output_dir=target_dir,
        )
    except Exception as exc:
        out_stream.write(f"[!] Generation failed: {exc}\n")
        return 1

    for artifact in result.artifacts:
        out_path = Path(target_dir) / artifact.name
        out_stream.write(f"[✓] Generated artifact: {out_path.resolve()}\n")
    return 0
