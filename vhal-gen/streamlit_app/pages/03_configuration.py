"""Page 3: Configuration options for code generation."""

import streamlit as st

st.header("Configuration")

if "model" not in st.session_state:
    st.warning("Load a model first on the Model Loader page.")
    st.stop()

st.subheader("Android Version")
android_version = st.selectbox(
    "Target Android Version",
    options=["14"],
    index=0,
    help="Android 15/16 support is on the roadmap.",
)
st.session_state["android_version"] = android_version

st.subheader("Transport Mode")
transport = st.radio(
    "Daemon transport",
    options=["mock", "udp"],
    index=0,
    help="Mock: simulated signal values for emulator. UDP: live vehicle network.",
)
st.session_state["transport"] = transport

if transport == "udp":
    udp_addr = st.text_input("UDP Target Address", value="10.0.11.1")
    udp_port = st.number_input("UDP Port", value=5555, min_value=1, max_value=65535)
    st.session_state["udp_addr"] = udp_addr
    st.session_state["udp_port"] = udp_port
else:
    st.session_state["udp_addr"] = "10.0.11.1"
    st.session_state["udp_port"] = 5555

st.subheader("Output")
output_dir = st.text_input("Output Directory", value="./output")
st.session_state["output_dir"] = output_dir

st.success("Configuration saved. Go to the Generate page to generate code.")
