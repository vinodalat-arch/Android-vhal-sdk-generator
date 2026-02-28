"""Shell command runner with streaming output."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Iterator


class ShellRunner:
    """Runs shell commands with optional streaming output."""

    def run_streaming(
        self, cmd: list[str], cwd: Path | None = None
    ) -> Iterator[str]:
        """Run command and yield stdout/stderr lines as they arrive.

        Args:
            cmd: Command and arguments.
            cwd: Working directory.

        Yields:
            Lines of combined stdout/stderr output.
        """
        try:
            proc = subprocess.Popen(
                cmd,
                cwd=str(cwd) if cwd else None,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            if proc.stdout:
                for line in proc.stdout:
                    yield line.rstrip("\n")
            proc.wait()
            if proc.returncode != 0:
                yield f"[Exit code: {proc.returncode}]"
        except FileNotFoundError:
            yield f"ERROR: Command not found: {cmd[0]}"
        except Exception as e:
            yield f"ERROR: {e}"

    def run(
        self, cmd: list[str], cwd: Path | None = None, timeout: int = 120
    ) -> tuple[int, str, str]:
        """Run command and return (returncode, stdout, stderr).

        Args:
            cmd: Command and arguments.
            cwd: Working directory.
            timeout: Timeout in seconds.

        Returns:
            Tuple of (return_code, stdout, stderr).
        """
        try:
            result = subprocess.run(
                cmd,
                cwd=str(cwd) if cwd else None,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return result.returncode, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            return -1, "", f"Command timed out after {timeout}s"
        except FileNotFoundError:
            return -1, "", f"Command not found: {cmd[0]}"
