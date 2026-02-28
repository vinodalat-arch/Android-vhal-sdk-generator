"""KPIT Vehicle SDK Generator — single-page Streamlit UI."""

import io
import sys
import zipfile
from pathlib import Path

import streamlit as st

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from vhal_gen.builder.stub_build import StubBuilder
from vhal_gen.classifier.signal_classifier import SignalClassifier
from vhal_gen.fetcher.gerrit_fetcher import GerritFetcher
from vhal_gen.generator.generator_engine import GeneratorEngine
from vhal_gen.parser.model_loader import load_flync_model
from vhal_gen.pipeline.deploy_orchestrator import DeployOrchestrator
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


def _on_select_folder(widget_key, browse_key):
    """on_click callback — sets value before widgets render."""
    st.session_state[widget_key] = st.session_state[browse_key]


def _on_navigate(browse_key, new_path):
    """on_click callback — updates browse path before dialog re-renders."""
    st.session_state[browse_key] = new_path


@st.dialog("Browse Folder")
def _browse_folder_dialog(widget_key, browse_key):
    """Modal folder browser that closes on selection."""
    cur = Path(st.session_state[browse_key])
    st.caption(f"`{cur}`")

    if cur != cur.parent:
        st.button(
            ".. (parent)", key=f"{widget_key}__up",
            on_click=_on_navigate, args=(browse_key, str(cur.parent)),
        )

    try:
        subdirs = sorted(
            d.name for d in cur.iterdir()
            if d.is_dir() and not d.name.startswith(".")
        )
    except (PermissionError, OSError):
        subdirs = []
        st.warning("Cannot read directory")

    for name in subdirs[:25]:
        st.button(
            name, key=f"{widget_key}__d_{name}",
            use_container_width=True,
            on_click=_on_navigate, args=(browse_key, str(cur / name)),
        )

    if len(subdirs) > 25:
        st.caption(f"… and {len(subdirs) - 25} more")

    st.divider()
    if st.button(
        "Select this folder", key=f"{widget_key}__sel",
        type="primary", use_container_width=True,
        on_click=_on_select_folder, args=(widget_key, browse_key),
    ):
        st.rerun()  # closes the dialog


