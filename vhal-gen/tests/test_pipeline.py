"""Unit tests for the deploy-test pipeline modules.

All external commands (gh, adb, git) are mocked via a fake ShellRunner.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from vhal_gen.pipeline import config
from vhal_gen.pipeline.artifact_manager import ArtifactManager
from vhal_gen.pipeline.build_trigger import BuildTrigger
from vhal_gen.pipeline.emulator_deployer import EmulatorDeployer
from vhal_gen.pipeline.property_verifier import PropertyVerifier


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class FakeShellRunner:
    """Records calls and returns pre-configured responses."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self._responses: dict[str, tuple[int, str, str]] = {}

    def set_response(self, key: str, rc: int, stdout: str = "", stderr: str = "") -> None:
        """Register a response keyed by substring match on the command."""
        self._responses[key] = (rc, stdout, stderr)

    def run(
        self, cmd: list[str], cwd: Path | None = None, timeout: int = 120
    ) -> tuple[int, str, str]:
        self.calls.append(cmd)
        cmd_str = " ".join(cmd)
        for key, response in self._responses.items():
            if key in cmd_str:
                return response
        # Default: success with empty output
        return 0, "", ""

    def run_streaming(self, cmd: list[str], cwd: Path | None = None):
        self.calls.append(cmd)
        yield from []


def _collect(iterator) -> list[str]:
    return list(iterator)


# ---------------------------------------------------------------------------
# BuildTrigger
# ---------------------------------------------------------------------------

class TestBuildTrigger:

    def test_trigger_aborts_when_no_repo(self):
        shell = FakeShellRunner()
        shell.set_response("gh repo view", 1, stderr="not a git repository")
        trigger = BuildTrigger(shell)

        lines = _collect(trigger.trigger_and_wait())
        assert any("ERROR:" in l for l in lines)
        assert any("gh auth login" in l for l in lines)

    def test_trigger_reports_run_id(self):
        shell = FakeShellRunner()
        shell.set_response("gh repo view", 0, stdout="owner/repo")
        shell.set_response("gh workflow run", 0)
        shell.set_response(
            "gh run list",
            0,
            stdout=json.dumps([{"databaseId": 99887766, "status": "queued"}]),
        )
        shell.set_response(
            "gh run view",
            0,
            stdout=json.dumps({"status": "completed", "conclusion": "success"}),
        )
        trigger = BuildTrigger(shell)

        lines = _collect(trigger.trigger_and_wait())
        assert any("99887766" in l for l in lines)
        assert any("PASS" in l for l in lines)

    def test_trigger_reports_failure(self):
        shell = FakeShellRunner()
        shell.set_response("gh repo view", 0, stdout="owner/repo")
        shell.set_response("gh workflow run", 0)
        shell.set_response(
            "gh run list",
            0,
            stdout=json.dumps([{"databaseId": 111, "status": "queued"}]),
        )
        shell.set_response(
            "gh run view",
            0,
            stdout=json.dumps({"status": "completed", "conclusion": "failure"}),
        )
        trigger = BuildTrigger(shell)

        lines = _collect(trigger.trigger_and_wait())
        assert any("FAIL" in l for l in lines)


# ---------------------------------------------------------------------------
# ArtifactManager
# ---------------------------------------------------------------------------

class TestArtifactManager:

    def test_verify_all_present(self, tmp_path: Path):
        # Create all expected artifact files
        for name in config.ARTIFACT_FILES:
            (tmp_path / name).write_text("content")

        shell = FakeShellRunner()
        mgr = ArtifactManager(shell)
        lines = _collect(mgr.verify_dir(tmp_path))

        pass_lines = [l for l in lines if l.startswith("PASS")]
        assert len(pass_lines) == len(config.ARTIFACT_FILES)
        assert any("All artifacts verified" in l for l in lines)

    def test_verify_missing_file(self, tmp_path: Path):
        # Create only some files
        (tmp_path / "build-info.json").write_text("{}")

        shell = FakeShellRunner()
        mgr = ArtifactManager(shell)
        lines = _collect(mgr.verify_dir(tmp_path))

        fail_lines = [l for l in lines if l.startswith("FAIL")]
        assert len(fail_lines) >= 1
        assert any("WARNING" in l for l in lines)

    def test_download_retries_on_failure(self, tmp_path: Path):
        shell = FakeShellRunner()
        shell.set_response("gh run download", 1, stderr="network error")
        mgr = ArtifactManager(shell)

        lines = _collect(mgr.download("123", tmp_path))
        # Should see retry messages and final failure
        assert any("FAIL" in l for l in lines)
        download_calls = [c for c in shell.calls if "download" in " ".join(c)]
        assert len(download_calls) == config.ARTIFACT_DOWNLOAD_RETRIES

    def test_find_artifact_file_nested(self, tmp_path: Path):
        nested = tmp_path / "vhal-build-42"
        nested.mkdir()
        (nested / "flync-daemon").write_text("binary")

        shell = FakeShellRunner()
        mgr = ArtifactManager(shell)
        result = mgr.find_artifact_file(tmp_path, "flync-daemon")
        assert result is not None
        assert result.name == "flync-daemon"


