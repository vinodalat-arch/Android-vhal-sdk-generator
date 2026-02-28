"""Trigger GitHub Actions VHAL build and poll for completion."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Iterator

from ..shell.runner import ShellRunner
from . import config


class BuildTrigger:
    """Triggers the build-vhal workflow and waits for it to finish."""

    def __init__(self, shell: ShellRunner | None = None) -> None:
        self._shell = shell or ShellRunner()

    def _get_repo_name(self, cwd: Path | None = None) -> tuple[str, str]:
        """Return (repo_name, error_msg).  error_msg is empty on success."""
        rc, stdout, stderr = self._shell.run(
            ["gh", "repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"],
            cwd=cwd,
            timeout=15,
        )
        if rc != 0:
            return "", stderr.strip() or "gh repo view failed"
        return stdout.strip(), ""

    def trigger_and_wait(
        self,
        *,
        generated_code_ref: str = "main",
        aosp_tag: str = config.DEFAULT_AOSP_TAG,
        build_target: str = config.DEFAULT_BUILD_TARGET,
        cwd: Path | None = None,
    ) -> Iterator[str]:
        """Trigger the workflow and yield status lines until completion.

        Yields:
            Status lines (same convention as StubBuilder.compile_check).
        """
        repo, err = self._get_repo_name(cwd)
        if err:
            yield f"ERROR: Cannot determine GitHub repo — {err}"
            yield "Hint: run `gh auth login` then try again."
            return

        yield f"Repository: {repo}"

        # Trigger workflow_dispatch
        yield f"Triggering workflow {config.WORKFLOW_FILE} ..."
        rc, stdout, stderr = self._shell.run(
            [
                "gh", "workflow", "run", config.WORKFLOW_FILE,
                "-f", f"aosp_tag={aosp_tag}",
                "-f", f"build_target={build_target}",
                "-f", f"generated_code_ref={generated_code_ref}",
            ],
            cwd=cwd,
            timeout=30,
        )
        if rc != 0:
            yield f"ERROR: Failed to trigger workflow — {stderr.strip()}"
            return

        yield "Workflow triggered.  Waiting for run to appear..."

        # Wait briefly for the run to register
        time.sleep(5)

        # Find the latest run for this workflow
        run_id, err = self._find_latest_run(cwd)
        if err:
            yield f"ERROR: {err}"
            return

        yield f"Run ID: {run_id}"

        # Poll until complete
        yield from self._poll_run(run_id, cwd)

    def _find_latest_run(self, cwd: Path | None) -> tuple[str, str]:
        """Return (run_id, error_msg)."""
        rc, stdout, stderr = self._shell.run(
            [
                "gh", "run", "list",
                "--workflow", config.WORKFLOW_FILE,
                "--limit", "1",
                "--json", "databaseId,status",
            ],
            cwd=cwd,
            timeout=15,
        )
        if rc != 0:
            return "", f"gh run list failed: {stderr.strip()}"

        try:
            runs = json.loads(stdout)
        except json.JSONDecodeError:
            return "", f"Failed to parse run list: {stdout[:200]}"

        if not runs:
            return "", "No workflow runs found"

        return str(runs[0]["databaseId"]), ""

    def _poll_run(self, run_id: str, cwd: Path | None) -> Iterator[str]:
        """Poll a workflow run until it completes or times out."""
        deadline = time.monotonic() + config.BUILD_TIMEOUT_SECONDS

        while time.monotonic() < deadline:
            rc, stdout, stderr = self._shell.run(
                [
                    "gh", "run", "view", run_id,
                    "--json", "status,conclusion",
                ],
                cwd=cwd,
                timeout=15,
            )
            if rc != 0:
                yield f"WARNING: gh run view failed — {stderr.strip()}"
                time.sleep(config.BUILD_POLL_INTERVAL_SECONDS)
                continue

            try:
                info = json.loads(stdout)
            except json.JSONDecodeError:
                time.sleep(config.BUILD_POLL_INTERVAL_SECONDS)
                continue

            status = info.get("status", "unknown")
            conclusion = info.get("conclusion", "")

            if status == "completed":
                if conclusion == "success":
                    yield f"PASS Build completed successfully (run {run_id})"
                else:
                    yield f"FAIL Build finished with conclusion: {conclusion}"
                    yield f"  View logs: gh run view {run_id} --log-failed"
                return

            yield f"  Build status: {status} ..."
            time.sleep(config.BUILD_POLL_INTERVAL_SECONDS)

        yield f"FAIL Build timed out after {config.BUILD_TIMEOUT_SECONDS // 60} minutes"
        yield f"  Cancel manually: gh run cancel {run_id}"
