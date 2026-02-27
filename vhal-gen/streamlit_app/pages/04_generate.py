"""Page 4: Generate code and preview output."""

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from vhal_gen.classifier.signal_classifier import SignalClassifier
from vhal_gen.generator.generator_engine import GeneratorEngine

st.header("Generate")

if "model" not in st.session_state:
    st.warning("Load a model first on the Model Loader page.")
    st.stop()

model = st.session_state["model"]
transport = st.session_state.get("transport", "mock")
output_dir = st.session_state.get("output_dir", "./output")
udp_addr = st.session_state.get("udp_addr", "10.0.11.1")
udp_port = st.session_state.get("udp_port", 5555)

# Ensure mappings exist
if "mappings" not in st.session_state:
    classifier = SignalClassifier()
    st.session_state["mappings"] = classifier.classify(model)

mappings = st.session_state["mappings"]

st.write(f"**Transport:** {transport}")
st.write(f"**Output:** {output_dir}")
st.write(f"**Mappings:** {len(mappings)} signals")

if st.button("Generate Code", type="primary"):
    out_path = Path(output_dir)

    with st.spinner("Generating..."):
        engine = GeneratorEngine(
            mappings=mappings,
            model=model,
            transport=transport,
            udp_addr=udp_addr,
            udp_port=udp_port,
        )
        generated = engine.generate(out_path)

    st.success(f"Generated {len(generated)} files!")

    st.subheader("Generated Files")
    for f in generated:
        rel = f.relative_to(out_path)
        with st.expander(str(rel)):
            content = f.read_text()
            lang = "cpp" if f.suffix in (".cpp", ".h") else "json" if f.suffix == ".json" else "java" if f.suffix == ".java" else "xml" if f.suffix == ".xml" else "text"
            st.code(content, language=lang)
