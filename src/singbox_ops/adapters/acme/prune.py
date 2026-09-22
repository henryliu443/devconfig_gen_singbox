"""Prune stale acme.sh certificate directories.

Only ``<acme_home>/<host>_ecc`` directories are ever considered. Anything whose
host is not in the keep set is removed. The operation refuses to run with an
empty keep set, and defaults to a dry run, so a slip can never wipe every
certificate (the failure mode of hand-rolled shell).
"""

from __future__ import annotations

import os
from typing import Mapping, Sequence

from ...core.command import CommandRunner, LocalCommandRunner
from ...core.exceptions import AdapterError

DEFAULT_ACME_HOME = "/root/.acme.sh"
SUFFIX = "_ecc"


def plan_prune(
    runner: CommandRunner,
    acme_home: str,
    keep_hosts: Sequence[str],
) -> "tuple[list, list]":
    keep_set = {str(item).strip() for item in keep_hosts if str(item).strip()}
    if not keep_set:
        raise AdapterError("refusing to prune: no hosts to keep")
    try:
        entries = runner.listdir(acme_home)
    except OSError as exc:
        raise AdapterError(f"cannot list {acme_home}: {exc}") from exc

    keep: list = []
    remove: list = []
    for entry in entries:
        if not entry.endswith(SUFFIX):
            continue
        domain = entry[: -len(SUFFIX)]
        (keep if domain in keep_set else remove).append(entry)
    return keep, remove


def prune_certs(
    runner: CommandRunner,
    acme_home: str = DEFAULT_ACME_HOME,
    keep_hosts: Sequence[str] = (),
    dry_run: bool = True,
) -> Mapping[str, object]:
    keep, remove = plan_prune(runner, acme_home, keep_hosts)
    result = {"acme_home": acme_home, "keep": sorted(keep), "remove": sorted(remove), "dry_run": dry_run}
    if dry_run:
        return result
    for entry in remove:
        runner.run(["rm", "-rf", os.path.join(acme_home, entry)], check=False)
    return result
