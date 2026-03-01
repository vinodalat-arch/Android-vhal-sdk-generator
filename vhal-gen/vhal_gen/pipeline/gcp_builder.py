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
        force_sdk_sync: bool = False,
    ) -> None:
        self._instance = instance_name
        self._zone = zone
        self._project = project
        self._shell = shell or ShellRunner()
        self._force_sdk_sync = force_sdk_sync

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

        yield f"PASS gcloud configured (project: {project})"

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

        Smart sync: only uploads the 13 generated files each run.  The static
        SDK directory (~464 files) is uploaded only when missing on the remote
        or when ``force_sdk_sync`` is set.
        """
        bridge_local = vhal_dir / "impl" / "bridge"
        if not bridge_local.is_dir():
            yield f"ERROR: Bridge directory not found at {bridge_local}"
            return

        # --- Step 1: SDK sync (skip if already present on remote) ----------
        sdk_remote = f"{config.GCP_REMOTE_VHAL_PATH}/sdk"
        check_cmd = self._gcloud_base() + [
            "compute", "ssh", self._instance,
            "--zone", self._zone, "--quiet", "--",
            f"test -d {sdk_remote} && echo EXISTS || echo MISSING",
        ]
        rc, stdout, _ = self._shell.run(check_cmd, timeout=30)
        sdk_present = "EXISTS" in stdout

        if self._force_sdk_sync or not sdk_present:
            sdk_local = bridge_local / "sdk"
            if sdk_local.is_dir():
                reason = "forced" if self._force_sdk_sync else "missing on remote"
                yield f"Uploading SDK ({reason}) ..."
                mkdir_cmd = self._gcloud_base() + [
                    "compute", "ssh", self._instance,
                    "--zone", self._zone, "--quiet", "--",
                    f"mkdir -p {sdk_remote}",
                ]
                self._shell.run(mkdir_cmd, timeout=30)

                cmd = self._gcloud_base() + [
                    "compute", "scp", "--recurse",
                    str(sdk_local),
                    f"{self._instance}:{config.GCP_REMOTE_VHAL_PATH}/",
                    "--zone", self._zone, "--quiet",
                ]
                rc, _, stderr = self._shell.run(
                    cmd, timeout=config.GCP_INCREMENTAL_BUILD_TIMEOUT,
                )
                if rc != 0:
                    yield f"ERROR: SCP upload of sdk/ failed — {stderr.strip()}"
                    return
                yield "PASS SDK synced"
            else:
                yield "SKIP No local sdk/ directory to upload"
        else:
            yield "SKIP SDK already present on remote"

        # --- Step 2: Upload generated bridge files individually ------------
        yield f"Syncing {len(config.GCP_GENERATED_BRIDGE_FILES)} generated files ..."
        # Ensure test-apk/ subdir exists on remote
        mkdir_cmd = self._gcloud_base() + [
            "compute", "ssh", self._instance,
            "--zone", self._zone, "--quiet", "--",
            f"mkdir -p {config.GCP_REMOTE_VHAL_PATH}/test-apk",
        ]
        self._shell.run(mkdir_cmd, timeout=30)

        for filename in config.GCP_GENERATED_BRIDGE_FILES:
            local_file = bridge_local / filename
            if not local_file.exists():
                continue  # Optional file not generated this run
            remote = f"{self._instance}:{config.GCP_REMOTE_VHAL_PATH}/{filename}"
            cmd = self._gcloud_base() + [
                "compute", "scp",
                str(local_file), remote,
                "--zone", self._zone, "--quiet",
            ]
            rc, _, stderr = self._shell.run(
                cmd, timeout=config.GCP_INCREMENTAL_BUILD_TIMEOUT,
            )
            if rc != 0:
                yield f"ERROR: SCP upload of {filename} failed — {stderr.strip()}"
                return
        yield "PASS Generated bridge files synced"

        # --- Step 3: Upload patched vhal files (unchanged) -----------------
        vhal_local = vhal_dir / "impl" / "vhal"
        if not vhal_local.is_dir():
            yield f"ERROR: VHAL directory not found at {vhal_local}"
            return

        patched_files = [
            vhal_local / "src" / "VehicleService.cpp",
            vhal_local / "Android.bp",
        ]
        for local_file in patched_files:
            if not local_file.exists():
                yield f"ERROR: Patched file not found at {local_file}"
                return

            rel = local_file.relative_to(vhal_local)
            remote = f"{self._instance}:{config.GCP_REMOTE_BUILD_PATH}/{rel}"

            yield f"Syncing {rel} ..."
            cmd = self._gcloud_base() + [
                "compute", "scp",
                str(local_file), remote,
                "--zone", self._zone, "--quiet",
            ]
            rc, _, stderr = self._shell.run(
                cmd, timeout=config.GCP_INCREMENTAL_BUILD_TIMEOUT,
            )
            if rc != 0:
                yield f"ERROR: SCP upload of {rel} failed — {stderr.strip()}"
                return
        yield "PASS Patched vhal files synced"

    def _run_build(self) -> Iterator[str]:
        """SSH into the instance and run incremental mma."""
        yield "Running VHAL build (mma) ..."
        build_script = (
            "cd ~/aosp && source build/envsetup.sh && "
            f"lunch {config.DEFAULT_LUNCH_TARGET} && "
            f"cd {config.GCP_REMOTE_BUILD_PATH} && "
            "mma -j$(nproc) 2>&1"
        )
        cmd = self._gcloud_base() + [
            "compute", "ssh", self._instance,
            "--zone", self._zone, "--quiet",
            "--", build_script,
        ]
        last_line = ""
        for line in self._shell.run_streaming(cmd):
            yield f"  {line}"
            last_line = line

        if "Exit code:" in last_line:
            yield "FAIL VHAL build failed"
        else:
            yield "PASS VHAL build succeeded"

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
