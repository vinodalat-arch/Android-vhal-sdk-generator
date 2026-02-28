"""Orchestrate the full deploy-test pipeline (stages 1–6)."""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

from ..builder.stub_build import StubBuilder
from ..classifier.signal_classifier import SignalClassifier
from ..generator.generator_engine import GeneratorEngine
from ..parser.model_loader import load_flync_model
from ..shell.runner import ShellRunner
from .artifact_manager import ArtifactManager
from .build_trigger import BuildTrigger
from . import config
from .emulator_deployer import EmulatorDeployer
from .property_verifier import PropertyVerifier


class DeployOrchestrator:
    """Chains all six deploy-test stages, yielding status lines throughout."""

    def __init__(self, shell: ShellRunner | None = None) -> None:
        self._shell = shell or ShellRunner()
        self._trigger = BuildTrigger(self._shell)
        self._artifacts = ArtifactManager(self._shell)
        self._deployer = EmulatorDeployer(self._shell)
        self._verifier = PropertyVerifier(self._shell)

    def run(
        self,
        *,
        model_dir: Path,
        vhal_dir: Path,
        sdk_dir: Path | None = None,
        skip_generate: bool = False,
        skip_build: bool = False,
        artifact_dir: Path | None = None,
        git_ref: str = "main",
        aosp_tag: str = config.DEFAULT_AOSP_TAG,
        incremental: bool = False,
        gcp_instance: str = "",
        gcp_zone: str = "",
        gcp_project: str | None = None,
    ) -> Iterator[str]:
        """Execute the deploy-test pipeline.

        Args:
            model_dir: Path to FLYNC YAML model directory.
            vhal_dir: Path to pulled VHAL source tree.
            sdk_dir: Optional Vehicle Body SDK source directory.
            skip_generate: Skip code generation (use existing bridge code).
            skip_build: Skip GCP build (use pre-downloaded artifacts).
            artifact_dir: Path to pre-downloaded artifacts (required if skip_build).
            git_ref: Git ref to pass to the build workflow.
            aosp_tag: AOSP tag for the build.
            incremental: Use incremental GCP instance build instead of GitHub Actions.
            gcp_instance: GCP Compute Engine instance name (required if incremental).
            gcp_zone: GCP zone (required if incremental).
            gcp_project: GCP project ID (optional).

        Yields:
            Status lines suitable for CLI streaming.
        """
        # --- Stage 1: Generate ---
        if not skip_generate:
            yield "=== Stage 1: Generate ==="
            yield from self._stage_generate(model_dir, vhal_dir, sdk_dir)
        else:
            yield "=== Stage 1: Generate (skipped) ==="

        # --- Stages 2–4: Build ---
        if incremental:
            # Incremental build on a pre-existing GCP instance
            from .gcp_builder import GcpBuilder

            if artifact_dir is None:
                artifact_dir = Path("artifacts") / "incremental"
            builder = GcpBuilder(
                instance_name=gcp_instance,
                zone=gcp_zone,
                project=gcp_project,
                shell=self._shell,
            )
            yield ""
            for line in builder.build_incremental(
                vhal_dir=vhal_dir, artifact_dir=artifact_dir,
            ):
                yield line
                if line.startswith(("FAIL", "ERROR:")):
                    yield "Pipeline aborted — VHAL build failed."
                    return
        elif not skip_build:
            yield ""
            yield "=== Stage 2: Git Push ==="
            yield from self._stage_git_push()

            # --- Stage 3: Trigger build ---
            yield ""
            yield "=== Stage 3: Build (GCP) ==="
            has_fail = False
            run_id = ""
            for line in self._trigger.trigger_and_wait(
                generated_code_ref=git_ref,
                aosp_tag=aosp_tag,
            ):
                yield line
                if line.startswith("FAIL") or line.startswith("ERROR:"):
                    has_fail = True
                if line.startswith("Run ID:"):
                    run_id = line.split(":", 1)[1].strip()

            if has_fail:
                yield "Pipeline aborted — build failed."
                return

            # --- Stage 4: Download artifacts ---
            yield ""
            yield "=== Stage 4: Download Artifacts ==="
            if artifact_dir is None:
                artifact_dir = Path("artifacts") / run_id
            for line in self._artifacts.download(run_id, artifact_dir):
                yield line
                if line.startswith("FAIL"):
                    yield "Pipeline aborted — artifact download failed."
                    return
        else:
            yield ""
            yield "=== Stages 2–4: Build (skipped) ==="
            if artifact_dir is None:
                yield "ERROR: --artifact-dir is required when using --skip-build"
                return
            if not artifact_dir.is_dir():
                yield f"ERROR: Artifact directory not found: {artifact_dir}"
                return
            yield from self._artifacts.verify_dir(artifact_dir)

        # --- Stage 5: Deploy to emulator ---
        yield ""
        yield "=== Stage 5: Deploy to Emulator ==="
        for line in self._deployer.deploy(artifact_dir, self._artifacts, vhal_dir=vhal_dir):
            yield line
            if line.startswith("ERROR:"):
                yield "Pipeline aborted — deploy failed."
                return

        # --- Stage 6: Verify properties ---
        yield ""
        yield "=== Stage 6: Verify Properties ==="
        props_path = self._artifacts.find_artifact_file(
            artifact_dir, "DefaultProperties.json"
        )
        if props_path is None:
            yield "ERROR: DefaultProperties.json not found in artifacts"
            return
        yield from self._verifier.verify(props_path)

    def _stage_generate(
        self, model_dir: Path, vhal_dir: Path, sdk_dir: Path | None
    ) -> Iterator[str]:
        """Run code generation."""
        yield f"Loading FLYNC model from: {model_dir}"
        model = load_flync_model(model_dir)
        yield f"  Parsed {len(model.pdus)} PDUs, {sum(len(p.signals) for p in model.pdus.values())} signals"

        yield "Classifying signals..."
        classifier = SignalClassifier()
        mappings = classifier.classify(model)
        standard = [m for m in mappings if m.is_standard]
        vendor = [m for m in mappings if m.is_vendor]
        yield f"  {len(standard)} standard, {len(vendor)} vendor mappings"

        yield f"Generating code into: {vhal_dir}"
        engine = GeneratorEngine(
            mappings=mappings,
            model=model,
            sdk_source_dir=sdk_dir,
        )
        generated = engine.generate(vhal_root=vhal_dir)
        yield f"  Generated {len(generated)} files"

    def _stage_git_push(self) -> Iterator[str]:
        """Commit and push generated code."""
        # Check for uncommitted changes
        rc, stdout, _ = self._shell.run(
            ["git", "status", "--porcelain"], timeout=10
        )
        if not stdout.strip():
            yield "No changes to commit — assuming code already pushed."
            return

        yield "Staging generated files..."
        self._shell.run(["git", "add", "output/"], timeout=10)

        yield "Committing..."
        rc, stdout, stderr = self._shell.run(
            ["git", "commit", "-m", "chore: update generated VHAL code for deploy-test"],
            timeout=15,
        )
        if rc != 0 and "nothing to commit" not in stdout + stderr:
            yield f"ERROR: git commit failed — {stderr.strip()}"
            yield "Hint: make sure you have a clean working tree or commit manually."
            return

        yield "Pushing to remote..."
        rc, _, stderr = self._shell.run(["git", "push"], timeout=60)
        if rc != 0:
            yield f"ERROR: git push failed — {stderr.strip()}"
            yield "Hint: check `gh auth login` and remote configuration."
            return

        yield "PASS Code pushed to remote."
