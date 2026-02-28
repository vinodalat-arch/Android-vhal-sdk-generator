"""Download and verify build artifacts from GitHub Actions."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Iterator

from ..shell.runner import ShellRunner
from . import config


class ArtifactManager:
    """Downloads build artifacts via `gh run download` and verifies them."""

    def __init__(self, shell: ShellRunner | None = None) -> None:
        self._shell = shell or ShellRunner()

    def download(
        self,
        run_id: str,
        dest_dir: Path,
        cwd: Path | None = None,
    ) -> Iterator[str]:
        """Download artifacts and yield status lines.

        Args:
            run_id: GitHub Actions run ID.
            dest_dir: Local directory to save artifacts into.
            cwd: Working directory for gh commands.

        Yields:
            Status lines.
        """
        dest_dir.mkdir(parents=True, exist_ok=True)
        yield f"Downloading artifacts from run {run_id} → {dest_dir}"

        last_err = ""
        for attempt in range(1, config.ARTIFACT_DOWNLOAD_RETRIES + 1):
            rc, stdout, stderr = self._shell.run(
                [
                    "gh", "run", "download", run_id,
                    "--dir", str(dest_dir),
                ],
                cwd=cwd,
                timeout=300,
            )
            if rc == 0:
                yield "Download complete."
                break
            last_err = stderr.strip()
            if attempt < config.ARTIFACT_DOWNLOAD_RETRIES:
                yield f"  Download attempt {attempt} failed, retrying in {config.ARTIFACT_DOWNLOAD_BACKOFF_SECONDS}s..."
                time.sleep(config.ARTIFACT_DOWNLOAD_BACKOFF_SECONDS)
        else:
            yield f"FAIL Download failed after {config.ARTIFACT_DOWNLOAD_RETRIES} attempts: {last_err}"
            return

        yield from self._verify(dest_dir)

    def verify_dir(self, artifact_dir: Path) -> Iterator[str]:
        """Verify a previously downloaded artifact directory.

        Yields:
            Status lines.
        """
        yield f"Verifying artifacts in {artifact_dir}"
        yield from self._verify(artifact_dir)

    def _verify(self, artifact_dir: Path) -> Iterator[str]:
        """Check that expected files exist and are non-empty."""
        # gh run download nests files inside an artifact-name subdirectory.
        # Flatten: look in artifact_dir and one level of subdirectories.
        found: dict[str, Path] = {}
        for path in artifact_dir.rglob("*"):
            if path.is_file():
                found[path.name] = path

        all_ok = True
        for expected in config.ARTIFACT_FILES:
            if expected in found and found[expected].stat().st_size > 0:
                size_kb = found[expected].stat().st_size / 1024
                yield f"PASS {expected} ({size_kb:.0f} KB)"
            else:
                yield f"FAIL {expected} — missing or empty"
                all_ok = False

        if all_ok:
            yield "All artifacts verified."
        else:
            yield "WARNING: Some artifacts missing — deploy may fail."

    def find_artifact_file(self, artifact_dir: Path, name: str) -> Path | None:
        """Locate a named file in the artifact directory (handles nesting)."""
        for path in artifact_dir.rglob(name):
            if path.is_file():
                return path
        return None
