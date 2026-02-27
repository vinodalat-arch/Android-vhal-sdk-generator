"""Page 2: Review and override signal → property mappings."""

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from vhal_gen.classifier.signal_classifier import SignalClassifier

st.header("Signal Mapping")

if "model" not in st.session_state:
    st.warning("Load a model first on the Model Loader page.")
    st.stop()

model = st.session_state["model"]

if "mappings" not in st.session_state or st.button("Re-classify"):
    classifier = SignalClassifier()
    st.session_state["mappings"] = classifier.classify(model)

mappings = st.session_state["mappings"]

st.subheader(f"Mappings ({len(mappings)} signals)")

standard = [m for m in mappings if m.is_standard]
vendor = [m for m in mappings if m.is_vendor]

col1, col2 = st.columns(2)
col1.metric("Standard AOSP", len(standard))
col2.metric("Vendor", len(vendor))

st.subheader("Standard Property Mappings")
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

st.subheader("Vendor Property Mappings")
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
