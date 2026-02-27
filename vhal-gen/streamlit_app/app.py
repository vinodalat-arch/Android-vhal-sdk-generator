"""KPIT Vehicle SDK Generator — single-page Streamlit UI."""

import io
import sys
import zipfile
from pathlib import Path

import streamlit as st

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from vhal_gen.classifier.signal_classifier import SignalClassifier
from vhal_gen.fetcher.gerrit_fetcher import GerritFetcher
from vhal_gen.generator.generator_engine import GeneratorEngine
from vhal_gen.parser.model_loader import load_flync_model
from vhal_gen.shell.runner import ShellRunner

# ── Page config ──
st.set_page_config(
    page_title="KPIT Vehicle SDK Generator",
    page_icon="🚗",
    layout="wide",
)

# ── Custom CSS ──
st.markdown("""
<style>
    .workflow-step { padding: 4px 0; font-size: 0.9rem; }
    .step-done { color: #28a745; }
    .step-active { color: #ffc107; }
    .step-pending { color: #6c757d; }
    div[data-testid="stMetric"] { text-align: center; }
</style>
""", unsafe_allow_html=True)

# ── Folder picker helper ──


def _folder_picker(label, key, placeholder="", help_text=None, container=st):
    """Text input paired with an inline folder browser popover."""
    if key not in st.session_state:
        st.session_state[key] = ""

    browse_key = f"_browse_{key}"

    value = container.text_input(label, key=key, help=help_text, placeholder=placeholder)

    # Sync browse starting path with the current text value
    if value and Path(value).is_dir():
        st.session_state[browse_key] = value
    elif browse_key not in st.session_state:
        st.session_state[browse_key] = str(Path.home())

    with container.popover("Browse"):
        cur = Path(st.session_state[browse_key])
        st.caption(f"`{cur}`")

        if cur != cur.parent:
            if st.button(".. (parent)", key=f"{key}__up"):
                st.session_state[browse_key] = str(cur.parent)
                st.rerun()

        try:
            subdirs = sorted(
                d.name for d in cur.iterdir()
                if d.is_dir() and not d.name.startswith(".")
            )
        except (PermissionError, OSError):
            subdirs = []
            st.warning("Cannot read directory")

        for name in subdirs[:25]:
            if st.button(name, key=f"{key}__d_{name}", use_container_width=True):
                st.session_state[browse_key] = str(cur / name)
                st.rerun()

        if len(subdirs) > 25:
            st.caption(f"… and {len(subdirs) - 25} more")

        st.divider()
        if st.button(
            "Select this folder", key=f"{key}__sel",
            type="primary", use_container_width=True,
        ):
            st.session_state[key] = str(cur)
            st.rerun()

    return value


# ═══════════════════════════════════════════════════════
# SIDEBAR
# ═══════════════════════════════════════════════════════

st.sidebar.title("KPIT Vehicle SDK Generator")

# ── Project Base Folder ──
st.sidebar.subheader("Project Base Folder")
project_base = _folder_picker(
    "Base path", "project_base",
    placeholder="/path/to/project", container=st.sidebar,
)

# Auto-populate derived paths when project base changes
_prev_base = st.session_state.get("_prev_project_base", "")
if project_base != _prev_base:
    st.session_state["_prev_project_base"] = project_base
    if project_base:
        _base = Path(project_base)
        st.session_state["model_dir"] = str(_base / "flync-model-dev-2")
        st.session_state["sdk_source_dir"] = str(
            _base / "performance-stack-Body-lighting-Draft" / "src"
        )
        st.session_state["output_dir"] = str(_base / "output")
    else:
        st.session_state["model_dir"] = ""
        st.session_state["sdk_source_dir"] = ""
        st.session_state["output_dir"] = ""

# ── YAML Model Input ──
st.sidebar.subheader("YAML Model")
model_dir = _folder_picker(
    "FLYNC Model Directory", "model_dir",
    placeholder="/path/to/flync-model-dev-2", container=st.sidebar,
)

if st.sidebar.button("Load Model", type="primary", use_container_width=True):
    if not model_dir:
        st.sidebar.error("Enter a model directory path.")
    else:
        model_path = Path(model_dir)
        if not model_path.exists():
            st.sidebar.error(f"Directory not found: {model_path}")
        else:
            try:
                with st.sidebar.status("Parsing YAML files...", expanded=True) as status:
                    model = load_flync_model(model_path)
                    # Auto-classify signals
                    classifier = SignalClassifier()
                    mappings = classifier.classify(model)
                    st.session_state["model"] = model
                    st.session_state["mappings"] = mappings
                    st.session_state["model_loaded"] = True
                    status.update(label="Model loaded!", state="complete")
            except Exception as e:
                st.sidebar.error(f"Failed to load model: {e}")

