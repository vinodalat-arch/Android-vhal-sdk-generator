"""KPIT Vehicle Platform Builder — single-page Streamlit UI."""

import io
import os
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


# ── Architecture diagram ──

def _render_architecture_diagram(
    hl_bridge: bool = False,
    hl_daemon: bool = False,
    hl_vhal_service: bool = False,
    hl_sdk: bool = False,
    blink: bool = False,
) -> str:
    """Return HTML for the Android Automotive layered architecture diagram.

    Highlighted layers get a green glow to show what vhal-gen modifies.
    """
    blink_cls = " blink" if blink else ""

    def _hl(flag: bool) -> str:
        return "highlighted" if flag else ""

    def _tag(flag: bool, label: str, cls: str) -> str:
        if not flag:
            return ""
        return f'<span class="layer-tag {cls}">{label}</span>'

    def _tag_inline(flag: bool, label: str, cls: str) -> str:
        if not flag:
            return ""
        return (
            f'<div style="margin-top:4px">'
            f'<span class="layer-tag {cls}" style="position:static">{label}</span>'
            f'</div>'
        )

    return f"""
<style>
  .arch-container {{
    font-family: 'Inter', -apple-system, sans-serif;
    max-width: 680px;
    margin: 0 auto;
  }}
  .layer {{
    border: 2px solid #444;
    border-radius: 8px;
    padding: 10px 16px;
    margin: 4px 0;
    text-align: center;
    transition: all 0.3s ease;
    position: relative;
  }}
  .layer-label {{
    font-size: 13px;
    font-weight: 600;
    color: #e0e0e0;
  }}
  .layer-sub {{
    font-size: 11px;
    color: #999;
    margin-top: 2px;
  }}
  .layer-tag {{
    position: absolute;
    right: 10px;
    top: 50%;
    transform: translateY(-50%);
    font-size: 10px;
    padding: 2px 8px;
    border-radius: 10px;
    font-weight: 600;
  }}
  .l-app       {{ background: #1a2332; border-color: #2d4a6e; }}
  .l-framework {{ background: #1a2332; border-color: #2d4a6e; }}
  .l-car       {{ background: #1a2332; border-color: #2d4a6e; }}
  .l-vhal      {{ background: #1e2a1e; border-color: #3d6b3d; }}
  .l-bridge    {{ background: #2a1e1e; border-color: #6b3d3d; }}
  .l-sdk       {{ background: #2a2a1e; border-color: #6b6b3d; }}
  .l-vsm       {{ background: #1a2a2a; border-color: #2d8a7a; }}
  .highlighted {{
    border-color: #61a229 !important;
    background: #1e3310 !important;
    box-shadow: 0 0 15px rgba(97, 162, 41, 0.3);
  }}
  .highlighted .layer-label {{ color: #7bc043; }}
  @keyframes blink-glow {{
    0%, 100% {{ opacity: 1; box-shadow: 0 0 15px rgba(97, 162, 41, 0.3); }}
    50% {{ opacity: 0.5; box-shadow: 0 0 25px rgba(97, 162, 41, 0.6); }}
  }}
  .blink {{
    animation: blink-glow 0.8s ease-in-out 6;
  }}
  .tag-generated {{ background: #61a229; color: #fff; }}
  .tag-patched   {{ background: #4e8221; color: #fff; }}
  .tag-shared    {{ background: #7c4dff; color: #fff; }}
  .vhal-inner {{
    display: flex;
    gap: 8px;
    justify-content: center;
    margin-top: 8px;
  }}
  .component {{
    border: 1.5px dashed #666;
    border-radius: 6px;
    padding: 8px 14px;
    min-width: 140px;
    transition: all 0.3s ease;
  }}
  .component.highlighted {{ border-style: solid; }}
  .eth-connector {{
    text-align: center;
    color: #6b9bd2;
    font-size: 11px;
    margin: 6px 0 2px 0;
    letter-spacing: 1px;
  }}
</style>

<div class="arch-container">

  <div class="layer l-app">
    <div class="layer-label">Android Applications</div>
    <div class="layer-sub">Car Settings, Maps, Media, OEM Apps</div>
  </div>

  <div class="layer l-framework">
    <div class="layer-label">Android Framework</div>
    <div class="layer-sub">CarPropertyManager API</div>
  </div>

  <div class="layer l-car">
    <div class="layer-label">Car Service</div>
    <div class="layer-sub">VehiclePropertyService (system_server)</div>
  </div>

  <div class="layer l-vhal {_hl(hl_vhal_service)}{blink_cls if hl_vhal_service else ''}" style="padding-bottom:14px;">
    <div class="layer-label">VHAL Service</div>
    {_tag(hl_vhal_service, "PATCHED", "tag-patched")}
    <div class="vhal-inner">
      <div class="component l-bridge {_hl(hl_bridge)}">
        <div class="layer-label">BridgeVehicleHardware</div>
        {_tag_inline(hl_bridge, "GENERATED", "tag-generated")}
      </div>
      <div style="display:flex;align-items:center;color:#888;font-size:20px;">&#x2194;</div>
      <div class="component l-bridge {_hl(hl_daemon)}">
        <div class="layer-label">VehicleDaemon</div>
        {_tag_inline(hl_daemon, "GENERATED", "tag-generated")}
      </div>
    </div>
  </div>

  <div class="layer l-sdk {_hl(hl_sdk)}{blink_cls if hl_sdk else ''}">
    <div class="layer-label">Common SDK used by All Nodes</div>
    {_tag(hl_sdk, "SHARED", "tag-shared")}
  </div>

  <div class="eth-connector">&#x25BC; Ethernet &#x25BC;</div>

  <div class="layer l-vsm">
    <div class="layer-label">Vehicle State Manager</div>
    <div class="layer-sub">Hardware gateway connecting IVI to vehicle ECU network</div>
  </div>

</div>
"""

