"""Unit tests for the GcpBuilder incremental build pipeline."""

from __future__ import annotations

from pathlib import Path

import pytest

from vhal_gen.pipeline import config
from vhal_gen.pipeline.gcp_builder import GcpBuilder


# ---------------------------------------------------------------------------
# Helpers (same as test_pipeline.py)
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
# check_gcloud
# ---------------------------------------------------------------------------

class TestCheckGcloud:

    def test_gcloud_not_installed(self):
        shell = FakeShellRunner()
        shell.set_response("gcloud info", 1, stderr="command not found")
        builder = GcpBuilder(instance_name="vm-1", zone="us-central1-a", shell=shell)

        lines = _collect(builder.check_gcloud())
        assert any("ERROR:" in l for l in lines)

    def test_gcloud_configured(self):
        shell = FakeShellRunner()
        shell.set_response("gcloud info", 0, stdout="user@example.com")
        shell.set_response("gcloud config get-value", 0, stdout="my-project")
        builder = GcpBuilder(instance_name="vm-1", zone="us-central1-a", shell=shell)

        lines = _collect(builder.check_gcloud())
        assert any("PASS" in l and "user@example.com" in l for l in lines)

    def test_gcloud_not_authenticated(self):
        shell = FakeShellRunner()
        shell.set_response("gcloud info", 0, stdout="")
        builder = GcpBuilder(instance_name="vm-1", zone="us-central1-a", shell=shell)

        lines = _collect(builder.check_gcloud())
        assert any("ERROR:" in l and "not authenticated" in l for l in lines)


# ---------------------------------------------------------------------------
# check_instance
# ---------------------------------------------------------------------------

class TestCheckInstance:

    def test_instance_running(self):
        shell = FakeShellRunner()
        shell.set_response("instances describe", 0, stdout="RUNNING")
        builder = GcpBuilder(instance_name="vm-1", zone="us-central1-a", shell=shell)

        lines = _collect(builder.check_instance())
        assert any("PASS" in l and "RUNNING" in l for l in lines)

    def test_instance_terminated(self):
        shell = FakeShellRunner()
        shell.set_response("instances describe", 0, stdout="TERMINATED")
        builder = GcpBuilder(instance_name="vm-1", zone="us-central1-a", shell=shell)

        lines = _collect(builder.check_instance())
        assert any("FAIL" in l and "TERMINATED" in l for l in lines)

    def test_instance_not_found(self):
        shell = FakeShellRunner()
        shell.set_response("instances describe", 1, stderr="not found")
        builder = GcpBuilder(instance_name="vm-x", zone="us-central1-a", shell=shell)

        lines = _collect(builder.check_instance())
        assert any("ERROR:" in l and "not found" in l for l in lines)

    def test_project_flag_included(self):
        shell = FakeShellRunner()
        shell.set_response("instances describe", 0, stdout="RUNNING")
        builder = GcpBuilder(
            instance_name="vm-1", zone="us-central1-a",
            project="my-proj", shell=shell,
        )
        _collect(builder.check_instance())
        cmd_str = " ".join(shell.calls[-1])
        assert "--project" in cmd_str and "my-proj" in cmd_str


# ---------------------------------------------------------------------------
# get_instance_status / start / stop
# ---------------------------------------------------------------------------

class TestInstanceControl:

    def test_get_status_running(self):
        shell = FakeShellRunner()
        shell.set_response("instances describe", 0, stdout="RUNNING")
        builder = GcpBuilder(instance_name="vm-1", zone="us-central1-a", shell=shell)
        assert builder.get_instance_status() == "RUNNING"

    def test_get_status_not_found(self):
        shell = FakeShellRunner()
        shell.set_response("instances describe", 1, stderr="not found")
        builder = GcpBuilder(instance_name="vm-x", zone="us-central1-a", shell=shell)
        assert builder.get_instance_status() == "NOT_FOUND"

    def test_start_instance(self):
        shell = FakeShellRunner()
        shell.set_response("instances start", 0)
        builder = GcpBuilder(instance_name="vm-1", zone="us-central1-a", shell=shell)
        lines = _collect(builder.start_instance())
        assert any("PASS" in l and "started" in l for l in lines)

    def test_stop_instance(self):
        shell = FakeShellRunner()
        shell.set_response("instances stop", 0)
        builder = GcpBuilder(instance_name="vm-1", zone="us-central1-a", shell=shell)
        lines = _collect(builder.stop_instance())
        assert any("PASS" in l and "stopped" in l for l in lines)

    def test_start_failure(self):
        shell = FakeShellRunner()
        shell.set_response("instances start", 1, stderr="quota exceeded")
        builder = GcpBuilder(instance_name="vm-1", zone="us-central1-a", shell=shell)
        lines = _collect(builder.start_instance())
        assert any("ERROR:" in l for l in lines)


# ---------------------------------------------------------------------------
# _sync_code
# ---------------------------------------------------------------------------

