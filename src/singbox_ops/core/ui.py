"""Tiny ANSI UI helpers for the interactive CLI.

Colours are disabled when the stream is not a TTY, when ``NO_COLOR`` is set, or
when ``TERM=dumb``, so logs and CI output stay clean.
"""

from __future__ import annotations

import os
import sys

RESET = "\033[0m"


def _supports_color(stream) -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("TERM", "") == "dumb":
        return False
    return hasattr(stream, "isatty") and stream.isatty()


class UI:
    def __init__(self, stream=None):
        self.stream = stream if stream is not None else sys.stdout
        self.color = _supports_color(self.stream)

    def _c(self, text: str, code: str) -> str:
        return f"\033[{code}m{text}{RESET}" if self.color else text

    def bold(self, text): return self._c(text, "1")
    def dim(self, text): return self._c(text, "2")
    def green(self, text): return self._c(text, "32")
    def yellow(self, text): return self._c(text, "33")
    def red(self, text): return self._c(text, "31")
    def cyan(self, text): return self._c(text, "36")

    def banner(self, title: str, subtitle: str = "") -> None:
        line = "═" * 60
        self.stream.write(self.cyan(line) + "\n")
        self.stream.write("  " + self.bold(title) + "\n")
        if subtitle:
            self.stream.write("  " + self.dim(subtitle) + "\n")
        self.stream.write(self.cyan(line) + "\n")

    def section(self, title: str) -> None:
        self.stream.write("\n" + self.cyan("▶ ") + self.bold(title) + "\n")

    def field(self, name: str, desc: str = "", required: bool = False) -> None:
        tag = self.red(" *必填") if required else ""
        self.stream.write(f"  {self.bold(name)}{tag}\n")
        if desc:
            self.stream.write("    " + self.dim(desc) + "\n")

    def step(self, text: str) -> None:
        self.stream.write("  " + self.cyan("→ ") + text + "\n")

    def success(self, text: str) -> None:
        self.stream.write("  " + self.green("✓ ") + text + "\n")

    def warn(self, text: str) -> None:
        self.stream.write("  " + self.yellow("! ") + text + "\n")

    def error(self, text: str) -> None:
        self.stream.write("  " + self.red("✗ ") + text + "\n")

    def kv(self, key: str, value: str) -> None:
        self.stream.write("  " + self.dim(f"{key}:") + " " + str(value) + "\n")
