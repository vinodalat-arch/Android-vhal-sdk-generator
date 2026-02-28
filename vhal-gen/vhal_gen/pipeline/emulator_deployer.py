"""Push build artifacts to a running Android automotive emulator via adb."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Iterator

from ..shell.runner import ShellRunner
from . import config


class EmulatorDeployer:
    """Deploys VHAL binaries and config to an emulator over adb."""

    def __init__(self, shell: ShellRunner | None = None) -> None:
        self._shell = shell or ShellRunner()

    def deploy(
        self,
        artifact_dir: Path,
        artifact_manager: object | None = None,
    ) -> Iterator[str]:
        """Push binaries to emulator and restart VHAL service.

        Args:
            artifact_dir: Directory containing downloaded build artifacts.
            artifact_manager: Optional ArtifactManager for file lookup.

        Yields:
            Status lines.
        """
        # Check emulator is connected
        yield from self._check_device()

        # adb root
        yield "Requesting adb root..."
        rc, stdout, _ = self._shell.run(["adb", "root"], timeout=15)
        if rc != 0 and "already running as root" not in stdout:
            yield "ERROR: adb root failed — is the emulator a userdebug build?"
            return

        # Wait for device after root restart
        self._shell.run(["adb", "wait-for-device"], timeout=30)

        # adb remount
        yield from self._remount()

        # Stop VHAL service before pushing
        yield f"Stopping {config.VHAL_SERVICE_NAME}..."
        self._shell.run(
            ["adb", "shell", "stop", config.VHAL_SERVICE_NAME], timeout=15
        )

        # Push each artifact to its device path
        all_ok = True
        for name, device_path in config.DEVICE_PATHS.items():
            local_path = self._find_file(artifact_dir, name, artifact_manager)
            if local_path is None:
                yield f"FAIL {name} — not found in {artifact_dir}"
                all_ok = False
                continue

            yield f"Pushing {name} → {device_path}"
            rc, _, stderr = self._shell.run(
                ["adb", "push", str(local_path), device_path], timeout=60
            )
            if rc != 0:
                yield f"FAIL push {name}: {stderr.strip()}"
                all_ok = False
                continue

            # Set permissions for binaries (not json)
            if not name.endswith(".json"):
                self._shell.run(
                    ["adb", "shell", "chmod", "755", device_path], timeout=10
                )
                self._shell.run(
                    ["adb", "shell", "chcon", config.SELINUX_CONTEXT, device_path],
                    timeout=10,
                )

            yield f"PASS {name}"

        # Push updated VINTF manifest (V2 → V3) so framework accepts our binary
        if config.VINTF_MANIFEST_V3 and config.DEVICE_VINTF_MANIFEST_PATH:
            import tempfile
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".xml", delete=False,
            ) as f:
                f.write(config.VINTF_MANIFEST_V3)
                manifest_tmp = f.name
            yield f"Pushing VINTF manifest → {config.DEVICE_VINTF_MANIFEST_PATH}"
            rc, _, stderr = self._shell.run(
                ["adb", "push", manifest_tmp, config.DEVICE_VINTF_MANIFEST_PATH],
                timeout=15,
            )
            if rc != 0:
                yield f"FAIL VINTF manifest push: {stderr.strip()}"
                all_ok = False
            else:
                yield "PASS VINTF manifest updated (V3)"

        if not all_ok:
            yield "WARNING: Some files failed to push — service may not start."

        # Start VHAL service
        yield f"Starting {config.VHAL_SERVICE_NAME}..."
        self._shell.run(
            ["adb", "shell", "start", config.VHAL_SERVICE_NAME], timeout=15
        )

        # Brief wait for service to initialize
        time.sleep(3)

        # Verify service is running
        rc, stdout, _ = self._shell.run(
            ["adb", "shell", "getprop", f"init.svc.{config.VHAL_SERVICE_NAME}"],
            timeout=10,
        )
        svc_state = stdout.strip()
        if svc_state == "running":
            yield f"PASS {config.VHAL_SERVICE_NAME} is running"
        else:
            yield f"FAIL {config.VHAL_SERVICE_NAME} state: {svc_state or 'unknown'}"

    def _check_device(self) -> Iterator[str]:
        """Verify an emulator/device is connected."""
        rc, stdout, _ = self._shell.run(["adb", "devices"], timeout=10)
        lines = [
            line for line in stdout.strip().splitlines()[1:]  # skip header
            if line.strip() and "device" in line
        ]
        if not lines:
            yield "ERROR: No device/emulator found.  Start one with:"
            yield "  emulator -avd automotive -no-snapshot &"
            yield "  adb wait-for-device"
            return
        device_id = lines[0].split()[0]
        yield f"Device connected: {device_id}"

    def _remount(self) -> Iterator[str]:
        """adb remount, handling verity if needed."""
        rc, stdout, stderr = self._shell.run(["adb", "remount"], timeout=30)
        combined = stdout + stderr
        if "verity" in combined.lower() and "disable" in combined.lower():
            yield "Verity is enabled — disabling and rebooting..."
            self._shell.run(["adb", "disable-verity"], timeout=15)
            self._shell.run(["adb", "reboot"], timeout=15)
            yield f"Waiting {config.ADB_REBOOT_WAIT_SECONDS}s for reboot..."
            time.sleep(config.ADB_REBOOT_WAIT_SECONDS)
            self._shell.run(["adb", "wait-for-device"], timeout=120)
            self._shell.run(["adb", "root"], timeout=15)
            self._shell.run(["adb", "wait-for-device"], timeout=30)
            rc, stdout, stderr = self._shell.run(["adb", "remount"], timeout=30)
            if rc != 0:
                yield f"ERROR: adb remount failed after reboot — {stderr.strip()}"
                return
        yield "Filesystem remounted read-write."

    @staticmethod
    def _find_file(
        artifact_dir: Path,
        name: str,
        artifact_manager: object | None,
    ) -> Path | None:
        """Locate a file in the artifact directory."""
        if artifact_manager is not None and hasattr(artifact_manager, "find_artifact_file"):
            result = artifact_manager.find_artifact_file(artifact_dir, name)
            if result:
                return result

        # Fallback: search recursively
        for path in artifact_dir.rglob(name):
            if path.is_file():
                return path
        return None
