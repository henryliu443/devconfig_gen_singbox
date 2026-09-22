"""Injectable command / filesystem runner.

Every adapter goes through a :class:`CommandRunner` instead of calling
``subprocess`` or ``open`` directly. That gives us two things:

- ``--dry-run`` is just a :class:`RecordingRunner`: it records intended actions
  instead of executing them.
- tests use the same runner, so no adapter test ever touches a real system.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, List, Optional, Sequence, Tuple

from .exceptions import CommandError


class CommandResult:
    """Minimal result object shared by real and recorded runs."""

    def __init__(self, args: Any, returncode: int = 0, stdout: str = "", stderr: str = ""):
        self.args = args
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr

    def check_returncode(self) -> "CommandResult":
        if self.returncode != 0:
            raise CommandError(self.args, self.returncode, self.stdout, self.stderr)
        return self


class CommandRunner:
    """Structural contract for executing commands and touching files."""

    def run(self, args: Sequence[str], *, check: bool = True, env=None) -> CommandResult:
        raise NotImplementedError

    def shell(self, command: str, *, check: bool = True, env=None) -> CommandResult:
        raise NotImplementedError

    def write_text(self, path, text: str, *, mode: Optional[int] = None) -> None:
        raise NotImplementedError

    def read_text(self, path) -> str:
        raise NotImplementedError

    def exists(self, path) -> bool:
        raise NotImplementedError

    def islink(self, path) -> bool:
        raise NotImplementedError

    def listdir(self, path) -> List[str]:
        raise NotImplementedError

    def mkdir(self, path, *, mode: Optional[int] = None) -> None:
        raise NotImplementedError

    def unlink(self, path, *, missing_ok: bool = True) -> None:
        raise NotImplementedError

    def symlink(self, target, path) -> None:
        raise NotImplementedError

    def chmod(self, path, mode: int) -> None:
        raise NotImplementedError


def _fmt(args) -> str:
    if isinstance(args, str):
        return args
    return " ".join(str(item) for item in args)


class LocalCommandRunner(CommandRunner):
    """Execute commands and write files on the local machine.

    ``on_command`` receives every command line right before it is executed, so
    the CLI can echo what it is doing.
    """

    def __init__(self, on_command=None):
        self.on_command = on_command

    def run(self, args: Sequence[str], *, check: bool = True, env=None) -> CommandResult:
        if self.on_command is not None:
            self.on_command(_fmt(args))
        merged_env = None
        if env is not None:
            merged_env = dict(os.environ)
            merged_env.update({str(k): str(v) for k, v in env.items()})
        proc = subprocess.run(
            [str(item) for item in args],
            capture_output=True,
            text=True,
            env=merged_env,
        )
        result = CommandResult(args, proc.returncode, proc.stdout, proc.stderr)
        return result.check_returncode() if check else result

    def shell(self, command: str, *, check: bool = True, env=None) -> CommandResult:
        if self.on_command is not None:
            self.on_command(command)
        merged_env = None
        if env is not None:
            merged_env = dict(os.environ)
            merged_env.update({str(k): str(v) for k, v in env.items()})
        proc = subprocess.run(command, shell=True, capture_output=True, text=True, env=merged_env)
        result = CommandResult(command, proc.returncode, proc.stdout, proc.stderr)
        return result.check_returncode() if check else result

    def write_text(self, path, text: str, *, mode: Optional[int] = None) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        if mode is not None:
            fd = os.open(str(target), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(text)
            return
        target.write_text(text, encoding="utf-8")

    def read_text(self, path) -> str:
        return Path(path).read_text(encoding="utf-8")

    def exists(self, path) -> bool:
        return Path(path).exists()

    def islink(self, path) -> bool:
        return Path(path).is_symlink()

    def listdir(self, path) -> List[str]:
        return sorted(os.listdir(str(path)))

    def mkdir(self, path, *, mode: Optional[int] = None) -> None:
        target = Path(path)
        target.mkdir(parents=True, exist_ok=True)
        if mode is not None:
            os.chmod(str(target), mode)

    def unlink(self, path, *, missing_ok: bool = True) -> None:
        try:
            Path(path).unlink()
        except FileNotFoundError:
            if not missing_ok:
                raise

    def symlink(self, target, path) -> None:
        link = Path(path)
        link.parent.mkdir(parents=True, exist_ok=True)
        if link.is_symlink() or link.exists():
            link.unlink()
        link.symlink_to(target)

    def chmod(self, path, mode: int) -> None:
        os.chmod(str(path), mode)


class RecordingRunner(CommandRunner):
    """Record intended actions without performing them (``--dry-run`` / tests)."""

    def __init__(self, existing: Optional[Sequence[str]] = None, on_command=None):
        self.on_command = on_command
        self.commands: List[Tuple[Any, ...]] = []
        self.shell_commands: List[str] = []
        self.writes: List[Tuple[str, str, Optional[int]]] = []
        self.directories: List[Tuple[str, Optional[int]]] = []
        self.removed: List[str] = []
        self.links: List[Tuple[str, str]] = []
        self._existing = set(str(item) for item in (existing or ()))
        self._files = {}
        self._dirs = {}

    def run(self, args: Sequence[str], *, check: bool = True, env=None) -> CommandResult:
        self.commands.append(("run", tuple(str(item) for item in args), dict(env or {})))
        if self.on_command is not None:
            self.on_command(_fmt(args))
        return CommandResult(tuple(args), 0, "", "")

    def shell(self, command: str, *, check: bool = True, env=None) -> CommandResult:
        self.shell_commands.append(command)
        self.commands.append(("shell", command, dict(env or {})))
        if self.on_command is not None:
            self.on_command(command)
        return CommandResult(command, 0, "", "")

    def write_text(self, path, text: str, *, mode: Optional[int] = None) -> None:
        self.writes.append((str(path), text, mode))
        self._existing.add(str(path))
        self._files[str(path)] = text

    def read_text(self, path) -> str:
        return self._files.get(str(path), "")

    def exists(self, path) -> bool:
        return str(path) in self._existing

    def islink(self, path) -> bool:
        return False

    def listdir(self, path) -> List[str]:
        return sorted(self._dirs.get(str(path), set()))

    def mkdir(self, path, *, mode: Optional[int] = None) -> None:
        self.directories.append((str(path), mode))
        self._existing.add(str(path))
        self._dirs.setdefault(str(path), set())

    def unlink(self, path, *, missing_ok: bool = True) -> None:
        self.removed.append(str(path))
        self._existing.discard(str(path))

    def symlink(self, target, path) -> None:
        self.links.append((str(target), str(path)))
        self._existing.add(str(path))

    def chmod(self, path, mode: int) -> None:
        self.commands.append(("chmod", str(path), mode))


def default_runner() -> CommandRunner:
    return LocalCommandRunner()


def which(name: str) -> Optional[str]:
    return shutil.which(name)