class TestSyncCode:

    def _make_vhal_dir(self, tmp_path: Path) -> Path:
        """Create a vhal_dir with impl/bridge/ and impl/vhal/ subdirs."""
        vhal_dir = tmp_path / "vhal"
        (vhal_dir / "impl" / "bridge").mkdir(parents=True)
        (vhal_dir / "impl" / "vhal").mkdir(parents=True)
        return vhal_dir

    def test_sync_success(self, tmp_path: Path):
        shell = FakeShellRunner()
        shell.set_response("compute scp", 0)
        builder = GcpBuilder(instance_name="vm-1", zone="us-central1-a", shell=shell)
        vhal_dir = self._make_vhal_dir(tmp_path)

        lines = _collect(builder._sync_code(vhal_dir))
        pass_lines = [l for l in lines if l.startswith("PASS")]
        # Should have 2 PASS lines: bridge synced + vhal synced
        assert len(pass_lines) == 2
        assert any("Bridge" in l for l in pass_lines)
        assert any("vhal" in l.lower() for l in pass_lines)
        # Should have made 2 SCP calls
        scp_calls = [c for c in shell.calls if "scp" in " ".join(c)]
        assert len(scp_calls) == 2

    def test_sync_bridge_scp_failure(self, tmp_path: Path):
        shell = FakeShellRunner()
        shell.set_response("compute scp", 1, stderr="ssh connection refused")
        builder = GcpBuilder(instance_name="vm-1", zone="us-central1-a", shell=shell)
        vhal_dir = self._make_vhal_dir(tmp_path)

        lines = _collect(builder._sync_code(vhal_dir))
        assert any("ERROR:" in l and "bridge" in l.lower() for l in lines)
        # Should abort after first SCP failure, no second SCP
        scp_calls = [c for c in shell.calls if "scp" in " ".join(c)]
        assert len(scp_calls) == 1

    def test_sync_missing_bridge_dir(self, tmp_path: Path):
        shell = FakeShellRunner()
        builder = GcpBuilder(instance_name="vm-1", zone="us-central1-a", shell=shell)
        # No impl/bridge/ created
        lines = _collect(builder._sync_code(tmp_path))
        assert any("ERROR:" in l and "Bridge directory" in l for l in lines)


# ---------------------------------------------------------------------------
# _pull_artifacts
# ---------------------------------------------------------------------------

class TestPullArtifacts:

    def test_all_pulled(self, tmp_path: Path):
        shell = FakeShellRunner()
        shell.set_response("compute scp", 0)
        builder = GcpBuilder(instance_name="vm-1", zone="us-central1-a", shell=shell)

        lines = _collect(builder._pull_artifacts(tmp_path))
        pass_lines = [l for l in lines if l.startswith("PASS")]
        # One PASS per artifact + one "All artifacts pulled"
        assert len(pass_lines) == len(config.GCP_ARTIFACT_REMOTE_PATHS) + 1

    def test_scp_failure(self, tmp_path: Path):
        shell = FakeShellRunner()
        shell.set_response("compute scp", 1, stderr="timeout")
        builder = GcpBuilder(instance_name="vm-1", zone="us-central1-a", shell=shell)

        lines = _collect(builder._pull_artifacts(tmp_path))
        assert any("FAIL" in l for l in lines)


# ---------------------------------------------------------------------------
# build_incremental (end-to-end)
# ---------------------------------------------------------------------------

class TestBuildIncremental:

    def _make_happy_shell(self) -> FakeShellRunner:
        shell = FakeShellRunner()
        shell.set_response("gcloud info", 0, stdout="user@example.com")
        shell.set_response("gcloud config get-value", 0, stdout="my-project")
        shell.set_response("instances describe", 0, stdout="RUNNING")
        shell.set_response("compute scp", 0)
        shell.set_response("compute ssh", 0)
        return shell

    def test_happy_path(self, tmp_path: Path):
        shell = self._make_happy_shell()
        builder = GcpBuilder(instance_name="vm-1", zone="us-central1-a", shell=shell)

        vhal_dir = tmp_path / "vhal"
        (vhal_dir / "impl" / "bridge").mkdir(parents=True)
        (vhal_dir / "impl" / "vhal").mkdir(parents=True)
        artifact_dir = tmp_path / "artifacts"

        lines = _collect(builder.build_incremental(
            vhal_dir=vhal_dir, artifact_dir=artifact_dir,
        ))
        assert any("PASS" in l and "build-info.json" in l for l in lines)
        assert not any(l.startswith("FAIL") or l.startswith("ERROR:") for l in lines)
        assert (artifact_dir / "build-info.json").exists()

    def test_aborts_on_instance_not_running(self, tmp_path: Path):
        shell = FakeShellRunner()
        shell.set_response("gcloud info", 0, stdout="user@example.com")
        shell.set_response("gcloud config get-value", 0, stdout="my-project")
        shell.set_response("instances describe", 0, stdout="TERMINATED")
        builder = GcpBuilder(instance_name="vm-1", zone="us-central1-a", shell=shell)

        lines = _collect(builder.build_incremental(
            vhal_dir=tmp_path, artifact_dir=tmp_path / "out",
        ))
        assert any("FAIL" in l and "TERMINATED" in l for l in lines)
        # Should not proceed to sync
        scp_calls = [c for c in shell.calls if "scp" in " ".join(c)]
        assert len(scp_calls) == 0

    def test_aborts_on_gcloud_not_installed(self, tmp_path: Path):
        shell = FakeShellRunner()
        shell.set_response("gcloud info", 1, stderr="command not found")
        builder = GcpBuilder(instance_name="vm-1", zone="us-central1-a", shell=shell)

        lines = _collect(builder.build_incremental(
            vhal_dir=tmp_path, artifact_dir=tmp_path / "out",
        ))
        assert any("ERROR:" in l for l in lines)
        # Should not proceed at all
        assert len(shell.calls) == 1
