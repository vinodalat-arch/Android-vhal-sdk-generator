# Roadmap

## Current Scope (v1.0)
- Android 14 AIDL VHAL support
- FLYNC YAML parsing (PDU, channels, VSM)
- Deterministic signal → property mapping (exact match + vendor)
- Code generation: BridgeVehicleHardware, FlyncDaemon, transports
- Single VHAL project build (daemon built alongside bridge)
- Mock transport for emulator testing
- CLI tool (generate, inspect, classify, compile-check, deploy-test, gcp-status)
- Streamlit web UI
- Unit and integration tests
- **Compile check (stubs)** — local `clang++ -fsyntax-only` validation of the entire
  daemon codebase (generated bridge + SDK reference code, 8 files) using A14-compatible
  stub headers, available from both CLI and Web UI
- **Deploy-test pipeline** — full GCP build via GitHub Actions (~2 hours), artifact
  download, emulator deployment, and property verification — all from CLI or Web UI
- **Incremental GCP build** — sync code to a pre-existing GCP Compute Engine instance,
  run `mma` incremental build (~5–15 min), and pull artifacts back. GCP instance status
  check available via `gcp-status` CLI command and Streamlit UI status card

## Future (v1.1+)

### Android 15/16 Support
- VHAL AIDL interface changes between versions
- Templatize for target Android version
- Property ID compatibility matrix

### Docker-Based AOSP Build
- Container with AOSP build environment
- Build VHAL module without full AOSP tree on host
- CI/CD integration for automated builds

### CI/CD for Auto-Regeneration
- Watch YAML model repo for changes
- Auto-regenerate code on model updates
- Auto-build and validate
- Notification on failures

### Extended Signal Support
- Additional PDU types beyond body/lighting
- Powertrain, chassis, ADAS signals
- Multi-domain signal mapping

### Enhanced Streamlit UI
- Visual signal bit-layout editor
- Property override persistence
- Diff view for regeneration
- Export/import mapping configurations
