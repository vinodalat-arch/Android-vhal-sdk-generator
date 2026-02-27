"""Page 1: Load and inspect FLYNC YAML model."""

import sys
from pathlib import Path

import streamlit as st

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from vhal_gen.parser.model_loader import load_flync_model

st.header("Model Loader")

model_dir = st.text_input(
    "FLYNC Model Directory",
    value="",
    placeholder="/path/to/flync-model-dev-2",
)

if st.button("Load Model") and model_dir:
    model_path = Path(model_dir)
    if not model_path.exists():
        st.error(f"Directory not found: {model_path}")
    else:
        try:
            with st.spinner("Parsing YAML files..."):
                model = load_flync_model(model_path)
            st.session_state["model"] = model
            st.success(
                f"Loaded {len(model.pdus)} PDUs, "
                f"{sum(len(p.signals) for p in model.pdus.values())} signals"
            )
        except Exception as e:
            st.error(f"Failed to load model: {e}")

if "model" in st.session_state:
    model = st.session_state["model"]

    st.subheader("PDUs")
    pdu_data = []
    for name, pdu in sorted(model.pdus.items()):
        pdu_data.append({
            "Name": name,
            "ID": f"0x{pdu.pdu_id:X}",
            "Length (bytes)": pdu.length,
            "Signals": len(pdu.signals),
            "Direction": pdu.direction.value,
        })
    st.dataframe(pdu_data, use_container_width=True)

    st.subheader("Signals")
    for pdu_name, pdu in sorted(model.pdus.items()):
        if not pdu.signals:
            continue
        with st.expander(f"{pdu_name} (0x{pdu.pdu_id:X}, {pdu.direction.value})"):
            sig_data = []
            for sig in pdu.signals:
                sig_data.append({
                    "Name": sig.name,
                    "Start Bit": sig.start_bit,
                    "Bit Length": sig.bit_length,
                    "Type": sig.base_data_type,
                    "Endianness": sig.endianness,
                    "Range": f"[{sig.lower_limit}-{sig.upper_limit}]",
                    "Values": ", ".join(
                        f"{v.num_value}={v.description}" for v in sig.value_table
                    ) if sig.value_table else "",
                })
            st.dataframe(sig_data, use_container_width=True)

    if model.global_states:
        st.subheader("Global States")
        gs_data = []
        for gs in model.global_states:
            gs_data.append({
                "ID": gs.state_id,
                "Name": gs.name,
                "Default": gs.is_default,
                "Participants": ", ".join(gs.participants),
            })
        st.dataframe(gs_data, use_container_width=True)