# ── Page config ──
st.set_page_config(
    page_title="KPIT Vehicle Platform Builder",
    page_icon="🚗",
    layout="wide",
)

# ── KPIT Brand Constants ──
KPIT_GREEN = "#61a229"
KPIT_GREEN_DARK = "#4e8221"
KPIT_GREEN_LIGHT = "#7bc043"
KPIT_LOGO_SVG = (
    '<svg width="74" height="21" viewBox="0 0 74 21" fill="none" xmlns="http://www.w3.org/2000/svg">'
    '<path d="M48.8978 0.395142H45.6201V20.6478H48.8978V0.395142Z" fill="currentColor"/>'
    '<path d="M57.937 0.395111V3.21457H63.8176V20.5538H67.0228V0.395111H57.937Z" fill="currentColor"/>'
    '<path d="M36.3267 2.22799C35.0492 1.02971 33.3155 0.418762 31.1711 0.418762H23.2401V20.5538H26.4695V13.529H30.9763C33.2178 13.529 35.025 12.9417 36.3025 11.767C36.9608 11.1401 37.4769 10.3851 37.8173 9.55097C38.1578 8.71684 38.3151 7.82215 38.279 6.92486C38.3018 6.05259 38.1403 5.18509 37.8043 4.37657C37.4684 3.56804 36.9654 2.83586 36.3267 2.22576M34.8804 6.92486C34.9141 7.42751 34.832 7.93114 34.6402 8.39872C34.4483 8.86629 34.1515 9.28589 33.7717 9.62667C32.8838 10.3125 31.7687 10.6555 30.6387 10.5901H26.4211V3.35542H30.8317C31.9009 3.30403 32.9506 3.64803 33.7717 4.31886C34.1463 4.64341 34.4407 5.04669 34.6327 5.49838C34.8248 5.95006 34.9095 6.43839 34.8804 6.92664" fill="currentColor"/>'
    '<path d="M7.86768 10.1926L16.1582 0.395111H12.3257L5.28896 8.68861L5.19269 8.80625H3.86728V0.395111H0.685852V14.6551H3.86728V11.6248H5.24105L6.59064 13.2696L12.5675 20.5778H16.2549L7.86768 10.1926Z" fill="currentColor"/>'
    '<path d="M2.78233 17.5877C2.32533 17.4614 1.83573 17.5167 1.42033 17.7416C1.00494 17.9665 0.697455 18.3428 0.564952 18.7882C0.502117 19.0079 0.484682 19.2376 0.513665 19.4639C0.542648 19.6902 0.61747 19.9086 0.733766 20.1064C0.970219 20.5097 1.35987 20.8057 1.81827 20.9303C1.96577 20.9765 2.11965 21.0002 2.27452 21.0007C2.5076 21.0039 2.739 20.9618 2.95528 20.8769C3.17155 20.792 3.36838 20.6659 3.53433 20.506C3.70028 20.3461 3.83203 20.1556 3.92193 19.9456C4.01183 19.7355 4.05808 19.5101 4.058 19.2824C4.05348 18.905 3.92775 18.5386 3.69853 18.2347C3.46932 17.9309 3.1482 17.7051 2.7805 17.589" fill="currentColor"/>'
    '<path d="M72.2523 0.0653653C71.7953 -0.0608134 71.3058 -0.00542536 70.8904 0.219456C70.475 0.444338 70.1675 0.820477 70.0349 1.26587C69.9721 1.48554 69.9547 1.71522 69.9836 1.94153C70.0126 2.16784 70.0874 2.38625 70.2037 2.58403C70.4363 2.98098 70.8158 3.27583 71.2641 3.40799C71.4116 3.45411 71.5654 3.47786 71.7203 3.4784C72.1051 3.47819 72.4795 3.35662 72.7877 3.13179C73.096 2.90696 73.3217 2.5909 73.4312 2.23065C73.5589 1.7906 73.5072 1.31938 73.2871 0.915688C73.067 0.511993 72.6955 0.207123 72.2505 0.06492" fill="currentColor"/>'
    '</svg>'
)