# ── Model Info ──
if st.session_state.get("model_loaded"):
    model = st.session_state["model"]
    mappings = st.session_state["mappings"]
    standard = [m for m in mappings if m.is_standard]
    vendor = [m for m in mappings if m.is_vendor]

    st.sidebar.divider()
    st.sidebar.subheader("Model Info")
    st.sidebar.markdown(
        f"- **PDUs:** {len(model.pdus)}\n"
        f"- **Signals:** {sum(len(p.signals) for p in model.pdus.values())}\n"
        f"- **Standard mappings:** {len(standard)}\n"
        f"- **Vendor mappings:** {len(vendor)}"
    )

# ── Workflow Progress ──
st.sidebar.divider()
st.sidebar.subheader("Workflow Progress")


def _step_indicator(done: bool, label: str) -> str:
    if done:
        return f'<div class="workflow-step step-done">● {label}</div>'
    return f'<div class="workflow-step step-pending">○ {label}</div>'


st.sidebar.markdown(
    _step_indicator(st.session_state.get("model_loaded", False), "Model Loaded")
    + _step_indicator(bool(st.session_state.get("mappings")), "Signals Classified")
    + _step_indicator(st.session_state.get("vhal_pulled", False), "VHAL Source Pulled")
    + _step_indicator(st.session_state.get("code_generated", False), "Code Generated")
    + _step_indicator(st.session_state.get("verified", False), "Verified"),
    unsafe_allow_html=True,
)

# ═══════════════════════════════════════════════════════
# MAIN AREA
# ═══════════════════════════════════════════════════════

st.title("KPIT Vehicle SDK Generator")

tab_ivi, tab_sdk = st.tabs(["Generate IVI Package", "Generate Vehicle SDK"])

# ── Vehicle SDK Tab (placeholder) ──
with tab_sdk:
    st.info("Coming soon — requires reference Vehicle SDK integration.")

