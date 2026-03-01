"""Unit tests for the SshBuilder incremental build pipeline."""

from __future__ import annotations

from pathlib import Path

import pytest

from vhal_gen.pipeline import config
from vhal_gen.pipeline.ssh_builder import SshBuilder


# ---------------------------------------------------------------------------
# Helpers (same pattern as test_gcp_builder.py)
# ---------------------------------------------------------------------------

class FakeShellRunner:
    """Records calls and returns pre-configured responses."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self._responses: dict[str, tuple[int, str, str]] = {}

    def set_response(self, key: str, rc: int, stdout: str = "", stderr: str = "") -> None:
        self._responses[key] = (rc, stdout, stderr)

    def run(
        self, cmd: list[str], cwd: Path | None = None, timeout: int = 120
    ) -> tuple[int, str, str]:
        self.calls.append(cmd)
        cmd_str = " ".join(cmd)
        for key, response in self._responses.items():
            if key in cmd_str:
                return response
        return 0, "", ""

    def run_streaming(self, cmd: list[str], cwd: Path | None = None):
        self.calls.append(cmd)
        yield from []


def _collect(iterator) -> list[str]:
    return list(iterator)


# ---------------------------------------------------------------------------
# check_connection
# ---------------------------------------------------------------------------

class TestCheckConnection:

    def _make_full_check_shell(self) -> FakeShellRunner:
        """Shell that passes all 4 check_connection steps."""
        shell = FakeShellRunner()
        shell.set_response("echo ok", 0, stdout="ok")
        shell.set_response("echo AOSP_OK || echo AOSP_MISSING", 0, stdout="AOSP_OK")
        shell.set_response("echo TOOLS_OK || echo TOOLS_MISSING", 0, stdout="TOOLS_OK")
        shell.set_response("build_id.mk", 0, stdout="BUILD_ID := AP2A.240905.003")
        return shell

    def test_full_check_success(self):
        shell = self._make_full_check_shell()
        builder = SshBuilder(ssh_host="10.0.0.1", shell=shell)

        lines = _collect(builder.check_connection())
        pass_lines = [l for l in lines if l.startswith("PASS")]
        assert len(pass_lines) == 3  # SSH login, AOSP tree, build tools
        assert any("SSH login" in l for l in pass_lines)
        assert any("AOSP source tree" in l for l in pass_lines)
        assert any("build tools" in l for l in pass_lines)
        # Also has INFO line with build version
        info_lines = [l for l in lines if l.startswith("INFO")]
        assert len(info_lines) == 1
        assert "BUILD_ID" in info_lines[0]

    def test_ssh_success_with_user(self):
        shell = self._make_full_check_shell()
        builder = SshBuilder(ssh_host="10.0.0.1", ssh_user="bob", shell=shell)

        lines = _collect(builder.check_connection())
        assert any("PASS" in l and "bob@10.0.0.1" in l for l in lines)
        # Verify user@host is in the command
        cmd_str = " ".join(shell.calls[0])
        assert "bob@10.0.0.1" in cmd_str

    def test_ssh_failure(self):
        shell = FakeShellRunner()
        shell.set_response("echo ok", 1, stderr="Connection refused")
        builder = SshBuilder(ssh_host="10.0.0.1", shell=shell)

        lines = _collect(builder.check_connection())
        assert any("ERROR:" in l and "Connection refused" in l for l in lines)
        # Should stop at step 1 — no AOSP check
        assert len(shell.calls) == 1

    def test_aosp_tree_missing(self):
        shell = FakeShellRunner()
        shell.set_response("echo ok", 0, stdout="ok")
        shell.set_response("echo AOSP_OK || echo AOSP_MISSING", 0, stdout="AOSP_MISSING")
        builder = SshBuilder(ssh_host="10.0.0.1", shell=shell)

        lines = _collect(builder.check_connection())
        assert any("ERROR:" in l and "AOSP source tree not found" in l for l in lines)
        # Should stop at step 2 — no tools check
        assert len(shell.calls) == 2

    def test_build_tools_missing(self):
        shell = FakeShellRunner()
        shell.set_response("echo ok", 0, stdout="ok")
        shell.set_response("echo AOSP_OK || echo AOSP_MISSING", 0, stdout="AOSP_OK")
        shell.set_response("echo TOOLS_OK || echo TOOLS_MISSING", 0, stdout="TOOLS_MISSING")
        builder = SshBuilder(ssh_host="10.0.0.1", shell=shell)

        lines = _collect(builder.check_connection())
        assert any("ERROR:" in l and "build tools" in l for l in lines)

    def test_ssh_key_included(self):
        shell = self._make_full_check_shell()
        builder = SshBuilder(
            ssh_host="10.0.0.1", ssh_key="/home/user/.ssh/id_rsa", shell=shell,
        )
        _collect(builder.check_connection())
        cmd_str = " ".join(shell.calls[0])
        assert "-i" in cmd_str
        assert "/home/user/.ssh/id_rsa" in cmd_str

    def test_ssh_opts_present(self):
        shell = self._make_full_check_shell()
        builder = SshBuilder(ssh_host="10.0.0.1", shell=shell)
        _collect(builder.check_connection())
        cmd_str = " ".join(shell.calls[0])
        assert "StrictHostKeyChecking=no" in cmd_str
        assert "BatchMode=yes" in cmd_str


# ---------------------------------------------------------------------------
# _sync_code
# ---------------------------------------------------------------------------

class TestSyncCode:

    def _make_vhal_dir(self, tmp_path: Path) -> Path:
        """Create a vhal_dir with impl/bridge/ (generated files + test-apk/) and impl/vhal/."""
        vhal_dir = tmp_path / "vhal"
        bridge = vhal_dir / "impl" / "bridge"
        bridge.mkdir(parents=True)
        (bridge / "test-apk").mkdir()
        # Create all 13 generated files
        for fname in config.GCP_GENERATED_BRIDGE_FILES:
            (bridge / fname).write_text("generated")
        (vhal_dir / "impl" / "vhal" / "src").mkdir(parents=True)
        (vhal_dir / "impl" / "vhal" / "Android.bp").write_text("cc_binary {}")
        (vhal_dir / "impl" / "vhal" / "src" / "VehicleService.cpp").write_text("int main() {}")
        return vhal_dir

    def test_sync_success(self, tmp_path: Path):
        """SDK missing on remote → upload SDK + 13 generated files + 2 vhal files."""
        shell = FakeShellRunner()
        shell.set_response("scp", 0)
        # SSH check returns MISSING so SDK gets uploaded
        shell.set_response("echo EXISTS || echo MISSING", 0, stdout="MISSING")
        builder = SshBuilder(ssh_host="10.0.0.1", shell=shell)
        vhal_dir = self._make_vhal_dir(tmp_path)
        # Add sdk/ dir so SDK upload happens
        (vhal_dir / "impl" / "bridge" / "sdk").mkdir()
        (vhal_dir / "impl" / "bridge" / "sdk" / "foo.h").write_text("// sdk")

        lines = _collect(builder._sync_code(vhal_dir))
        pass_lines = [l for l in lines if l.startswith("PASS")]
        # SDK synced + Generated bridge files synced + Patched vhal synced
        assert len(pass_lines) == 3
        assert any("SDK" in l for l in pass_lines)
        assert any("Generated" in l for l in pass_lines)
        assert any("vhal" in l.lower() for l in pass_lines)
        # SCP calls: 1 SDK recursive + 13 individual + 2 vhal = 16
        scp_calls = [c for c in shell.calls if "scp" in c[0]]
        assert len(scp_calls) == 16

    def test_sync_sdk_already_present(self, tmp_path: Path):
        """SDK already on remote → skip SDK, upload only generated + vhal."""
        shell = FakeShellRunner()
        shell.set_response("scp", 0)
        shell.set_response("echo EXISTS || echo MISSING", 0, stdout="EXISTS")
        builder = SshBuilder(ssh_host="10.0.0.1", shell=shell)
        vhal_dir = self._make_vhal_dir(tmp_path)

        lines = _collect(builder._sync_code(vhal_dir))
        skip_lines = [l for l in lines if l.startswith("SKIP")]
        assert any("SDK already present" in l for l in skip_lines)
        # No SDK SCP — only 13 generated + 2 vhal = 15
        scp_calls = [c for c in shell.calls if "scp" in c[0]]
        assert len(scp_calls) == 15

    def test_sync_force_sdk(self, tmp_path: Path):
        """force_sdk_sync=True → uploads SDK even if present."""
        shell = FakeShellRunner()
        shell.set_response("scp", 0)
        shell.set_response("echo EXISTS || echo MISSING", 0, stdout="EXISTS")
        builder = SshBuilder(ssh_host="10.0.0.1", shell=shell, force_sdk_sync=True)
        vhal_dir = self._make_vhal_dir(tmp_path)
        (vhal_dir / "impl" / "bridge" / "sdk").mkdir()

        lines = _collect(builder._sync_code(vhal_dir))
        assert any("PASS" in l and "SDK" in l for l in lines)
        assert any("forced" in l for l in lines)

    def test_sync_bridge_scp_failure(self, tmp_path: Path):
        """First individual generated file SCP fails → abort."""
        shell = FakeShellRunner()
        shell.set_response("scp", 1, stderr="ssh connection refused")
        # SDK check says present, so skip SDK upload
        shell.set_response("echo EXISTS || echo MISSING", 0, stdout="EXISTS")
        builder = SshBuilder(ssh_host="10.0.0.1", shell=shell)
        vhal_dir = self._make_vhal_dir(tmp_path)

        lines = _collect(builder._sync_code(vhal_dir))
        assert any("ERROR:" in l for l in lines)
        # Should abort after first SCP failure
        scp_calls = [c for c in shell.calls if "scp" in c[0]]
        assert len(scp_calls) == 1

    def test_sync_missing_bridge_dir(self, tmp_path: Path):
        shell = FakeShellRunner()
        builder = SshBuilder(ssh_host="10.0.0.1", shell=shell)
        # No impl/bridge/ created
        lines = _collect(builder._sync_code(tmp_path))
        assert any("ERROR:" in l and "Bridge directory" in l for l in lines)

    def test_custom_aosp_dir_in_remote_paths(self, tmp_path: Path):
        """Remote paths use the aosp_dir parameter."""
        shell = FakeShellRunner()
        shell.set_response("scp", 0)
        shell.set_response("echo EXISTS || echo MISSING", 0, stdout="EXISTS")
        builder = SshBuilder(ssh_host="10.0.0.1", aosp_dir="/opt/aosp", shell=shell)
        vhal_dir = self._make_vhal_dir(tmp_path)

        _collect(builder._sync_code(vhal_dir))
        # Check that scp targets use the custom aosp_dir
        scp_calls = [c for c in shell.calls if "scp" in c[0]]
        assert any("/opt/aosp" in " ".join(c) for c in scp_calls)


# ---------------------------------------------------------------------------
# _pull_artifacts
# ---------------------------------------------------------------------------

class TestPullArtifacts:

    def test_all_pulled(self, tmp_path: Path):
        shell = FakeShellRunner()
        shell.set_response("scp", 0)
        builder = SshBuilder(ssh_host="10.0.0.1", shell=shell)

        lines = _collect(builder._pull_artifacts(tmp_path))
        pass_lines = [l for l in lines if l.startswith("PASS")]
        # One PASS per artifact + one "All artifacts pulled"
        assert len(pass_lines) == len(config.GCP_ARTIFACT_REMOTE_PATHS) + 1

    def test_scp_failure(self, tmp_path: Path):
        shell = FakeShellRunner()
        shell.set_response("scp", 1, stderr="timeout")
        builder = SshBuilder(ssh_host="10.0.0.1", shell=shell)

        lines = _collect(builder._pull_artifacts(tmp_path))
        assert any("FAIL" in l for l in lines)

    def test_uses_scp_not_gcloud(self, tmp_path: Path):
        """Verify no gcloud commands are issued."""
        shell = FakeShellRunner()
        shell.set_response("scp", 0)
        builder = SshBuilder(ssh_host="10.0.0.1", shell=shell)

        _collect(builder._pull_artifacts(tmp_path))
        for cmd in shell.calls:
            assert cmd[0] != "gcloud", f"gcloud binary used in SSH path: {cmd}"


# ---------------------------------------------------------------------------
# build_incremental (end-to-end)
# ---------------------------------------------------------------------------

class TestBuildIncremental:

    def _make_happy_shell(self) -> FakeShellRunner:
        shell = FakeShellRunner()
        shell.set_response("echo ok", 0, stdout="ok")
        shell.set_response("echo AOSP_OK || echo AOSP_MISSING", 0, stdout="AOSP_OK")
        shell.set_response("echo TOOLS_OK || echo TOOLS_MISSING", 0, stdout="TOOLS_OK")
        shell.set_response("build_id.mk", 0, stdout="BUILD_ID := AP2A")
        shell.set_response("scp", 0)
        return shell

    def test_happy_path(self, tmp_path: Path):
        shell = self._make_happy_shell()
        builder = SshBuilder(ssh_host="10.0.0.1", shell=shell)

        vhal_dir = tmp_path / "vhal"
        bridge = vhal_dir / "impl" / "bridge"
        bridge.mkdir(parents=True)
        (bridge / "test-apk").mkdir()
        for fname in config.GCP_GENERATED_BRIDGE_FILES:
            (bridge / fname).write_text("generated")
        (vhal_dir / "impl" / "vhal" / "src").mkdir(parents=True)
        (vhal_dir / "impl" / "vhal" / "Android.bp").write_text("cc_binary {}")
        (vhal_dir / "impl" / "vhal" / "src" / "VehicleService.cpp").write_text("int main() {}")
        artifact_dir = tmp_path / "artifacts"

        lines = _collect(builder.build_incremental(
            vhal_dir=vhal_dir, artifact_dir=artifact_dir,
        ))
        assert any("PASS" in l and "build-info.json" in l for l in lines)
        assert not any(l.startswith("FAIL") or l.startswith("ERROR:") for l in lines)
        assert (artifact_dir / "build-info.json").exists()

        # Verify build-info.json has ssh_incremental type
        import json
        info = json.loads((artifact_dir / "build-info.json").read_text())
        assert info["build_type"] == "ssh_incremental"
        assert info["host"] == "10.0.0.1"

    def test_aborts_on_ssh_failure(self, tmp_path: Path):
        shell = FakeShellRunner()
        shell.set_response("echo ok", 1, stderr="Connection refused")
        builder = SshBuilder(ssh_host="10.0.0.1", shell=shell)

        lines = _collect(builder.build_incremental(
            vhal_dir=tmp_path, artifact_dir=tmp_path / "out",
        ))
        assert any("ERROR:" in l for l in lines)
        # Should not proceed to sync
        scp_calls = [c for c in shell.calls if "scp" in c[0]]
        assert len(scp_calls) == 0

    def test_no_gcloud_binary(self, tmp_path: Path):
        """Zero gcloud commands in the entire SSH build path."""
        shell = self._make_happy_shell()
        builder = SshBuilder(ssh_host="10.0.0.1", shell=shell)

        vhal_dir = tmp_path / "vhal"
        bridge = vhal_dir / "impl" / "bridge"
        bridge.mkdir(parents=True)
        (bridge / "test-apk").mkdir()
        for fname in config.GCP_GENERATED_BRIDGE_FILES:
            (bridge / fname).write_text("generated")
        (vhal_dir / "impl" / "vhal" / "src").mkdir(parents=True)
        (vhal_dir / "impl" / "vhal" / "Android.bp").write_text("cc_binary {}")
        (vhal_dir / "impl" / "vhal" / "src" / "VehicleService.cpp").write_text("int main() {}")

        _collect(builder.build_incremental(
            vhal_dir=vhal_dir, artifact_dir=tmp_path / "artifacts",
        ))
        for cmd in shell.calls:
            # Check the binary (first element) is never gcloud
            assert cmd[0] != "gcloud", f"gcloud binary used in SSH path: {cmd}"
