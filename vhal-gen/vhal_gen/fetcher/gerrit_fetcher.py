"""Sparse git clone of VHAL source from Android Gerrit."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Iterator

logger = logging.getLogger(__name__)


class GerritFetcher:
    """Fetches VHAL AIDL source from Android Gerrit via sparse checkout."""

    GERRIT_URL = "https://android.googlesource.com/platform/hardware/interfaces"
    VHAL_SUBDIR = "automotive/vehicle/aidl"

    def fetch_vhal(
        self,
        target_dir: Path,
        tag: str = "android14-release",
        force: bool = False,
    ) -> Iterator[str]:
        """Sparse-clone just the VHAL directory from Gerrit.

        Yields status lines as the clone progresses.
        The final yielded line starts with "DONE:" followed by the path.

        Args:
            target_dir: Parent directory for the clone.
            tag: Git tag to fetch (e.g. 'android14-release').
            force: If True, re-clone even if directory exists.

        Yields:
            Status/progress lines for streaming display.
        """
        clone_dir = target_dir / "aosp-vhal" / tag
        vhal_path = clone_dir / self.VHAL_SUBDIR

        if vhal_path.exists() and not force:
            yield f"Using cached VHAL source at {vhal_path}"
            yield f"DONE:{vhal_path}"
            return

        clone_dir.mkdir(parents=True, exist_ok=True)

        steps = [
            (["git", "init"], "Initializing repository..."),
            (
                ["git", "remote", "add", "origin", self.GERRIT_URL],
                "Adding Gerrit remote...",
            ),
            (
                ["git", "sparse-checkout", "set", self.VHAL_SUBDIR],
                f"Setting sparse checkout to {self.VHAL_SUBDIR}...",
            ),
            (
                ["git", "fetch", "--depth=1", "origin", f"refs/tags/{tag}"],
                f"Fetching tag {tag} (sparse, ~50MB)...",
            ),
            (["git", "checkout", "FETCH_HEAD"], "Checking out source..."),
        ]

        for cmd, status_msg in steps:
            yield status_msg
            try:
                result = subprocess.run(
                    cmd,
                    cwd=str(clone_dir),
                    capture_output=True,
                    text=True,
                    timeout=300,
                )
                if result.stdout.strip():
                    for line in result.stdout.strip().splitlines():
                        yield f"  {line}"
                if result.returncode != 0:
                    err = result.stderr.strip()
                    # git remote add fails if remote already exists — skip
                    if "already exists" in err:
                        yield "  (remote already exists, continuing)"
                        continue
                    yield f"ERROR: {err}"
                    return
            except subprocess.TimeoutExpired:
                yield "ERROR: Command timed out after 300s"
                return
            except FileNotFoundError:
                yield "ERROR: git is not installed or not in PATH"
                return

        if vhal_path.exists():
            yield f"VHAL source ready at {vhal_path}"
            yield f"DONE:{vhal_path}"
        else:
            yield f"WARNING: Expected path {vhal_path} not found after clone"
            yield f"DONE:{clone_dir}"

    def list_android14_tags(self) -> list[str]:
        """List available android-14* tags via git ls-remote.

        Returns:
            Sorted list of tag names matching android-14*.
            Returns a default list if git ls-remote fails.
        """
        try:
            result = subprocess.run(
                ["git", "ls-remote", "--tags", self.GERRIT_URL, "android-14*"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                tags = []
                for line in result.stdout.strip().splitlines():
                    ref = line.split("\t")[-1]
                    tag_name = ref.replace("refs/tags/", "")
                    if not tag_name.endswith("^{}"):
                        tags.append(tag_name)
                return sorted(tags, reverse=True)
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        # Fallback defaults
        return [
            "android-14.0.0_r75",
            "android-14.0.0_r74",
            "android-14.0.0_r67",
        ]
