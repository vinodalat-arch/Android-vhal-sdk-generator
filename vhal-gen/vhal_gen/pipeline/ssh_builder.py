"""Incremental build on a remote machine via plain SSH/SCP."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from ..shell.runner import ShellRunner
from . import config


class SshBuilder:
    """Sync code to a remote host over SSH, run incremental mma, pull artifacts back.

    Drop-in alternative to GcpBuilder that uses plain ``ssh``/``scp`` instead of
    ``gcloud compute ssh``/``scp``, bypassing Zscaler/gcloud issues.
    """

    def __init__(
        self,
        *,
        ssh_host: str,
        ssh_user: str = "",
        ssh_key: str = "",
        ssh_password: str = "",
        aosp_dir: str = "~/aosp",
        shell: ShellRunner | None = None,
        force_sdk_sync: bool = False,
    ) -> None:
        self._host = ssh_host
        self._user = ssh_user
        self._key = ssh_key
        self._password = ssh_password
        self._aosp_dir = aosp_dir
        self._shell = shell or ShellRunner()
        self._force_sdk_sync = force_sdk_sync

        # Remote paths derived from aosp_dir
        self._remote_bridge = (
            f"{aosp_dir}/hardware/interfaces/automotive/vehicle/aidl/impl/bridge"
        )
        self._remote_vhal = (
            f"{aosp_dir}/hardware/interfaces/automotive/vehicle/aidl/impl/vhal"
        )
        self._remote_product_out = (
            f"{aosp_dir}/out/target/product/{config._ARCH_PRODUCT}"
        )

    # -- helpers --------------------------------------------------------

    def _target(self) -> str:
        """Return ``user@host`` or just ``host``."""
        if self._user:
            return f"{self._user}@{self._host}"
        return self._host

    def _ssh_opts(self) -> list[str]:
        """Common SSH/SCP options."""
        opts = ["-o", "StrictHostKeyChecking=no"]
        if not self._password:
            opts += ["-o", "BatchMode=yes"]
        if self._key:
            opts += ["-i", self._key]
        return opts

    def _wrap_sshpass(self, cmd: list[str]) -> list[str]:
        """Prepend sshpass if password auth is configured."""
        if self._password:
            return ["sshpass", "-p", self._password, *cmd]
        return cmd

    def _ssh_cmd(self, remote_cmd: str) -> list[str]:
        """Build an ssh command list."""
        return self._wrap_sshpass(
            ["ssh", *self._ssh_opts(), self._target(), remote_cmd]
        )

    def _scp_upload(
        self, local: str, remote: str, *, recurse: bool = False,
    ) -> list[str]:
        """Build an scp upload command list."""
        cmd = ["scp", *self._ssh_opts()]
        if recurse:
            cmd.append("-r")
        cmd += [local, f"{self._target()}:{remote}"]
        return self._wrap_sshpass(cmd)

    def _scp_download(self, remote: str, local: str) -> list[str]:
        """Build an scp download command list."""
        return self._wrap_sshpass([
            "scp", *self._ssh_opts(),
            f"{self._target()}:{remote}", local,
        ])

    # -- public checks --------------------------------------------------

    def check_connection(self) -> Iterator[str]:
        """Verify SSH connectivity, AOSP tree, and build tools on the remote host."""
        # Step 0: If password auth, verify sshpass is installed locally
        if self._password:
            rc, _, stderr = self._shell.run(["which", "sshpass"], timeout=5)
            if rc != 0:
                yield "ERROR: sshpass not installed — run `brew install sshpass` (or `apt install sshpass`)"
                return

        # Step 1: SSH login
        cmd = self._ssh_cmd("echo ok")
        rc, stdout, stderr = self._shell.run(cmd, timeout=15)
        if rc != 0:
            yield f"ERROR: SSH connection to {self._target()} failed — {stderr.strip()}"
            return
        if "ok" not in stdout:
            yield f"ERROR: Unexpected SSH response — {stdout.strip()}"
            return
        yield f"PASS SSH login to {self._target()} succeeded"

        # Step 2: AOSP source tree accessible
        check_aosp = self._ssh_cmd(
            f"test -f {self._aosp_dir}/build/envsetup.sh && echo AOSP_OK || echo AOSP_MISSING"
        )
        rc, stdout, _ = self._shell.run(check_aosp, timeout=15)
        if rc != 0 or "AOSP_OK" not in stdout:
            yield f"ERROR: AOSP source tree not found at {self._aosp_dir} on remote"
            return
        yield f"PASS AOSP source tree found at {self._aosp_dir}"

        # Step 3: Check build tools (lunch, mma via envsetup.sh)
        check_tools = self._ssh_cmd(
            f"cd {self._aosp_dir} && source build/envsetup.sh > /dev/null 2>&1 "
            "&& type lunch > /dev/null 2>&1 && echo TOOLS_OK || echo TOOLS_MISSING"
        )
        rc, stdout, _ = self._shell.run(check_tools, timeout=30)
        if rc != 0 or "TOOLS_OK" not in stdout:
            yield f"ERROR: AOSP build tools not available — envsetup.sh or lunch missing"
            return
        yield "PASS AOSP build tools available (envsetup.sh, lunch)"

        # Step 4: Report AOSP version info
        version_cmd = self._ssh_cmd(
            f"cat {self._aosp_dir}/build/core/build_id.mk 2>/dev/null | "
            "grep 'BUILD_ID' | head -1 || echo 'BUILD_ID unknown'"
        )
        rc, stdout, _ = self._shell.run(version_cmd, timeout=15)
        version_info = stdout.strip() if rc == 0 and stdout.strip() else "unknown"
        yield f"INFO AOSP build info: {version_info}"

    # -- standalone push (no build) -------------------------------------

    def push_source(self, vhal_dir: Path) -> Iterator[str]:
        """Push generated VHAL source to the remote host (no build)."""
        yield "=== Push VHAL Source (SSH) ==="

        for line in self.check_connection():
            yield line
            if line.startswith("ERROR:"):
                return

        for line in self._sync_code(vhal_dir):
            yield line
            if line.startswith("ERROR:"):
                return

        yield "PASS VHAL source pushed to remote host"

    # -- internal pipeline steps ----------------------------------------

    def _sync_code(self, vhal_dir: Path) -> Iterator[str]:
        """SCP generated bridge code and patched vhal files to the remote host.

        Smart sync: only uploads the 13 generated files each run.  The static
        SDK directory (~464 files) is uploaded only when missing on the remote
        or when ``force_sdk_sync`` is set.
        """
        bridge_local = vhal_dir / "impl" / "bridge"
        if not bridge_local.is_dir():
            yield f"ERROR: Bridge directory not found at {bridge_local}"
            return

        # --- Step 1: SDK sync (skip if already present on remote) ----------
        sdk_remote = f"{self._remote_bridge}/sdk"
        check_cmd = self._ssh_cmd(
            f"test -d {sdk_remote} && echo EXISTS || echo MISSING",
        )
        rc, stdout, _ = self._shell.run(check_cmd, timeout=30)
        sdk_present = "EXISTS" in stdout

        if self._force_sdk_sync or not sdk_present:
            sdk_local = bridge_local / "sdk"
            if sdk_local.is_dir():
                reason = "forced" if self._force_sdk_sync else "missing on remote"
                yield f"Uploading SDK ({reason}) ..."
                mkdir_cmd = self._ssh_cmd(f"mkdir -p {sdk_remote}")
                self._shell.run(mkdir_cmd, timeout=30)

                cmd = self._scp_upload(
                    str(sdk_local), f"{self._remote_bridge}/",
                    recurse=True,
                )
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
        mkdir_cmd = self._ssh_cmd(f"mkdir -p {self._remote_bridge}/test-apk")
        self._shell.run(mkdir_cmd, timeout=30)

        for filename in config.GCP_GENERATED_BRIDGE_FILES:
            local_file = bridge_local / filename
            if not local_file.exists():
                continue  # Optional file not generated this run
            remote = f"{self._remote_bridge}/{filename}"
            cmd = self._scp_upload(str(local_file), remote)
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
            remote = f"{self._remote_vhal}/{rel}"

            yield f"Syncing {rel} ..."
            cmd = self._scp_upload(str(local_file), remote)
            rc, _, stderr = self._shell.run(
                cmd, timeout=config.GCP_INCREMENTAL_BUILD_TIMEOUT,
            )
            if rc != 0:
                yield f"ERROR: SCP upload of {rel} failed — {stderr.strip()}"
                return
        yield "PASS Patched vhal files synced"

    def _run_build(self) -> Iterator[str]:
        """SSH into the remote host and run incremental mma."""
        yield "Running VHAL build (mma) ..."
        build_script = (
            f"cd {self._aosp_dir} && source build/envsetup.sh && "
            f"lunch {config.DEFAULT_LUNCH_TARGET} && "
            f"cd {self._remote_vhal} && "
            "mma -j$(nproc) 2>&1"
        )
        cmd = self._ssh_cmd(build_script)
        last_line = ""
        for line in self._shell.run_streaming(cmd):
            yield f"  {line}"
            last_line = line

        if "Exit code:" in last_line:
            yield "FAIL VHAL build failed"
        else:
            yield "PASS VHAL build succeeded"

    def _pull_artifacts(self, artifact_dir: Path) -> Iterator[str]:
        """SCP the build artifacts back to the local machine."""
        yield f"Pulling artifacts to {artifact_dir} ..."
        artifact_dir.mkdir(parents=True, exist_ok=True)

        for name, rel_path in config.GCP_ARTIFACT_REMOTE_PATHS.items():
            remote = f"{self._remote_product_out}/{rel_path}"
            local = artifact_dir / name
            cmd = self._scp_download(remote, str(local))
            rc, _, stderr = self._shell.run(cmd, timeout=120)
            if rc != 0:
                yield f"FAIL Failed to pull {name} — {stderr.strip()}"
                return
            yield f"PASS Pulled {name}"

        yield "PASS All artifacts pulled"

    def _write_build_info(self, artifact_dir: Path) -> None:
        """Write a local build-info.json for the SSH build."""
        info = {
            "build_type": "ssh_incremental",
            "host": self._target(),
            "aosp_dir": self._aosp_dir,
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
        yield "=== Stage 2: Check SSH Connection ==="
        for line in self.check_connection():
            yield line
            if line.startswith("ERROR:"):
                return

        yield ""
        yield "=== Stage 3: Sync & Build (SSH Incremental) ==="
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
