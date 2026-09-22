"""Write generated artifacts to their final paths.

Artifacts are matched to logical output keys (``server_config``,
``client_config``, ``links``) rather than exact filenames, so JSON/YAML and
provider naming changes stay compatible.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional, Sequence

from devconfig_gen import formats

from ...core.command import CommandRunner, LocalCommandRunner

SERVER_SUFFIX = "server_config"
CLIENT_SUFFIX = "client_config"
LINKS_SUFFIX = "links"


def match_output_key(artifact_name: str) -> Optional[str]:
    name = artifact_name.lower()
    if "links" in name:
        return LINKS_SUFFIX
    if "server" in name:
        return SERVER_SUFFIX
    if "client" in name:
        return CLIENT_SUFFIX
    return None


def serialize_artifact(artifact: Any) -> str:
    content = artifact.content
    if isinstance(content, str):
        return content
    fmt = formats.format_from_media_type(artifact.media_type)
    return formats.dumps(content, fmt)


class LocalFilesExport:
    def __init__(self, runner: Optional[CommandRunner] = None):
        self.runner = runner or LocalCommandRunner()

    def write(
        self,
        artifacts: Sequence[Any],
        outputs: Mapping[str, str],
        *,
        dry_run: bool = False,
    ) -> Mapping[str, str]:
        written: dict = {}
        for artifact in artifacts:
            key = match_output_key(artifact.name)
            if key is None:
                continue
            destination = outputs.get(key)
            if not destination:
                continue
            # Single-file model: never write *through* a legacy symlink (for
            # example config.json -> profiles/config.direct.json). Replace the
            # link with a real file so the old profile-switching scheme cannot
            # silently redirect our write.
            if not dry_run and self.runner.islink(destination):
                self.runner.unlink(destination)
            text = serialize_artifact(artifact)
            self.runner.write_text(destination, text, mode=0o600)
            written[key] = destination
        return written
