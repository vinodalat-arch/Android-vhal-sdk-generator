"""Main Streamlit entry point for vhal-gen UI."""

import streamlit as st

st.set_page_config(
    page_title="vhal-gen",
    page_icon="🚗",
    layout="wide",
)

st.title("vhal-gen: FLYNC YAML → Android VHAL Code Generator")
st.markdown("""
Select a page from the sidebar to get started:
1. **Model Loader** — Load and inspect your FLYNC YAML model
2. **Signal Mapping** — Review and override signal → property mappings
3. **Configuration** — Set output options (transport, Android version)
4. **Generate** — Generate code and download output
""")

st.sidebar.success("Select a page above.")