def _folder_picker(label, key, placeholder="", help_text=None, container=st):
    """Text input paired with a folder browser dialog."""
    if key not in st.session_state:
        st.session_state[key] = ""

    browse_key = f"_browse_{key}"

    value = container.text_input(label, key=key, help=help_text, placeholder=placeholder)

    # Sync browse starting path with the current text value
    if value and Path(value).is_dir():
        st.session_state[browse_key] = value
    elif browse_key not in st.session_state:
        st.session_state[browse_key] = str(Path.home())

    if container.button("Browse", key=f"{key}__browse"):
        _browse_folder_dialog(key, browse_key)

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
    else:
        st.session_state["model_dir"] = ""
        st.session_state["sdk_source_dir"] = ""

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
    + _step_indicator(st.session_state.get("verified", False), "Verified")
    + _step_indicator(st.session_state.get("deploy_tested", False), "Deploy Tested"),
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

    col_gerrit, col_tag, col_fetch = st.columns([3, 1, 1])
    with col_gerrit:
        gerrit_url = st.text_input(
            "Gerrit URL",
            value=GerritFetcher.GERRIT_URL,
            help="Android Gerrit repository for VHAL AIDL interfaces.",
        )
    with col_fetch:
        st.markdown("<div style='height: 28px'></div>", unsafe_allow_html=True)
        if st.button("Fetch Tags"):
            fetcher = GerritFetcher()
            fetcher.GERRIT_URL = gerrit_url
            with st.spinner("Querying Gerrit..."):
                tags = fetcher.list_android14_tags()
            if tags:
                st.session_state["gerrit_tags"] = tags
                st.rerun()
            else:
                st.warning("No tags found")

    _default_tags = [
        "android-14.0.0_r75",
        "android-14.0.0_r74",
        "android-14.0.0_r67",
    ]
    tag_options = st.session_state.get("gerrit_tags", _default_tags)

    with col_tag:
        tag = st.selectbox("Tag", options=tag_options, index=0)

    if st.button("Pull VHAL Source", type="primary"):
        fetcher = GerritFetcher()
        # Allow custom Gerrit URL
        fetcher.GERRIT_URL = gerrit_url
        target_dir = Path(st.session_state.get("project_base", ".")) / "output"
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

    st.divider()

    # ─────────────────────────────────────────────
    # Section 3: Generate IVI Package
    # ─────────────────────────────────────────────
    st.header("3. Generate IVI Package")

    if not st.session_state.get("model_loaded"):
        st.warning("Load a model first to generate code.")
    elif not st.session_state.get("vhal_pulled"):
        st.warning("Pull VHAL source first (Section 2) before generating.")
    else:
        model = st.session_state["model"]
        mappings = st.session_state["mappings"]
        vhal_path = st.session_state["vhal_path"]
        sdk_dir = st.session_state.get("sdk_source_dir", "")

        st.markdown(
            f"**Mappings:** {len(mappings)} signals · "
            f"**SDK:** {sdk_dir or 'not set'} · "
            f"**VHAL tree:** {vhal_path}"
        )

        if st.button("Generate", type="primary"):
            vhal_root = Path(vhal_path)
            if not vhal_root.exists():
                st.error(f"VHAL directory not found: {vhal_root}. Pull VHAL source first.")
            else:
                sdk_path = Path(sdk_dir) if sdk_dir and Path(sdk_dir).exists() else None
                try:
                    with st.spinner("Generating IVI package into VHAL tree..."):
                        engine = GeneratorEngine(
                            mappings=mappings,
                            model=model,
                            sdk_source_dir=sdk_path,
                        )
                        generated = engine.generate(vhal_root=vhal_root)
                        bridge_dir = vhal_root / "impl" / "bridge"
                        st.session_state["generated_files"] = generated
                        st.session_state["code_generated"] = True
                        st.session_state["bridge_dir"] = str(bridge_dir)

                    st.success(
                        f"Generated {len(generated)} files into {bridge_dir}\n\n"
                        "VehicleService.cpp and vhal/Android.bp auto-modified."
                    )
                    st.rerun()
                except Exception as e:
                    st.error(f"Generation failed: {e}")

        if st.session_state.get("code_generated") and st.session_state.get("bridge_dir"):
            generated = st.session_state["generated_files"]
            bridge_dir = Path(st.session_state["bridge_dir"])

            # Download ZIP of bridge directory
            zip_buf = io.BytesIO()
            with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
                for f in generated:
                    zf.write(f, f.relative_to(bridge_dir.parent))
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
                rel = f.relative_to(bridge_dir)
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

    # ── 4a. Local Verification ──
    st.subheader("4a. Local Verification")

    col_stub, col_e, col_v = st.columns(3)

    with col_stub:
        stub_clicked = st.button(
            "Compile Check (Stubs)",
            use_container_width=True,
            disabled=not st.session_state.get("code_generated", False),
        )
    with col_e:
        emulator_clicked = st.button("Run Emulator", use_container_width=True)
    with col_v:
        verify_clicked = st.button("Verify Properties", use_container_width=True)

    if stub_clicked:
        vhal_path = st.session_state.get("vhal_path")
        if not vhal_path:
            st.warning("Pull VHAL source and generate code first.")
        else:
            builder = StubBuilder()
            # Resolve SDK source dir with multiple fallbacks:
            # 1. Session state sdk_source_dir (set by sidebar or Section 2)
            # 2. Infer from project_base session state
            # 3. Auto-detect from vhal_path (walk up to find "output", go to parent)
            sdk_path = None
            vhal_root = Path(str(vhal_path))

            # Check if SDK already copied into bridge/sdk/ (no fallback needed)
            bridge_sdk = vhal_root / "impl" / "bridge" / "sdk"
            if not bridge_sdk.is_dir():
                # Try session state first
                sdk_dir_str = st.session_state.get("sdk_source_dir", "")
                if sdk_dir_str and Path(sdk_dir_str).is_dir():
                    sdk_path = Path(sdk_dir_str)
                else:
                    # Try project_base
                    base_str = st.session_state.get("project_base", "")
                    if base_str:
                        candidate = Path(base_str) / "performance-stack-Body-lighting-Draft" / "src"
                        if candidate.is_dir():
                            sdk_path = candidate
                    # Auto-detect from vhal_path: walk up to find "output" dir
                    if sdk_path is None:
                        parts = Path(str(vhal_path)).parts
                        if "output" in parts:
                            idx = parts.index("output")
                            inferred_base = Path(*parts[:idx])
                            candidate = inferred_base / "performance-stack-Body-lighting-Draft" / "src"
                            if candidate.is_dir():
                                sdk_path = candidate
                    # Fallback: look near the tool's own project root
                    if sdk_path is None:
                        tool_root = Path(__file__).resolve().parent.parent.parent
                        candidate = tool_root / "performance-stack-Body-lighting-Draft" / "src"
                        if candidate.is_dir():
                            sdk_path = candidate
                    if sdk_path:
                        st.info(f"Auto-detected SDK: {sdk_path}")
            with st.status("Running compile check (stubs)...", expanded=True) as status:
                all_lines: list[str] = []
                for line in builder.compile_check(vhal_root, sdk_dir=sdk_path):
                    all_lines.append(line)
                    if line.startswith("PASS"):
                        st.write(f":white_check_mark: {line}")
                    elif line.startswith("FAIL"):
                        st.write(f":x: {line}")
                    elif line.startswith("ERROR:"):
                        st.error(line)
                    elif line.startswith("SKIP"):
                        st.write(f":fast_forward: {line}")
                    elif line.startswith("Checking"):
                        st.write(line)
                    elif line.startswith("  "):
                        st.code(line.strip(), language="text")
                    elif line:
                        st.write(line)

                has_fail = any(l.startswith("FAIL") for l in all_lines)
                has_error = any(l.startswith("ERROR:") for l in all_lines)
                if has_fail or has_error:
                    status.update(label="Compile check failed", state="error")
                else:
                    status.update(label="Compile check passed", state="complete")

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

    # ── 4b. GCP Deploy Test ──
    st.subheader("4b. GCP Deploy Test")

    # --- GCP Instance Status Card ---
    st.markdown("**GCP Instance Status**")
    col_inst, col_zone, col_proj = st.columns([3, 2, 2])
    with col_inst:
        gcp_instance_name = st.text_input(
            "Instance Name", key="gcp_instance_name",
            placeholder="aosp-builder",
        )
    with col_zone:
        gcp_zone = st.text_input(
            "Zone", key="gcp_zone", value="us-central1-a",
        )
    with col_proj:
        gcp_project = st.text_input(
            "Project (optional)", key="gcp_project",
            placeholder="my-gcp-project",
        )

    col_check, col_start, col_stop = st.columns(3)
    with col_check:
        check_status_clicked = st.button(
            "Check Status", use_container_width=True,
            disabled=not gcp_instance_name,
        )
    with col_start:
        start_clicked = st.button(
            "Start Instance", use_container_width=True,
            disabled=not gcp_instance_name,
        )
    with col_stop:
        stop_clicked = st.button(
            "Stop Instance", use_container_width=True,
            disabled=not gcp_instance_name,
            help="Stop the VM to save cost. Disk charges still apply (~$85/mo for 500GB SSD).",
        )

    def _make_gcp_builder():
        from vhal_gen.pipeline.gcp_builder import GcpBuilder
        return GcpBuilder(
            instance_name=gcp_instance_name,
            zone=gcp_zone,
            project=gcp_project or None,
        )

    if check_status_clicked:
        if not gcp_instance_name:
            st.error("Enter an instance name to check status.")
        else:
            gcp_builder = _make_gcp_builder()
            with st.status("Checking GCP instance...", expanded=True) as gcp_status:
                gcp_ok = True
                for line in gcp_builder.check_gcloud():
                    if line.startswith("PASS"):
                        st.write(f":white_check_mark: {line}")
                    elif line.startswith("ERROR:"):
                        st.error(line)
                        gcp_ok = False

                if gcp_ok:
                    for line in gcp_builder.check_instance():
                        if line.startswith("PASS"):
                            st.write(f":white_check_mark: {line}")
                        elif line.startswith("FAIL"):
                            st.write(f":x: {line}")
                            gcp_ok = False
                        elif line.startswith("ERROR:"):
                            st.error(line)
                            gcp_ok = False

                vm_status = gcp_builder.get_instance_status() if gcp_ok or not gcp_ok else "UNKNOWN"
                st.session_state["gcp_ready"] = gcp_ok
                st.session_state["gcp_vm_status"] = vm_status if gcp_ok else gcp_builder.get_instance_status()
                if gcp_ok:
                    gcp_status.update(label="Instance ready", state="complete")
                else:
                    gcp_status.update(label="Instance not ready", state="error")

    if start_clicked and gcp_instance_name:
        gcp_builder = _make_gcp_builder()
        with st.status("Starting instance...", expanded=True) as start_status:
            for line in gcp_builder.start_instance():
                if line.startswith("PASS"):
                    st.write(f":white_check_mark: {line}")
                    st.session_state["gcp_ready"] = True
                    st.session_state["gcp_vm_status"] = "RUNNING"
                    start_status.update(label="Instance started", state="complete")
                elif line.startswith("ERROR:"):
                    st.error(line)
                    start_status.update(label="Start failed", state="error")
                else:
                    st.write(line)

    if stop_clicked and gcp_instance_name:
        gcp_builder = _make_gcp_builder()
        with st.status("Stopping instance...", expanded=True) as stop_status:
            for line in gcp_builder.stop_instance():
                if line.startswith("PASS"):
                    st.write(f":white_check_mark: {line}")
                    st.session_state["gcp_ready"] = False
                    st.session_state["gcp_vm_status"] = "TERMINATED"
                    stop_status.update(label="Instance stopped", state="complete")
                elif line.startswith("ERROR:"):
                    st.error(line)
                    stop_status.update(label="Stop failed", state="error")
                else:
                    st.write(line)

    # --- Status indicator ---
    vm_status = st.session_state.get("gcp_vm_status")
    if vm_status == "RUNNING":
        st.success("Instance RUNNING — ~$0.54/hr (e2-standard-16). Stop when not in use.")
    elif vm_status == "TERMINATED":
        st.info("Instance STOPPED — no compute charges. Disk: ~$85/mo (500GB SSD).")
    elif vm_status == "STAGING":
        st.warning("Instance STAGING — starting up...")
    elif vm_status == "STOPPING":
        st.warning("Instance STOPPING ...")
    elif vm_status == "NOT_FOUND":
        st.error("Instance not found.")
    elif vm_status == "GCLOUD_ERROR":
        st.error("Could not reach GCP — check gcloud auth.")
    elif vm_status is not None:
        st.warning(f"Instance status: {vm_status}")

    # --- Two Tabs: Full Build vs Incremental Build ---
    tab_full, tab_incr = st.tabs(["Full Build (GitHub Actions)", "Incremental Build (GCP Instance)"])

    # -- Tab 1: Full Build --
    with tab_full:
        col_tag_dt, col_ref = st.columns(2)
        with col_tag_dt:
            deploy_aosp_tag = st.text_input(
                "AOSP Tag",
                value="android-14.0.0_r75",
                key="deploy_aosp_tag",
                help="AOSP tag used for the GCP build.",
            )
        with col_ref:
            deploy_git_ref = st.text_input(
                "Git Ref",
                value="main",
                key="deploy_git_ref",
                help="Git branch or ref to build from.",
            )

        col_skip_gen, col_skip_build = st.columns(2)
        with col_skip_gen:
            deploy_skip_generate = st.checkbox(
                "Skip Generate", key="deploy_skip_generate",
                help="Skip code generation (use already-generated code).",
            )
        with col_skip_build:
            deploy_skip_build = st.checkbox(
                "Skip Build", key="deploy_skip_build",
                help="Skip GCP build and use pre-built artifacts.",
            )

        deploy_artifact_dir = ""
        if deploy_skip_build:
            deploy_artifact_dir = st.text_input(
                "Artifact Directory",
                key="deploy_artifact_dir",
                placeholder="/path/to/artifacts",
                help="Path to pre-built artifacts (required when skipping build).",
            )

        deploy_full_clicked = st.button(
            "Run Full Deploy Test", type="primary", use_container_width=True,
        )

    if deploy_full_clicked:
        model_dir_val = st.session_state.get("model_dir", "")
        vhal_path_val = st.session_state.get("vhal_path", "")

        if not model_dir_val or not Path(model_dir_val).is_dir():
            st.error("Model directory not set or not found. Load a model first.")
        elif not vhal_path_val or not Path(vhal_path_val).is_dir():
            st.error("VHAL source not found. Pull VHAL source first (Section 2).")
        elif deploy_skip_build and not (deploy_artifact_dir and Path(deploy_artifact_dir).is_dir()):
            st.error("Artifact directory is required when 'Skip Build' is checked.")
        else:
            sdk_dir_val = st.session_state.get("sdk_source_dir", "")
            sdk_path_arg = Path(sdk_dir_val) if sdk_dir_val and Path(sdk_dir_val).is_dir() else None
            artifact_path_arg = Path(deploy_artifact_dir) if deploy_artifact_dir else None

            orchestrator = DeployOrchestrator()
            with st.status("Running Full Deploy Test pipeline...", expanded=True) as status:
                all_lines: list[str] = []
                for line in orchestrator.run(
                    model_dir=Path(model_dir_val),
                    vhal_dir=Path(vhal_path_val),
                    sdk_dir=sdk_path_arg,
                    skip_generate=deploy_skip_generate,
                    skip_build=deploy_skip_build,
                    artifact_dir=artifact_path_arg,
                    git_ref=deploy_git_ref,
                    aosp_tag=deploy_aosp_tag,
                ):
                    all_lines.append(line)
                    if line.startswith("PASS"):
                        st.write(f":white_check_mark: {line}")
                    elif line.startswith("FAIL"):
                        st.write(f":x: {line}")
                    elif line.startswith("ERROR:"):
                        st.error(line)
                    elif line.startswith("==="):
                        st.markdown(f"**{line.strip('= ')}**")
                    elif line.startswith("Checking") or line.startswith("Stage"):
                        st.write(line)
                    elif line.startswith("  "):
                        st.code(line.strip(), language="text")
                    elif line:
                        st.write(line)

                has_fail = any(l.startswith("FAIL") for l in all_lines)
                has_error = any(l.startswith("ERROR:") for l in all_lines)
                if has_fail or has_error:
                    status.update(label="Deploy test failed", state="error")
                else:
                    st.session_state["deploy_tested"] = True
                    status.update(label="Deploy test passed!", state="complete")

    # -- Tab 2: Incremental Build --
    with tab_incr:
        st.caption("Sync code to GCP instance, run incremental mma (~5-15 min), pull artifacts back.")

        incr_skip_generate = st.checkbox(
            "Skip Generate", key="incr_skip_generate",
            help="Skip code generation (use already-generated code).",
        )

        gcp_ready = st.session_state.get("gcp_ready", False)
        deploy_incr_clicked = st.button(
            "Run Incremental Deploy Test",
            type="primary",
            use_container_width=True,
            disabled=not gcp_ready,
        )
        if not gcp_ready:
            st.caption("Click 'Check Status' above to verify the GCP instance is running.")

    if deploy_incr_clicked:
        model_dir_val = st.session_state.get("model_dir", "")
        vhal_path_val = st.session_state.get("vhal_path", "")

        if not model_dir_val or not Path(model_dir_val).is_dir():
            st.error("Model directory not set or not found. Load a model first.")
        elif not vhal_path_val or not Path(vhal_path_val).is_dir():
            st.error("VHAL source not found. Pull VHAL source first (Section 2).")
        else:
            sdk_dir_val = st.session_state.get("sdk_source_dir", "")
            sdk_path_arg = Path(sdk_dir_val) if sdk_dir_val and Path(sdk_dir_val).is_dir() else None

            orchestrator = DeployOrchestrator()
            with st.status("Running Incremental Deploy Test...", expanded=True) as status:
                all_lines: list[str] = []
                for line in orchestrator.run(
                    model_dir=Path(model_dir_val),
                    vhal_dir=Path(vhal_path_val),
                    sdk_dir=sdk_path_arg,
                    skip_generate=incr_skip_generate,
                    incremental=True,
                    gcp_instance=gcp_instance_name,
                    gcp_zone=gcp_zone,
                    gcp_project=gcp_project or None,
                ):
                    all_lines.append(line)
                    if line.startswith("PASS"):
                        st.write(f":white_check_mark: {line}")
                    elif line.startswith("FAIL"):
                        st.write(f":x: {line}")
                    elif line.startswith("ERROR:"):
                        st.error(line)
                    elif line.startswith("==="):
                        st.markdown(f"**{line.strip('= ')}**")
                    elif line.startswith("Checking") or line.startswith("Stage"):
                        st.write(line)
                    elif line.startswith("  "):
                        st.code(line.strip(), language="text")
                    elif line:
                        st.write(line)

                has_fail = any(l.startswith("FAIL") for l in all_lines)
                has_error = any(l.startswith("ERROR:") for l in all_lines)
                if has_fail or has_error:
                    status.update(label="Incremental deploy test failed", state="error")
                else:
                    st.session_state["deploy_tested"] = True
                    status.update(label="Incremental deploy test passed!", state="complete")