# ── IVI Package Tab ──
with tab_ivi:

    # ─────────────────────────────────────────────
    # Section 1: Signal Mapping
    # ─────────────────────────────────────────────
    st.header("1. Signal Mapping")

    if not st.session_state.get("model_loaded"):
        st.warning("Load a FLYNC model from the sidebar to begin.")
    else:
        model = st.session_state["model"]
        mappings = st.session_state["mappings"]
        standard = [m for m in mappings if m.is_standard]
        vendor = [m for m in mappings if m.is_vendor]

        col1, col2, col3 = st.columns(3)
        col1.metric("Standard AOSP", len(standard))
        col2.metric("Vendor", len(vendor))
        col3.metric("Total Signals", len(mappings))

        if st.button("Re-classify Signals"):
            classifier = SignalClassifier()
            st.session_state["mappings"] = classifier.classify(model)
            st.rerun()

        with st.expander("Standard Property Mappings", expanded=False):
            std_data = []
            for m in standard:
                std_data.append({
                    "Signal": m.signal_name,
                    "AOSP Property": m.standard_property_name,
                    "Property ID": m.property_id_hex,
                    "Area": f"0x{m.area_id:X}",
                    "Access": m.access.name,
                    "Direction": "RX" if m.is_rx else "TX",
                })
            if std_data:
                st.dataframe(std_data, use_container_width=True)
            else:
                st.caption("No standard mappings found.")

        with st.expander("Vendor Property Mappings", expanded=False):
            vnd_data = []
            for m in vendor:
                vnd_data.append({
                    "Signal": m.signal_name,
                    "Constant": m.vendor_constant_name,
                    "Property ID": m.property_id_hex,
                    "Type": m.property_type.name,
                    "Access": m.access.name,
                    "Direction": "RX" if m.is_rx else "TX",
                })
            if vnd_data:
                st.dataframe(vnd_data, use_container_width=True)
            else:
                st.caption("No vendor mappings found.")

    st.divider()

    # ─────────────────────────────────────────────
    # Section 2: VHAL Source & Configuration
    # ─────────────────────────────────────────────
    st.header("2. VHAL Source & Configuration")

    col_gerrit, col_tag = st.columns([3, 1])
    with col_gerrit:
        gerrit_url = st.text_input(
            "Gerrit URL",
            value=GerritFetcher.GERRIT_URL,
            help="Android Gerrit repository for VHAL AIDL interfaces.",
        )
    with col_tag:
        tag = st.selectbox(
            "Tag",
            options=["android14-release", "android14-qpr3-release"],
            index=0,
        )

    if st.button("Pull VHAL Source", type="primary"):
        fetcher = GerritFetcher()
        # Allow custom Gerrit URL
        fetcher.GERRIT_URL = gerrit_url
        target_dir = Path(st.session_state.get("output_dir", "./output"))
        with st.status("Pulling VHAL source...", expanded=True) as status:
            vhal_path = None
            for line in fetcher.fetch_vhal(target_dir, tag=tag):
                if line.startswith("DONE:"):
                    vhal_path = line[5:]
                    st.session_state["vhal_pulled"] = True
                    st.session_state["vhal_path"] = vhal_path
                elif line.startswith("ERROR:"):
                    st.error(line)
                else:
                    st.write(line)
            if vhal_path:
                status.update(label="VHAL source ready!", state="complete")
            else:
                status.update(label="VHAL pull failed", state="error")

    if st.session_state.get("vhal_pulled"):
        st.success(f"VHAL source: {st.session_state.get('vhal_path')}")

    st.subheader("Build Configuration")

    col_ver, col_sdk = st.columns(2)
    with col_ver:
        android_version = st.selectbox(
            "Android Version",
            options=["14"],
            index=0,
            help="Android 15/16 support is on the roadmap.",
        )
        st.session_state["android_version"] = android_version

    with col_sdk:
        sdk_source_dir = _folder_picker(
            "Vehicle Body SDK Directory", "sdk_source_dir",
            help_text="Path to Vehicle Body SDK source (com/, can_io/, app/swc/).",
        )

    output_dir = _folder_picker("Output Directory", "output_dir")

    st.divider()

    # ─────────────────────────────────────────────
    # Section 3: Generate IVI Package
    # ─────────────────────────────────────────────
    st.header("3. Generate IVI Package")

    if not st.session_state.get("model_loaded"):
        st.warning("Load a model first to generate code.")
    else:
        model = st.session_state["model"]
        mappings = st.session_state["mappings"]
        out_dir = st.session_state.get("output_dir", "./output")
        sdk_dir = st.session_state.get("sdk_source_dir", "")

        st.markdown(
            f"**Mappings:** {len(mappings)} signals · "
            f"**SDK:** {sdk_dir or 'not set'} · "
            f"**Output:** {out_dir}"
        )

        if st.button("Generate", type="primary"):
            out_path = Path(out_dir)
            sdk_path = Path(sdk_dir) if sdk_dir and Path(sdk_dir).exists() else None
            with st.spinner("Generating IVI package..."):
                engine = GeneratorEngine(
                    mappings=mappings,
                    model=model,
                    sdk_source_dir=sdk_path,
                )
                generated = engine.generate(out_path)
                st.session_state["generated_files"] = generated
                st.session_state["code_generated"] = True
                st.session_state["output_path"] = out_path

            st.success(f"Generated {len(generated)} files!")
            st.rerun()

        if st.session_state.get("code_generated"):
            generated = st.session_state["generated_files"]
            out_path = st.session_state["output_path"]

            # Download ZIP
            zip_buf = io.BytesIO()
            with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
                for f in generated:
                    zf.write(f, f.relative_to(out_path))
            zip_buf.seek(0)
            st.download_button(
                "Download ZIP",
                data=zip_buf.getvalue(),
                file_name="ivi-package.zip",
                mime="application/zip",
            )

            # File preview
            st.subheader("Generated Files")
            for f in generated:
                rel = f.relative_to(out_path)
                with st.expander(str(rel)):
                    content = f.read_text()
                    ext = f.suffix
                    lang = (
                        "cpp" if ext in (".cpp", ".h") else
                        "json" if ext == ".json" else
                        "java" if ext == ".java" else
                        "xml" if ext == ".xml" else
                        "makefile" if ext == ".bp" else
                        "markdown" if ext == ".md" else
                        "text"
                    )
                    st.code(content, language=lang)

    st.divider()

    # ─────────────────────────────────────────────
    # Section 4: Build, Deploy & Verify
    # ─────────────────────────────────────────────
    st.header("4. Build, Deploy & Verify")

    runner = ShellRunner()

    col_b, col_d, col_e, col_v = st.columns(4)

    with col_b:
        build_clicked = st.button("Build VHAL", use_container_width=True)
    with col_d:
        deploy_clicked = st.button("Deploy to Device", use_container_width=True)
    with col_e:
        emulator_clicked = st.button("Run Emulator", use_container_width=True)
    with col_v:
        verify_clicked = st.button("Verify Properties", use_container_width=True)

    if build_clicked:
        with st.status("Building VHAL...", expanded=True) as status:
            # Check for AOSP tree
            aosp_dir = st.session_state.get("vhal_path")
            if not aosp_dir:
                st.warning(
                    "Not available — requires AOSP build environment. "
                    "Pull VHAL source first, then set up a full AOSP tree for building."
                )
                status.update(label="Build skipped", state="error")
            else:
                st.info(
                    "Build requires a full AOSP source tree with `source build/envsetup.sh` "
                    "and `lunch` configured. Run the following in your AOSP tree:\n\n"
                    "```bash\n"
                    "source build/envsetup.sh\n"
                    "lunch sdk_car_x86_64-userdebug\n"
                    "m VehicleHal\n"
                    "```"
                )
                status.update(label="See build instructions", state="complete")

    if deploy_clicked:
        with st.status("Deploying to device...", expanded=True) as status:
            # Check adb availability
            rc, stdout, stderr = runner.run(["adb", "devices"])
            if rc != 0:
                st.warning(
                    "Not available — `adb` not found. "
                    "Install Android SDK Platform Tools and ensure `adb` is in PATH."
                )
                status.update(label="Deploy skipped", state="error")
            else:
                st.write("Connected devices:")
                st.code(stdout)
                out_dir = st.session_state.get("output_dir", "./output")
                st.info(
                    "To deploy the generated VHAL, run:\n\n"
                    "```bash\n"
                    f"adb root\n"
                    f"adb remount\n"
                    f"adb push {out_dir}/vhal/ /vendor/etc/automotive/vhal/\n"
                    f"adb shell stop vehicle_hal\n"
                    f"adb shell start vehicle_hal\n"
                    "```"
                )
                status.update(label="See deploy instructions", state="complete")

    if emulator_clicked:
        with st.status("Checking emulator...", expanded=True) as status:
            rc, stdout, stderr = runner.run(["emulator", "-list-avds"])
            if rc != 0:
                st.warning(
                    "Not available — `emulator` not found. "
                    "Install Android SDK Emulator and ensure it's in PATH."
                )
                status.update(label="Emulator not available", state="error")
            else:
                avds = [l for l in stdout.strip().splitlines() if l.strip()]
                if avds:
                    st.write("Available AVDs:")
                    for avd in avds:
                        st.write(f"  - {avd}")
                    st.info(
                        "Start the automotive emulator with:\n\n"
                        "```bash\n"
                        f"emulator -avd {avds[0]} -writable-system\n"
                        "```"
                    )
                else:
                    st.warning("No AVDs found. Create one with Android Studio AVD Manager.")
                status.update(label="Emulator info", state="complete")

    if verify_clicked:
        with st.status("Verifying properties...", expanded=True) as status:
            rc, stdout, stderr = runner.run(
                ["adb", "shell", "cmd", "car_service", "get-property-config"]
            )
            if rc != 0:
                st.warning(
                    "Not available — cannot reach device via `adb`. "
                    "Ensure a device/emulator is connected and running."
                )
                if stderr:
                    st.code(stderr)
                status.update(label="Verification failed", state="error")
            else:
                st.write("Property configuration from device:")
                st.code(stdout[:5000] if len(stdout) > 5000 else stdout)

                # Cross-check with generated mappings
                if st.session_state.get("mappings"):
                    mappings = st.session_state["mappings"]
                    results = []
                    for m in mappings:
                        found = m.property_id_hex in stdout or str(m.property_id) in stdout
                        results.append({
                            "Signal": m.signal_name,
                            "Property ID": m.property_id_hex,
                            "Status": "PASS" if found else "NOT FOUND",
                        })
                    st.dataframe(results, use_container_width=True)
                    passed = sum(1 for r in results if r["Status"] == "PASS")
                    if passed == len(results):
                        st.session_state["verified"] = True
                    st.write(f"**{passed}/{len(results)}** properties found on device.")

                status.update(label="Verification complete", state="complete")
