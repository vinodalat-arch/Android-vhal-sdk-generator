# KPIT Vehicle Platform Builder

A code generation tool that reads FLYNC YAML vehicle signal definitions and produces all C++ source, config, and build files needed to integrate vehicle signals into the Android VHAL (Vehicle Hardware Abstraction Layer) on Android Automotive 14.

## What It Does

1. **Parses** FLYNC YAML model files (PDU definitions, channels, signal layouts)
2. **Maps** vehicle signals to Android VehicleProperty IDs (standard AOSP + vendor)
3. **Generates** a complete VHAL integration package:
   - `BridgeVehicleHardware` — generic VHAL hardware implementation
   - `FlyncDaemon` — signal pack/unpack daemon with transport abstraction
   - `DefaultProperties.json` — property configuration loaded at boot
   - `VendorProperties.h` — vendor property ID constants
   - Build files, init config, and test APK
4. **Validates** generated code with a local compile check against AOSP headers
5. **Builds & deploys** to an Android Automotive emulator via GCP

## Quick Start

### Prerequisites

- Python 3.10+ (3.14 tested)
- `pip install pyyaml jinja2 click streamlit`

### Web UI

```bash
cd vhal-gen
.venv/bin/python -m streamlit run streamlit_app/app.py
```

Open http://localhost:8501 and follow the workflow:

1. Set YAML model directory in the sidebar → Load Model
2. Review signal mappings (standard AOSP vs vendor)
3. Click **Generate** (VHAL source is auto-fetched if needed)
4. Run **Compile Check** to validate
5. Deploy to GCP for a full AOSP build or incremental build

### CLI

```bash
# Generate VHAL code
vhal-gen generate ./flync-model-dev-2 -o ./output --transport mock

# Inspect parsed model
vhal-gen inspect ./flync-model-dev-2

# Classify signals
vhal-gen classify ./flync-model-dev-2

# Compile check against stubs
vhal-gen compile-check --vhal-dir <path> --sdk-dir <path>

# Full deploy-test pipeline
vhal-gen deploy-test ./flync-model-dev-2 --vhal-dir <path> --aosp-tag android-14.0.0_r75

# Incremental build on GCP instance
vhal-gen deploy-test ./flync-model-dev-2 --vhal-dir <path> \
  --incremental --gcp-instance <name> --gcp-zone us-central1-a

# Check GCP instance status
vhal-gen gcp-status --instance <name> --zone us-central1-a
```

## Architecture

```
Android Apps (CarPropertyManager)
        │ Binder
Car Service (AOSP, untouched)
        │ AIDL
VHAL Service
  ┌─────────────────────┐  ┌──────────────┐
  │ BridgeVehicleHardware│←→│ FlyncDaemon  │
  │     (GENERATED)      │  │  (GENERATED)  │
  └─────────────────────┘  └──────────────┘
        │ socketpair
Common SDK used by All Nodes
        │ Ethernet
Vehicle State Manager (Hardware)
```

The **Bridge** is a generic IPC forwarder (~200 lines). The **Daemon** contains all signal-specific pack/unpack logic. When the YAML model changes, only the daemon and property config are regenerated — no framework or CarService changes needed.

## Project Structure

```
├── vhal-gen/                    # Python tool
│   ├── streamlit_app/app.py     # Web UI (Streamlit)
│   ├── vhal_gen/
│   │   ├── cli.py               # CLI entry point
│   │   ├── parser/              # FLYNC YAML parser
│   │   ├── classifier/          # Signal → property mapper
│   │   ├── generator/           # Code generation engine
│   │   ├── templates/           # Jinja2 C++ templates
│   │   ├── builder/             # Stub compile checker
│   │   ├── pipeline/            # GCP build + deploy orchestrator
│   │   ├── fetcher/             # AOSP Gerrit source fetcher
│   │   ├── shell/               # Shell command runner
│   │   └── stubs/               # AOSP header stubs for local validation
│   └── tests/                   # 67 unit + integration tests
├── docs/                        # Technical documentation
├── flync-model-dev-2/           # Sample FLYNC YAML model
├── performance-stack-Body-lighting-Draft/  # Vehicle Body SDK reference
└── infra/                       # GCP infrastructure scripts
```

## Documentation

- [Project Overview](docs/PROJECT_OVERVIEW.md) — architecture, design decisions, usage
- [VHAL SDK Generator](docs/VHAL_SDK_GENERATOR.md) — comprehensive technical documentation
- [VHAL Architecture](docs/VHAL_ARCHITECTURE.md) — Android VHAL internals
- [Signal Mapping](docs/SIGNAL_MAPPING.md) — how signals map to VHAL properties
- [YAML Schema](docs/YAML_SCHEMA.md) — FLYNC YAML model format
- [Vehicle Network](docs/VEHICLE_NETWORK.md) — CAN/Ethernet network topology
- [Roadmap](docs/ROADMAP.md) — current scope and future plans

## Tests

```bash
cd vhal-gen
.venv/bin/python -m pytest tests/ -q
```

67 tests covering parser, classifier, generator, compile checker, GCP builder, and deploy orchestrator.

## Target Platform

- **Android 14** (AIDL VHAL) — primary target
- Android 15/16 on roadmap
- Runs on macOS and Linux (compile check uses platform-specific byte-order macros)
