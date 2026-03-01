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
        vhal_dir: Path | None = None,
    ) -> Iterator[str]:
        """Push binaries to emulator and restart VHAL service.

        Args:
            artifact_dir: Directory containing downloaded build artifacts.
            artifact_manager: Optional ArtifactManager for file lookup.
            vhal_dir: Generator output dir containing impl/bridge/DefaultProperties.json.

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

            # Set permissions for binaries (not json/so)
            if not name.endswith((".json", ".so")):
                self._shell.run(
                    ["adb", "shell", "chmod", "755", device_path], timeout=10
                )

            yield f"PASS {name}"

        # Push generated DefaultProperties.json (with numeric propertyId fields).
        # This is the generator's output, NOT the AOSP stock DefaultProperties.json.
        dp_pushed = False
        dp_local = None
        if vhal_dir is not None:
            dp_local = vhal_dir / "impl" / "bridge" / "DefaultProperties.json"
        if dp_local and dp_local.is_file():
            dp_device = f"{config.DEVICE_CONFIG_DIR}/DefaultProperties.json"
            yield f"Pushing generated DefaultProperties.json → {dp_device}"
            rc, _, stderr = self._shell.run(
                ["adb", "push", str(dp_local), dp_device], timeout=15,
            )
            if rc != 0:
                yield f"FAIL DefaultProperties.json push: {stderr.strip()}"
                all_ok = False
            else:
                yield "PASS DefaultProperties.json"
                dp_pushed = True
        else:
            yield "WARNING: Generated DefaultProperties.json not found — properties may not load"

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

        # Push privapp-permissions so the test app's CAR_* permissions are allowed
        privapp_pushed = False
        privapp_local = None
        if vhal_dir is not None:
            privapp_local = vhal_dir / "impl" / "bridge" / "privapp-permissions-vhaltest.xml"
        if privapp_local and privapp_local.is_file():
            device_path = "/system/etc/permissions/privapp-permissions-vhaltest.xml"
            yield f"Pushing privapp-permissions → {device_path}"
            rc, _, stderr = self._shell.run(
                ["adb", "push", str(privapp_local), device_path], timeout=15,
            )
            if rc != 0:
                yield f"FAIL privapp-permissions push: {stderr.strip()}"
                all_ok = False
            else:
                yield "PASS privapp-permissions"
                privapp_pushed = True
        else:
            yield "WARNING: privapp-permissions-vhaltest.xml not found — test app may not start"

        if not all_ok:
            yield "WARNING: Some files failed to push — service may not start."

        # Full reboot so PackageManager scans priv-apps and CarService
        # initializes fresh with the new VHAL binary.
        yield "Rebooting device for clean VHAL + app registration..."
        self._shell.run(["adb", "reboot"], timeout=15)

        yield from self._wait_for_full_boot()

        self._shell.run(["adb", "root"], timeout=15)
        self._shell.run(["adb", "wait-for-device"], timeout=30)

        # Set SELinux permissive for testing (daemon fork+exec needs it)
        yield "Setting SELinux permissive..."
        self._shell.run(["adb", "shell", "setenforce", "0"], timeout=10)

        # Wait for VHAL service to come up after boot
        time.sleep(10)

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
            from . import config
            udp_port = config.EMULATOR_UDP_FORWARD_PORT
            yield "ERROR: No device/emulator found.  Start one with:"
            yield (
                f"  emulator -avd automotive -writable-system "
                f"-qemu -net user,hostfwd=udp::{udp_port}-:{udp_port} &"
            )
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
            yield from self._wait_for_full_boot()
            self._shell.run(["adb", "root"], timeout=15)
            self._shell.run(["adb", "wait-for-device"], timeout=30)
            rc, stdout, stderr = self._shell.run(["adb", "remount"], timeout=30)
            if rc != 0:
                yield f"ERROR: adb remount failed after reboot — {stderr.strip()}"
                return
        yield "Filesystem remounted read-write."

    def _wait_for_full_boot(self, boot_timeout: int = 180) -> Iterator[str]:
        """Wait for the device to fully boot (sys.boot_completed=1).

        If the device doesn't boot within *boot_timeout* seconds, kill the
        emulator and cold-boot it.
        """
        yield f"Waiting for device to fully boot (up to {boot_timeout}s)..."
        self._shell.run(["adb", "wait-for-device"], timeout=120)

        deadline = time.time() + boot_timeout
        booted = False
        while time.time() < deadline:
            rc, stdout, _ = self._shell.run(
                ["adb", "shell", "getprop", "sys.boot_completed"], timeout=5,
            )
            if stdout.strip() == "1":
                booted = True
                break
            time.sleep(5)

        if booted:
            yield "PASS Device fully booted"
            return

        # Device stuck — kill and cold-boot
        yield "WARNING: Device stuck during boot — cold-booting emulator..."
        self._shell.run(["adb", "emu", "kill"], timeout=15)
        time.sleep(5)

        # Find the AVD name from the running emulator, fallback to "automotive"
        avd_name = "automotive"
        rc, stdout, _ = self._shell.run(
            ["adb", "shell", "getprop", "ro.boot.qemu.avd_name"], timeout=5,
        )
        if rc == 0 and stdout.strip():
            avd_name = stdout.strip()

        yield f"Starting emulator (AVD: {avd_name}) with cold boot..."
        self._shell.run(
            ["emulator", "-avd", avd_name, "-writable-system", "-no-snapshot-load"],
            timeout=5,  # Fire-and-forget — emulator runs in background
        )
        time.sleep(10)
        self._shell.run(["adb", "wait-for-device"], timeout=120)

        # Wait again for full boot
        deadline = time.time() + boot_timeout
        while time.time() < deadline:
            rc, stdout, _ = self._shell.run(
                ["adb", "shell", "getprop", "sys.boot_completed"], timeout=5,
            )
            if stdout.strip() == "1":
                yield "PASS Device fully booted (cold boot)"
                return
            time.sleep(5)

        yield "ERROR: Device failed to boot even after cold boot"

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
