"""Incremental build on a pre-existing GCP Compute Engine instance."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from ..shell.runner import ShellRunner
from . import config


class GcpBuilder:
    """Sync code to a GCP instance, run incremental mma, pull artifacts back."""

    def __init__(
        self,
        *,
        instance_name: str,
        zone: str,
        project: str | None = None,
        shell: ShellRunner | None = None,
    ) -> None:
        self._instance = instance_name
        self._zone = zone
        self._project = project
        self._shell = shell or ShellRunner()

    # -- helpers --------------------------------------------------------

    def _gcloud_base(self) -> list[str]:
        """Return base gcloud args including --project if set."""
        cmd = ["gcloud"]
        if self._project:
            cmd += ["--project", self._project]
        return cmd

    # -- public checks --------------------------------------------------

    def check_gcloud(self) -> Iterator[str]:
        """Verify gcloud CLI is installed and authenticated."""
        rc, account, stderr = self._shell.run(
            ["gcloud", "info", "--format=value(config.account)"], timeout=15,
        )
        if rc != 0:
            yield f"ERROR: gcloud CLI not available — {stderr.strip()}"
            return

        rc2, project, _ = self._shell.run(
            ["gcloud", "config", "get-value", "project"], timeout=15,
        )
        account = account.strip()
        project = project.strip()
        if not account:
            yield "ERROR: gcloud not authenticated — run `gcloud auth login`"
            return

        yield f"PASS gcloud configured (account: {account}, project: {project})"

    def check_instance(self) -> Iterator[str]:
        """Verify the instance exists and is RUNNING."""
        cmd = self._gcloud_base() + [
            "compute", "instances", "describe", self._instance,
            "--zone", self._zone, "--quiet", "--format=value(status)",
        ]
        rc, stdout, stderr = self._shell.run(cmd, timeout=15)
        if rc != 0:
            yield f"ERROR: Instance '{self._instance}' not found — {stderr.strip()}"
            return

        status = stdout.strip()
        if status == "RUNNING":
            yield f"PASS Instance '{self._instance}' is RUNNING"
        else:
            yield f"FAIL Instance '{self._instance}' is {status} (expected RUNNING)"

    def get_instance_status(self) -> str:
        """Return raw instance status string, or 'NOT_FOUND'/'GCLOUD_ERROR'."""
        rc, stdout, stderr = self._shell.run(
            self._gcloud_base() + [
                "compute", "instances", "describe", self._instance,
                "--zone", self._zone, "--quiet", "--format=value(status)",
            ],
            timeout=15,
        )
        if rc != 0:
            if "not found" in stderr.lower() or "Could not fetch" in stderr:
                return "NOT_FOUND"
            return "GCLOUD_ERROR"
        return stdout.strip()

    def start_instance(self) -> Iterator[str]:
        """Start the instance."""
        cmd = self._gcloud_base() + [
            "compute", "instances", "start", self._instance,
            "--zone", self._zone, "--quiet",
        ]
        yield f"Starting instance '{self._instance}' ..."
        rc, _, stderr = self._shell.run(cmd, timeout=120)
        if rc != 0:
            yield f"ERROR: Failed to start instance — {stderr.strip()}"
            return
        yield f"PASS Instance '{self._instance}' started"

    def stop_instance(self) -> Iterator[str]:
        """Stop the instance (saves cost — disk charges still apply)."""
        cmd = self._gcloud_base() + [
            "compute", "instances", "stop", self._instance,
            "--zone", self._zone, "--quiet",
        ]
        yield f"Stopping instance '{self._instance}' ..."
        rc, _, stderr = self._shell.run(cmd, timeout=120)
        if rc != 0:
            yield f"ERROR: Failed to stop instance — {stderr.strip()}"
            return
        yield f"PASS Instance '{self._instance}' stopped"

    # -- standalone push (no build) -------------------------------------

    def push_source(self, vhal_dir: Path) -> Iterator[str]:
        """Push generated VHAL source to the GCP instance (no build).

        Runs gcloud/instance checks, then syncs bridge/ and vhal/ dirs.
        """
        yield "=== Push VHAL Source ==="

        for line in self.check_gcloud():
            yield line
            if line.startswith("ERROR:"):
                return

        for line in self.check_instance():
            yield line
            if line.startswith(("ERROR:", "FAIL")):
                return

        for line in self._sync_code(vhal_dir):
            yield line
            if line.startswith("ERROR:"):
                return

        yield "PASS VHAL source pushed to instance"

    # -- internal pipeline steps ----------------------------------------

    def _sync_code(self, vhal_dir: Path) -> Iterator[str]:
        """SCP generated bridge code and patched vhal files to the instance.

        The generator produces files in two locations:
        - impl/bridge/ — generated templates + SDK files
        - impl/vhal/  — patched VehicleService.cpp and Android.bp

        Both must be uploaded to the matching remote paths.
        """
        # Upload impl/bridge/ (generated templates + SDK files)
        bridge_local = vhal_dir / "impl" / "bridge"
        if not bridge_local.is_dir():
            yield f"ERROR: Bridge directory not found at {bridge_local}"
            return

        yield f"Syncing bridge code from {bridge_local} ..."
        cmd = self._gcloud_base() + [
            "compute", "scp", "--recurse",
            f"{bridge_local}/",
            f"{self._instance}:{config.GCP_REMOTE_VHAL_PATH}/",
            "--zone", self._zone, "--quiet",
        ]
        rc, _, stderr = self._shell.run(
            cmd, timeout=config.GCP_INCREMENTAL_BUILD_TIMEOUT,
        )
        if rc != 0:
            yield f"ERROR: SCP upload of bridge/ failed — {stderr.strip()}"
            return
        yield "PASS Bridge code synced"

        # Upload impl/vhal/ (patched VehicleService.cpp + Android.bp)
        vhal_local = vhal_dir / "impl" / "vhal"
        if not vhal_local.is_dir():
            yield f"ERROR: VHAL directory not found at {vhal_local}"
            return

        yield f"Syncing patched vhal files from {vhal_local} ..."
        cmd = self._gcloud_base() + [
            "compute", "scp", "--recurse",
            f"{vhal_local}/",
            f"{self._instance}:{config.GCP_REMOTE_BUILD_PATH}/",
            "--zone", self._zone, "--quiet",
        ]
        rc, _, stderr = self._shell.run(
            cmd, timeout=config.GCP_INCREMENTAL_BUILD_TIMEOUT,
        )
        if rc != 0:
            yield f"ERROR: SCP upload of vhal/ failed — {stderr.strip()}"
            return
        yield "PASS Patched vhal files synced"

    def _run_build(self) -> Iterator[str]:
        """SSH into the instance and run incremental mma."""
        yield "Running incremental build (mma) ..."
        build_script = (
            "cd ~/aosp && source build/envsetup.sh && "
            f"lunch {config.DEFAULT_LUNCH_TARGET} && "
            f"cd {config.GCP_REMOTE_BUILD_PATH} && "
            "mma -j$(nproc) 2>&1"
        )
        cmd = self._gcloud_base() + [
            "compute", "ssh", self._instance,
            "--zone", self._zone, "--quiet", "--",
            "bash", "-lc", build_script,
        ]
        last_line = ""
        for line in self._shell.run_streaming(cmd):
            yield f"  {line}"
            last_line = line

        if "Exit code:" in last_line:
            yield "FAIL Incremental build failed"
        else:
            yield "PASS Incremental build succeeded"

    def _pull_artifacts(self, artifact_dir: Path) -> Iterator[str]:
        """SCP the 3 build artifacts back to the local machine."""
        yield f"Pulling artifacts to {artifact_dir} ..."
        artifact_dir.mkdir(parents=True, exist_ok=True)

        for name, rel_path in config.GCP_ARTIFACT_REMOTE_PATHS.items():
            remote = f"{self._instance}:{config.GCP_PRODUCT_OUT_PATH}/{rel_path}"
            local = artifact_dir / name
            cmd = self._gcloud_base() + [
                "compute", "scp",
                remote, str(local),
                "--zone", self._zone, "--quiet",
            ]
            rc, _, stderr = self._shell.run(cmd, timeout=120)
            if rc != 0:
                yield f"FAIL Failed to pull {name} — {stderr.strip()}"
                return
            yield f"PASS Pulled {name}"

        yield "PASS All artifacts pulled"

    def _write_build_info(self, artifact_dir: Path) -> None:
        """Write a local build-info.json for the incremental build."""
        info = {
            "build_type": "incremental",
            "instance": self._instance,
            "zone": self._zone,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        (artifact_dir / "build-info.json").write_text(
            json.dumps(info, indent=2) + "\n"
        )

    # -- main pipeline --------------------------------------------------

    def build_incremental(
        self, *, vhal_dir: Path, artifact_dir: Path,
    ) -> Iterator[str]:
        """Full incremental pipeline: check → sync → build → pull."""
        yield "=== Stage 2: Check GCP Instance ==="
        for line in self.check_gcloud():
            yield line
            if line.startswith("ERROR:"):
                return

        for line in self.check_instance():
            yield line
            if line.startswith(("FAIL", "ERROR:")):
                return

        yield ""
        yield "=== Stage 3: Sync & Build (Incremental) ==="
        for line in self._sync_code(vhal_dir):
            yield line
            if line.startswith("ERROR:"):
                return

        for line in self._run_build():
            yield line
            if line.startswith("FAIL"):
                return

        yield ""
        yield "=== Stage 4: Pull Artifacts ==="
        for line in self._pull_artifacts(artifact_dir):
            yield line
            if line.startswith("FAIL"):
                return

        self._write_build_info(artifact_dir)
        yield "PASS build-info.json written"
