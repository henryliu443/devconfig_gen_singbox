"""Exception hierarchy for the operations layer."""

from __future__ import annotations


class OpsError(Exception):
    """Base class for every error raised by ``singbox_ops``."""


class PlanError(OpsError, ValueError):
    """The deployment plan is missing or malformed."""


class AdapterError(OpsError):
    """An adapter could not complete its work."""


class CommandError(AdapterError):
    """An external command exited with a non-zero status."""

    def __init__(self, args, returncode, stdout="", stderr=""):
        self.args_list = list(args)
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        rendered = " ".join(str(item) for item in args) if not isinstance(args, str) else args
        super().__init__(
            f"command failed ({returncode}): {rendered}"
            + (f"\n{stderr.strip()}" if stderr and stderr.strip() else "")
        )