# ── Custom CSS + KPIT Branding ──
st.markdown(f"""
<style>
    .workflow-step {{ padding: 4px 0; font-size: 0.9rem; }}
    .step-done {{ color: {KPIT_GREEN}; }}
    .step-active {{ color: #ffc107; }}
    .step-pending {{ color: #dc3545; }}
    div[data-testid="stMetric"] {{ text-align: center; }}

    /* KPIT green primary buttons */
    .stButton > button[kind="primary"],
    button[data-testid="stBaseButton-primary"] {{
        background-color: {KPIT_GREEN} !important;
        border-color: {KPIT_GREEN} !important;
    }}
    .stButton > button[kind="primary"]:hover,
    button[data-testid="stBaseButton-primary"]:hover {{
        background-color: {KPIT_GREEN_DARK} !important;
        border-color: {KPIT_GREEN_DARK} !important;
    }}

    /* KPIT green accents on tabs */
    button[data-baseweb="tab"][aria-selected="true"] {{
        color: {KPIT_GREEN} !important;
        border-bottom-color: {KPIT_GREEN} !important;
    }}

    /* Sidebar logo header */
    .kpit-sidebar-logo {{
        display: flex;
        align-items: center;
        gap: 10px;
        padding: 0 0 8px 0;
    }}
    .kpit-sidebar-logo svg {{
        color: {KPIT_GREEN};
        width: 60px;
        height: auto;
    }}
    .kpit-sidebar-logo .kpit-title {{
        font-size: 14px;
        font-weight: 700;
        color: #4a4a4a;
        line-height: 1.3;
    }}

    /* Main page branded header */
    .kpit-header {{
        display: flex;
        align-items: center;
        gap: 14px;
        margin-bottom: 10px;
    }}
    .kpit-header svg {{
        color: {KPIT_GREEN};
        width: 80px;
        height: auto;
    }}
    .kpit-header .kpit-header-text {{
        font-size: 28px;
        font-weight: 700;
        color: #4a4a4a;
    }}
    .kpit-header .kpit-header-sub {{
        font-size: 13px;
        color: #999;
        margin-top: 2px;
    }}
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

st.sidebar.markdown(
    f'<div class="kpit-sidebar-logo">{KPIT_LOGO_SVG}'
    '<div class="kpit-title">Vehicle Platform<br/>Builder</div></div>',
    unsafe_allow_html=True,
)

# ── Output Directory ──
_DEFAULT_OUTPUT_DIR = str(Path.home() / "kpit-vhal-output")
if "output_dir" not in st.session_state:
    st.session_state["output_dir"] = _DEFAULT_OUTPUT_DIR
st.sidebar.subheader("Output Directory")
output_dir = _folder_picker(
    "Output path", "output_dir",
    placeholder=_DEFAULT_OUTPUT_DIR, container=st.sidebar,
    help_text=f"Default: {_DEFAULT_OUTPUT_DIR}. VHAL source is pulled and generated code is written here.",
)
if not output_dir:
    output_dir = _DEFAULT_OUTPUT_DIR

# ── YAML Model Input ──
st.sidebar.subheader("YAML Model")
model_dir = _folder_picker(
    "Vehicle Model Directory", "model_dir",
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
    return f'<div class="workflow-step step-pending">● {label}</div>'


st.sidebar.markdown(
    _step_indicator(st.session_state.get("model_loaded", False), "1. Model Loaded")
    + _step_indicator(bool(st.session_state.get("mappings")), "2. Signals Classified")
    + _step_indicator(st.session_state.get("vhal_pulled", False), "3. VHAL Source Pulled")
    + _step_indicator(st.session_state.get("code_generated", False), "4. Code Generated")
    + _step_indicator(st.session_state.get("compile_checked", False), "5. Compile Check")
    + _step_indicator(st.session_state.get("deploy_tested", False), "6. Built & Deployed"),
    unsafe_allow_html=True,
)

# ═══════════════════════════════════════════════════════
# MAIN AREA
# ═══════════════════════════════════════════════════════

st.markdown(
    f'<div class="kpit-header">{KPIT_LOGO_SVG}'
    '<div><div class="kpit-header-text">Vehicle Platform Builder</div>'
    '</div></div>',
    unsafe_allow_html=True,
)

tab_ivi, tab_sdk = st.tabs(["Generate IVI Node SDK", "Generate Vehicle SDK"])

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
        st.warning("Set the YAML model directory in the sidebar and click **Load Model** to begin.")
    else:
        model = st.session_state["model"]
        mappings = st.session_state["mappings"]
        standard = [m for m in mappings if m.is_standard]
        vendor = [m for m in mappings if m.is_vendor]

        col1, col2, col3 = st.columns(3)
        col1.metric("Standard AOSP", len(standard))
        col2.metric("Vendor", len(vendor))
        col3.metric("Total Signals", len(mappings))

        if st.button("Re-classify Signals", help="Re-run signal classification after changing the model or mapping rules."):
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
            help="Source repository URL for Android VHAL code. Default points to official AOSP.",
        )
    with col_fetch:
        st.markdown("&nbsp;", unsafe_allow_html=True)
        if st.button("Fetch Tags", help="Query the repository for available Android 14 release tags."):
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

    # Store for auto-pull in Generate section
    st.session_state["vhal_tag"] = tag
    st.session_state["gerrit_url"] = gerrit_url

    if st.button("Pull VHAL Source", type="primary", help="Download Android VHAL source code from the repository into the output directory."):
        fetcher = GerritFetcher()
        fetcher.GERRIT_URL = gerrit_url
        target_dir = Path(st.session_state.get("output_dir", _DEFAULT_OUTPUT_DIR))
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

    st.caption("Target: **Android 14** (Android 15/16 on roadmap)")
    sdk_source_dir = _folder_picker(
        "Vehicle SDK Directory (optional)", "sdk_source_dir",
        help_text="Path to Vehicle SDK source directory. SDK files will be copied into the generated package.",
    )

    st.divider()

    # ─────────────────────────────────────────────
    # Section 3: Generate IVI Node SDK
    # ─────────────────────────────────────────────
    st.header("3. Generate IVI Node SDK")

    if not st.session_state.get("model_loaded"):
        st.warning("Set the YAML model directory in the sidebar and click **Load Model** to begin.")
    else:
        model = st.session_state["model"]
        mappings = st.session_state["mappings"]
        sdk_dir = st.session_state.get("sdk_source_dir", "")

        vhal_path = st.session_state.get("vhal_path", "")
        st.markdown(
            f"**Mappings:** {len(mappings)} signals · "
            f"**SDK:** {sdk_dir or 'not configured (optional)'} · "
            f"**VHAL tree:** {vhal_path or 'will be fetched automatically'}"
        )

        if st.button("Generate", type="primary"):
            # Auto-pull VHAL source if not already pulled
            if not st.session_state.get("vhal_pulled") or not vhal_path:
                tag = st.session_state.get("vhal_tag", "android-14.0.0_r75")
                gerrit_url = st.session_state.get(
                    "gerrit_url",
                    "https://android.googlesource.com/platform/hardware/interfaces",
                )
                target_dir = Path(st.session_state.get("output_dir", _DEFAULT_OUTPUT_DIR))
                fetcher = GerritFetcher()
                fetcher.GERRIT_URL = gerrit_url
                with st.status("Auto-pulling VHAL source...", expanded=True) as pull_st:
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
                        pull_st.update(label="VHAL source ready!", state="complete")
                    else:
                        pull_st.update(label="VHAL pull failed", state="error")

                if not vhal_path:
                    st.stop()

            vhal_root = Path(vhal_path)
            if not vhal_root.exists():
                st.error(f"VHAL directory not found: {vhal_root}")
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
                        st.session_state["diagram_blink"] = True

                    st.success(
                        f"Generated {len(generated)} files into `{bridge_dir}`"
                    )
                    st.rerun()
                except Exception as e:
                    st.error(f"Generation failed: {e}")

        if st.session_state.get("code_generated") and st.session_state.get("bridge_dir"):
            generated = st.session_state["generated_files"]
            bridge_dir = Path(st.session_state["bridge_dir"])

            # ── Architecture Diagram (shown after generation) ──
            has_sdk = bool(st.session_state.get("sdk_source_dir", ""))
            should_blink = st.session_state.pop("diagram_blink", False)
            st.html(_render_architecture_diagram(
                hl_bridge=True,
                hl_daemon=True,
                hl_vhal_service=True,
                hl_sdk=has_sdk,
                blink=should_blink,
            ))

            # Split generated files into SDK vs Test App
            test_app_names = {"VhalTestActivity.java", "AndroidManifest.xml",
                              "privapp-permissions-vhaltest.xml"}
            sdk_files = [f for f in generated if f.name not in test_app_names]
            test_files = [f for f in generated if f.name in test_app_names]

            dl_col1, dl_col2 = st.columns(2)

            # Download Vehicle SDK
            sdk_buf = io.BytesIO()
            with zipfile.ZipFile(sdk_buf, "w", zipfile.ZIP_DEFLATED) as zf:
                for f in sdk_files:
                    zf.write(f, f.relative_to(bridge_dir.parent))
            sdk_buf.seek(0)
            dl_col1.download_button(
                "Download Vehicle SDK",
                data=sdk_buf.getvalue(),
                file_name="vehicle-sdk.zip",
                mime="application/zip",
            )

            # Download Test App
            test_buf = io.BytesIO()
            with zipfile.ZipFile(test_buf, "w", zipfile.ZIP_DEFLATED) as zf:
                for f in test_files:
                    zf.write(f, f.relative_to(bridge_dir.parent))
            test_buf.seek(0)
            dl_col2.download_button(
                "Download Test App",
                data=test_buf.getvalue(),
                file_name="vehicle-test-app.zip",
                mime="application/zip",
            )

            # File preview (collapsed by default)
            with st.expander(f"Generated Files ({len(generated)})", expanded=False):
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
    st.header("4. Build & Deploy")

    runner = ShellRunner()

    # ── 4a. Local Verification ──
    st.subheader("4a. Local Verification")

    col_stub, col_e = st.columns(2)

    with col_stub:
        stub_clicked = st.button(
            "Compile Check",
            use_container_width=True,
            disabled=not st.session_state.get("code_generated", False),
            help="Validate generated code compiles against Android VHAL headers.",
        )
    with col_e:
        emulator_clicked = st.button(
            "Emulator Status",
            use_container_width=True,
            help="Check available Android Automotive emulators on this machine.",
        )

    if stub_clicked:
        vhal_path = st.session_state.get("vhal_path")
        if not vhal_path:
            st.warning("Generate code first (Section 3) before running compile check.")
        else:
            builder = StubBuilder()
            # Resolve SDK source dir with fallbacks:
            # 1. Session state sdk_source_dir (set by sidebar or Section 2)
            # 2. Auto-detect from vhal_path (walk up to find "output", go to parent)
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
                    # Auto-detect from vhal_path: walk up to find "output" dir
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
                    st.session_state["compile_checked"] = True

    if emulator_clicked:
        with st.status("Checking emulator...", expanded=True) as status:
            # Find emulator binary — check PATH first, then common SDK locations
            import shutil
            emu_bin = shutil.which("emulator")
            if not emu_bin:
                _sdk_search = [
                    Path("/opt/homebrew/share/android-commandlinetools/emulator/emulator"),
                    Path.home() / "Library/Android/sdk/emulator/emulator",
                    Path(os.environ.get("ANDROID_HOME", "")) / "emulator/emulator",
                    Path(os.environ.get("ANDROID_SDK_ROOT", "")) / "emulator/emulator",
                ]
                for p in _sdk_search:
                    if p.is_file():
                        emu_bin = str(p)
                        break
            if not emu_bin:
                st.warning(
                    "Emulator not found. Install Android SDK Emulator via "
                    "`sdkmanager 'emulator'` or Android Studio."
                )
                status.update(label="Emulator not available", state="error")
            else:
                rc, stdout, stderr = runner.run([emu_bin, "-list-avds"])
                if rc != 0:
                    st.warning(f"Emulator found at `{emu_bin}` but failed to list AVDs: {stderr.strip()}")
                    status.update(label="Emulator error", state="error")
                else:
                    avds = [l for l in stdout.strip().splitlines() if l.strip()]
                    automotive_avds = [a for a in avds if "auto" in a.lower() or "aaos" in a.lower() or "car" in a.lower()]
                    if avds:
                        st.write(f"Found **{len(avds)}** AVD(s):")
                        for avd in avds:
                            tag = " *(automotive)*" if avd in automotive_avds else ""
                            st.write(f"  - `{avd}`{tag}")
                        # Pick automotive AVD first, then first available
                        default_avd = automotive_avds[0] if automotive_avds else avds[0]
                        udp_port = config.EMULATOR_UDP_FORWARD_PORT
                        st.info(
                            "Start the automotive emulator with:\n\n"
                            "```bash\n"
                            f"{emu_bin} -avd {default_avd} -writable-system "
                            f"-qemu -net user,hostfwd=udp::{udp_port}-:{udp_port}\n"
                            "```\n\n"
                            f"UDP port {udp_port} is forwarded from host → emulator "
                            "for VSM Ethernet communication."
                        )
                    else:
                        st.warning("No AVDs found. Create one with Android Studio AVD Manager.")
                    status.update(label=f"Emulator ready ({len(avds)} AVD{'s' if len(avds) != 1 else ''})", state="complete")

    # ── 4b. Build & Deploy VHAL ──
    st.subheader("4b. Build & Deploy VHAL")

    # --- GCP Instance Config (collapsed by default) ---
    with st.expander("GCP Build Instance", expanded=False):
        col_inst, col_zone, col_proj = st.columns([3, 2, 2])
        with col_inst:
            gcp_instance_name = st.text_input(
                "Instance Name", key="gcp_instance_name",
                value="aosp-builder",
                help="Name of the GCP Compute Engine VM with an AOSP build environment.",
            )
        with col_zone:
            gcp_zone = st.text_input(
                "Zone", key="gcp_zone", value="us-central1-a",
            )
        with col_proj:
            gcp_project = st.text_input(
                "Project", key="gcp_project",
                value="vhal-builder",
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
                help="Stop the VM to save compute cost. Storage charges still apply while the disk exists.",
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
        st.success("Instance is running. Stop it when not in use to save costs.")
    elif vm_status == "TERMINATED":
        st.info("Instance is stopped. No compute charges apply.")
    elif vm_status == "STAGING":
        st.warning("Instance STAGING — starting up...")
    elif vm_status == "STOPPING":
        st.warning("Instance STOPPING ...")
    elif vm_status == "NOT_FOUND":
        st.error("Instance not found. Verify the instance name and zone are correct.")
    elif vm_status == "GCLOUD_ERROR":
        st.error("Cannot connect to GCP. Run `gcloud auth login` in your terminal to authenticate.")
    elif vm_status is not None:
        st.warning(f"Instance status: {vm_status}")

    # --- Three Tabs: Build on GCP / SSH / Use Local Artifacts ---
    tab_incr, tab_ssh, tab_full = st.tabs(["Build VHAL on GCP", "Remote Build (SSH)", "Use Pre-built Artifacts"])

    # -- Tab: Use Pre-built Artifacts --
    with tab_full:
        st.caption("Deploy pre-built VHAL artifacts to emulator (stored in `prebuilts/` by default).")

        # Default to repo prebuilts/ directory
        _default_prebuilts = str(Path(__file__).parent.parent / "prebuilts")
        deploy_artifact_dir = st.text_input(
            "Artifact Directory",
            key="deploy_artifact_dir",
            value=_default_prebuilts,
            help="Path containing the VHAL binary and DefaultProperties.json. Defaults to repo prebuilts/.",
        )

        deploy_full_clicked = st.button(
            "Deploy to Emulator", type="primary", use_container_width=True,
            disabled=not deploy_artifact_dir,
        )

        deploy_tested = st.session_state.get("deploy_tested", False)
        col_commit, col_push = st.columns(2)
        with col_commit:
            commit_vhal_clicked = st.button(
                "Commit VHAL Source",
                use_container_width=True,
                disabled=not deploy_tested,
            )
        with col_push:
            vhal_committed = st.session_state.get("vhal_committed", False)
            push_vhal_clicked = st.button(
                "Push VHAL Source",
                use_container_width=True,
                disabled=not vhal_committed,
            )
        if not deploy_tested:
            st.caption("Run a successful deploy test first to enable commit and push.")

    if deploy_full_clicked:
        if not deploy_artifact_dir or not Path(deploy_artifact_dir).is_dir():
            st.error("Provide a valid artifact directory containing the VHAL binary and DefaultProperties.json.")
        else:
            model_dir_val = st.session_state.get("model_dir", "")
            vhal_path_val = st.session_state.get("vhal_path", "")
            orchestrator = DeployOrchestrator()
            with st.status("Deploying pre-built artifacts...", expanded=True) as status:
                all_lines: list[str] = []
                for line in orchestrator.run(
                    model_dir=Path(model_dir_val) if model_dir_val else Path("."),
                    vhal_dir=Path(vhal_path_val) if vhal_path_val else Path("."),
                    skip_generate=True,
                    skip_build=True,
                    artifact_dir=Path(deploy_artifact_dir),
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
                    status.update(label="Deploy failed", state="error")
                else:
                    st.session_state["deploy_tested"] = True
                    status.update(label="Deploy complete!", state="complete")

    if commit_vhal_clicked:
        vhal_path_val = st.session_state.get("vhal_path", "")
        if not vhal_path_val or not Path(vhal_path_val).is_dir():
            st.error("VHAL source not found. Pull VHAL source or click Generate to auto-fetch it.")
        else:
            shell = ShellRunner()
            vhal_p = Path(vhal_path_val)
            with st.status("Committing VHAL source...", expanded=True) as status:
                # git add generated files
                rc, _, stderr = shell.run(
                    ["git", "-C", str(vhal_p), "add", "impl/bridge/", "impl/vhal/"],
                    timeout=30,
                )
                if rc != 0:
                    st.error(f"git add failed: {stderr.strip()}")
                    status.update(label="Commit failed", state="error")
                else:
                    st.write(":white_check_mark: Files staged")
                    # git commit
                    rc2, out2, stderr2 = shell.run(
                        ["git", "-C", str(vhal_p), "commit",
                         "-m", "vhal-gen: update generated VHAL bridge + daemon code"],
                        timeout=30,
                    )
                    if rc2 != 0:
                        st.error(f"git commit failed: {stderr2.strip()}")
                        status.update(label="Commit failed", state="error")
                    else:
                        st.write(f":white_check_mark: {out2.strip()}")
                        st.session_state["vhal_committed"] = True
                        status.update(label="VHAL source committed!", state="complete")

    if push_vhal_clicked:
        vhal_path_val = st.session_state.get("vhal_path", "")
        if not vhal_path_val or not Path(vhal_path_val).is_dir():
            st.error("VHAL source not found.")
        else:
            shell = ShellRunner()
            vhal_p = Path(vhal_path_val)
            with st.status("Pushing VHAL source to remote...", expanded=True) as status:
                rc, out, stderr = shell.run(
                    ["git", "-C", str(vhal_p), "push"],
                    timeout=120,
                )
                if rc != 0:
                    st.error(f"git push failed: {stderr.strip()}")
                    status.update(label="Push failed", state="error")
                else:
                    st.write(f":white_check_mark: {out.strip() or 'Pushed to remote'}")
                    st.session_state["vhal_pushed"] = True
                    status.update(label="VHAL source pushed!", state="complete")

    # -- Tab: Remote Build (SSH) --
    with tab_ssh:
        st.caption("Build via plain SSH/SCP — bypasses Zscaler/gcloud issues.")

        with st.expander("SSH Connection", expanded=True):
            col_ssh_host, col_ssh_user = st.columns(2)
            with col_ssh_host:
                ssh_host_val = st.text_input(
                    "SSH Host", key="ssh_host",
                    value="10.152.12.25",
                    help="IP address or hostname of the remote build machine.",
                )
            with col_ssh_user:
                ssh_user_val = st.text_input(
                    "SSH User", key="ssh_user",
                    value="vinoda",
                )
            col_ssh_pass, col_ssh_key = st.columns(2)
            with col_ssh_pass:
                ssh_password_val = st.text_input(
                    "SSH Password", key="ssh_password",
                    value="Vinod123",
                    type="password",
                    help="SSH password (uses sshpass for non-interactive auth).",
                )
            with col_ssh_key:
                ssh_key_val = st.text_input(
                    "SSH Key", key="ssh_key",
                    placeholder="~/.ssh/id_rsa (optional)",
                    help="Path to SSH private key. Leave blank to use default.",
                )
            col_ssh_aosp, _ = st.columns(2)
            with col_ssh_aosp:
                ssh_aosp_dir_val = st.text_input(
                    "AOSP Dir", key="ssh_aosp_dir",
                    value="/mnt/dev/ford-sdk",
                    help="Path to AOSP source tree on the remote machine.",
                )

            ssh_check_clicked = st.button(
                "Check Connection", use_container_width=True,
                disabled=not ssh_host_val,
                key="ssh_check_btn",
            )

        _has_generated_code_ssh = st.session_state.get("code_generated", False)
        ssh_skip_generate = st.checkbox(
            "Skip Generate", key="ssh_skip_generate",
            disabled=not _has_generated_code_ssh,
            help="Skip code generation (use already-generated code)." if _has_generated_code_ssh
            else "Generate code first (Step 3) before skipping.",
        )

        deploy_ssh_clicked = st.button(
            "Build & Deploy VHAL (SSH)",
            type="primary",
            use_container_width=True,
            disabled=not ssh_host_val,
            key="deploy_ssh_btn",
        )
        if not ssh_host_val:
            st.caption("Enter an SSH host above to enable this button.")

    if ssh_check_clicked:
        from vhal_gen.pipeline.ssh_builder import SshBuilder
        ssh_builder = SshBuilder(
            ssh_host=ssh_host_val,
            ssh_user=ssh_user_val,
            ssh_key=ssh_key_val,
            ssh_password=ssh_password_val,
            aosp_dir=ssh_aosp_dir_val,
        )
        with st.status("Checking SSH connection & build environment...", expanded=True) as ssh_status:
            ssh_ok = True
            for line in ssh_builder.check_connection():
                if line.startswith("PASS"):
                    st.write(f":white_check_mark: {line}")
                elif line.startswith("INFO"):
                    st.info(line.removeprefix("INFO "))
                elif line.startswith("ERROR:"):
                    st.error(line)
                    ssh_ok = False
            if ssh_ok:
                st.session_state["ssh_ready"] = True
                ssh_status.update(label="Remote build environment ready", state="complete")
            else:
                st.session_state["ssh_ready"] = False
                ssh_status.update(label="Remote environment check failed", state="error")

    if deploy_ssh_clicked:
        model_dir_val = st.session_state.get("model_dir", "")
        vhal_path_val = st.session_state.get("vhal_path", "")

        if not model_dir_val or not Path(model_dir_val).is_dir():
            st.error("Model not loaded. Set the YAML model directory in the sidebar and click Load Model.")
        elif not vhal_path_val or not Path(vhal_path_val).is_dir():
            st.error("VHAL source not found. Pull VHAL source or click Generate to auto-fetch it.")
        else:
            sdk_dir_val = st.session_state.get("sdk_source_dir", "")
            sdk_path_arg = Path(sdk_dir_val) if sdk_dir_val and Path(sdk_dir_val).is_dir() else None

            orchestrator = DeployOrchestrator()
            with st.status("Building VHAL via SSH and deploying...", expanded=True) as status:
                all_lines: list[str] = []
                for line in orchestrator.run(
                    model_dir=Path(model_dir_val),
                    vhal_dir=Path(vhal_path_val),
                    sdk_dir=sdk_path_arg,
                    skip_generate=ssh_skip_generate,
                    remote_ssh=True,
                    ssh_host=ssh_host_val,
                    ssh_user=ssh_user_val,
                    ssh_key=ssh_key_val,
                    ssh_password=ssh_password_val,
                    aosp_dir=ssh_aosp_dir_val,
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
                    status.update(label="SSH build & deploy failed", state="error")
                else:
                    st.session_state["deploy_tested"] = True
                    # Update prebuilts/ with fresh artifacts
                    import shutil
                    prebuilts_dir = Path(__file__).parent.parent / "prebuilts"
                    artifact_src = Path("artifacts") / "ssh-incremental"
                    if artifact_src.is_dir():
                        prebuilts_dir.mkdir(exist_ok=True)
                        for f in artifact_src.iterdir():
                            if f.is_file():
                                shutil.copy2(f, prebuilts_dir / f.name)
                        st.write(":white_check_mark: Updated prebuilts/ with new artifacts")
                    status.update(label="VHAL built (SSH) and deployed!", state="complete")

    # -- Tab: Build VHAL on GCP (default) --
    with tab_incr:
        st.caption("Sync generated code to GCP, build VHAL module (~5-15 min), pull binary back, and deploy to emulator.")

        _has_generated_code_incr = st.session_state.get("code_generated", False)
        incr_skip_generate = st.checkbox(
            "Skip Generate", key="incr_skip_generate",
            disabled=not _has_generated_code_incr,
            help="Skip code generation (use already-generated code)." if _has_generated_code_incr
            else "Generate code first (Step 3) before skipping.",
        )

        deploy_incr_clicked = st.button(
            "Build & Deploy VHAL",
            type="primary",
            use_container_width=True,
            disabled=not gcp_instance_name,
        )
        if not gcp_instance_name:
            st.caption("Enter a GCP instance name above to enable this button.")

    if deploy_incr_clicked:
        model_dir_val = st.session_state.get("model_dir", "")
        vhal_path_val = st.session_state.get("vhal_path", "")

        if not model_dir_val or not Path(model_dir_val).is_dir():
            st.error("Model not loaded. Set the YAML model directory in the sidebar and click Load Model.")
        elif not vhal_path_val or not Path(vhal_path_val).is_dir():
            st.error("VHAL source not found. Pull VHAL source or click Generate to auto-fetch it.")
        else:
            sdk_dir_val = st.session_state.get("sdk_source_dir", "")
            sdk_path_arg = Path(sdk_dir_val) if sdk_dir_val and Path(sdk_dir_val).is_dir() else None

            orchestrator = DeployOrchestrator()
            with st.status("Building VHAL on GCP and deploying...", expanded=True) as status:
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
                    status.update(label="Build & deploy failed", state="error")
                else:
                    st.session_state["deploy_tested"] = True
                    # Update prebuilts/ with fresh artifacts
                    import shutil as _shutil
                    _prebuilts_dir = Path(__file__).parent.parent / "prebuilts"
                    _artifact_src = Path("artifacts") / "incremental"
                    if _artifact_src.is_dir():
                        _prebuilts_dir.mkdir(exist_ok=True)
                        for _f in _artifact_src.iterdir():
                            if _f.is_file():
                                _shutil.copy2(_f, _prebuilts_dir / _f.name)
                        st.write(":white_check_mark: Updated prebuilts/ with new artifacts")
                    status.update(label="VHAL built and deployed!", state="complete")
