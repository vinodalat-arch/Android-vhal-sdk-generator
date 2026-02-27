"""CLI entry point for vhal-gen."""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import click

from .builder.stub_build import StubBuilder
from .classifier.signal_classifier import SignalClassifier
from .generator.generator_engine import GeneratorEngine
from .parser.model_loader import load_flync_model

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


@click.group()
@click.version_option(version="1.0.0")
def main():
    """vhal-gen: FLYNC YAML to Android VHAL code generator."""


@main.command()
@click.argument("model_dir", type=click.Path(exists=True, file_okay=False))
@click.option(
    "--vhal-dir",
    "vhal_dir",
    required=True,
    type=click.Path(exists=True, file_okay=False),
    help="Path to pulled VHAL source (automotive/vehicle/aidl)",
)
@click.option(
    "--sdk-dir",
    "sdk_dir",
    default=None,
    type=click.Path(exists=True, file_okay=False),
    help="Vehicle Body SDK source directory (e.g. performance-stack-Body-lighting-Draft/src/)",
)
def generate(model_dir: str, vhal_dir: str, sdk_dir: str | None):
    """Generate VHAL code into a pulled VHAL source tree."""
    model_path = Path(model_dir)
    vhal_root = Path(vhal_dir)
    sdk_source_dir = Path(sdk_dir) if sdk_dir else None

    click.echo(f"Loading FLYNC model from: {model_path}")
    model = load_flync_model(model_path)
    click.echo(f"  Parsed {len(model.pdus)} PDUs, {sum(len(p.signals) for p in model.pdus.values())} signals")

    click.echo("Classifying signals...")
    classifier = SignalClassifier()
    mappings = classifier.classify(model)
    standard = [m for m in mappings if m.is_standard]
    vendor = [m for m in mappings if m.is_vendor]
    click.echo(f"  {len(standard)} standard AOSP mappings, {len(vendor)} vendor mappings")

    click.echo(f"Generating code into VHAL tree: {vhal_root}")
    if sdk_source_dir:
        click.echo(f"  SDK source: {sdk_source_dir}")
    engine = GeneratorEngine(
        mappings=mappings,
        model=model,
        sdk_source_dir=sdk_source_dir,
    )
    generated = engine.generate(vhal_root=vhal_root)
    bridge_dir = vhal_root / "impl" / "bridge"
    click.echo(f"  Generated {len(generated)} files to {bridge_dir}")

    for f in generated:
        click.echo(f"    {f.relative_to(vhal_root)}")

    click.echo("Done — VehicleService.cpp and vhal/Android.bp auto-modified.")


@main.command()
@click.argument("model_dir", type=click.Path(exists=True, file_okay=False))
def inspect(model_dir: str):
    """Inspect a FLYNC YAML model directory and show parsed summary."""
    model_path = Path(model_dir)

    click.echo(f"Loading FLYNC model from: {model_path}")
    model = load_flync_model(model_path)

    click.echo(f"\nPDUs ({len(model.pdus)}):")
    click.echo(f"{'Name':<40} {'ID':<12} {'Length':>6} {'Signals':>7} {'Dir':<4}")
    click.echo("-" * 75)
    for name, pdu in sorted(model.pdus.items()):
        pdu_id_str = f"0x{pdu.pdu_id:X}"
        click.echo(
            f"{name:<40} {pdu_id_str:<12} {pdu.length:>4}B {len(pdu.signals):>7} {pdu.direction.value:<4}"
        )

    click.echo(f"\nSignals (total: {sum(len(p.signals) for p in model.pdus.values())}):")
    for pdu_name, pdu in sorted(model.pdus.items()):
        if not pdu.signals:
            continue
        click.echo(f"\n  [{pdu_name}] (0x{pdu.pdu_id:X}, {pdu.direction.value}):")
        click.echo(f"  {'Signal':<35} {'Start':>5} {'Len':>4} {'Type':<6} {'Range'}")
        click.echo(f"  {'-'*70}")
        for sig in pdu.signals:
            click.echo(
                f"  {sig.name:<35} {sig.start_bit:>5} {sig.bit_length:>4} {sig.base_data_type:<6} "
                f"[{sig.lower_limit}-{sig.upper_limit}]"
            )

    if model.global_states:
        click.echo(f"\nGlobal States ({len(model.global_states)}):")
        for gs in model.global_states:
            default = " (default)" if gs.is_default else ""
            click.echo(f"  {gs.state_id}: {gs.name}{default} — {', '.join(gs.participants)}")


@main.command()
@click.argument("model_dir", type=click.Path(exists=True, file_okay=False))
def classify(model_dir: str):
    """Classify signals to VehicleProperty mappings and show results."""
    model_path = Path(model_dir)

    click.echo(f"Loading FLYNC model from: {model_path}")
    model = load_flync_model(model_path)

    classifier = SignalClassifier()
    mappings = classifier.classify(model)

    click.echo(f"\nSignal → VehicleProperty Mappings ({len(mappings)}):")
    click.echo(f"{'Signal':<35} {'Property ID':<14} {'Type':<8} {'Access':<5} {'Vendor':<6} {'Dir':<3}")
    click.echo("-" * 85)
    for m in mappings:
        prop_label = m.standard_property_name if m.is_standard else m.vendor_constant_name
        click.echo(
            f"{m.signal_name:<35} {m.property_id_hex:<14} "
            f"{'STD' if m.is_standard else 'VNDR':<8} "
            f"{'R' if m.access.value == 1 else 'RW':<5} "
            f"{'Yes' if m.is_vendor else 'No':<6} "
            f"{'RX' if m.is_rx else 'TX':<3}"
        )


@main.command("compile-check")
@click.option(
    "--vhal-dir",
    "vhal_dir",
    required=True,
    type=click.Path(exists=True, file_okay=False),
    help="Path to pulled VHAL source tree with generated bridge code.",
)
def compile_check(vhal_dir: str):
    """Run clang++ syntax check on generated bridge code using stub headers."""
    vhal_root = Path(vhal_dir)
    builder = StubBuilder()
    has_fail = False
    for line in builder.compile_check(vhal_root):
        if line.startswith("PASS"):
            click.echo(click.style(f"  {line}", fg="green"))
        elif line.startswith("FAIL"):
            click.echo(click.style(f"  {line}", fg="red"))
            has_fail = True
        elif line.startswith("ERROR:"):
            click.echo(click.style(line, fg="red", bold=True))
            has_fail = True
        elif line.startswith("  "):
            # Diagnostic detail from clang
            click.echo(click.style(f"    {line.strip()}", fg="yellow"))
        elif line:
            click.echo(line)
    sys.exit(1 if has_fail else 0)


if __name__ == "__main__":
    main()