# ---------------------------------------------------------------------------
# EmulatorDeployer
# ---------------------------------------------------------------------------

class TestEmulatorDeployer:

    def test_deploy_fails_without_device(self):
        shell = FakeShellRunner()
        # adb devices returns header only (no device)
        shell.set_response("adb devices", 0, stdout="List of devices attached\n")
        deployer = EmulatorDeployer(shell)

        lines = _collect(deployer.deploy(Path("/fake/artifacts")))
        assert any("ERROR:" in l and "No device" in l for l in lines)

    def test_deploy_pushes_all_files(self, tmp_path: Path):
        # Create artifact files
        for name in config.DEVICE_PATHS:
            (tmp_path / name).write_text("binary")

        shell = FakeShellRunner()
        shell.set_response("adb devices", 0, stdout="List of devices attached\nemulator-5554\tdevice\n")
        shell.set_response("adb root", 0, stdout="adbd is already running as root")
        shell.set_response("adb remount", 0)
        shell.set_response("adb push", 0)
        shell.set_response("adb shell chmod", 0)
        shell.set_response("adb shell chcon", 0)
        shell.set_response("adb shell stop", 0)
        shell.set_response("adb shell start", 0)
        shell.set_response("adb shell getprop", 0, stdout="running")
        shell.set_response("adb wait-for-device", 0)
        deployer = EmulatorDeployer(shell)

        lines = _collect(deployer.deploy(tmp_path))
        pass_lines = [l for l in lines if l.startswith("PASS")]
        # One PASS per pushed file + VINTF manifest + service running
        assert len(pass_lines) == len(config.DEVICE_PATHS) + 2

    def test_deploy_reports_missing_artifact(self, tmp_path: Path):
        # Empty artifact directory
        shell = FakeShellRunner()
        shell.set_response("adb devices", 0, stdout="List of devices attached\nemulator-5554\tdevice\n")
        shell.set_response("adb root", 0, stdout="adbd is already running as root")
        shell.set_response("adb remount", 0)
        shell.set_response("adb shell stop", 0)
        shell.set_response("adb shell start", 0)
        shell.set_response("adb shell getprop", 0, stdout="running")
        shell.set_response("adb wait-for-device", 0)
        deployer = EmulatorDeployer(shell)

        lines = _collect(deployer.deploy(tmp_path))
        fail_lines = [l for l in lines if l.startswith("FAIL")]
        assert len(fail_lines) >= 1


# ---------------------------------------------------------------------------
# PropertyVerifier
# ---------------------------------------------------------------------------

class TestPropertyVerifier:

    def test_verify_all_pass(self, tmp_path: Path):
        props = {
            "apiVersion": 1,
            "properties": [
                {"property": 0x11400400},
                {"property": 0x11400401},
            ],
        }
        props_file = tmp_path / "DefaultProperties.json"
        props_file.write_text(json.dumps(props))

        shell = FakeShellRunner()
        shell.set_response("car_service", 0, stdout="value: 0")
        verifier = PropertyVerifier(shell)

        lines = _collect(verifier.verify(props_file))
        assert any("All 2 properties verified" in l for l in lines)

    def test_verify_reports_failure(self, tmp_path: Path):
        props = {
            "apiVersion": 1,
            "properties": [
                {"property": 0x11400400},
            ],
        }
        props_file = tmp_path / "DefaultProperties.json"
        props_file.write_text(json.dumps(props))

        shell = FakeShellRunner()
        shell.set_response("car_service", 1, stderr="property not found")
        verifier = PropertyVerifier(shell)

        lines = _collect(verifier.verify(props_file))
        assert any("FAIL" in l for l in lines)
        assert any("1 properties failed" in l for l in lines)

    def test_verify_missing_file(self):
        shell = FakeShellRunner()
        verifier = PropertyVerifier(shell)
        lines = _collect(verifier.verify(Path("/nonexistent/file.json")))
        assert any("ERROR:" in l for l in lines)

    def test_verify_malformed_json(self, tmp_path: Path):
        props_file = tmp_path / "DefaultProperties.json"
        props_file.write_text("not json{{{")

        shell = FakeShellRunner()
        verifier = PropertyVerifier(shell)
        lines = _collect(verifier.verify(props_file))
        assert any("ERROR:" in l for l in lines)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

class TestConfig:

    def test_device_paths_cover_all_artifacts(self):
        """Device paths should cover all non-metadata artifact files."""
        binary_artifacts = [f for f in config.ARTIFACT_FILES if f != "build-info.json"]
        for name in binary_artifacts:
            assert name in config.DEVICE_PATHS, f"{name} missing from DEVICE_PATHS"

    def test_timeout_is_reasonable(self):
        assert config.BUILD_TIMEOUT_SECONDS >= 3600  # at least 1 hour
        assert config.BUILD_TIMEOUT_SECONDS <= 14400  # at most 4 hours
