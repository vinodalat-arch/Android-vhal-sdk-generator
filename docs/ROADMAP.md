# Roadmap

## Current Scope (v1.0)
- Android 14 AIDL VHAL support
- FLYNC YAML parsing (PDU, channels, VSM)
- Deterministic signal → property mapping (exact match + vendor)
- Code generation: BridgeVehicleHardware, FlyncDaemon, transports
- Single VHAL project build (daemon built alongside bridge)
- Mock transport for emulator testing
- CLI tool (generate, inspect, classify)
- Streamlit web UI
- Unit and integration tests

## Future (v1.1+)

### Android 15/16 Support
- VHAL AIDL interface changes between versions
- Templatize for target Android version
- Property ID compatibility matrix

### Docker-Based AOSP Build
- Container with AOSP build environment
- Build VHAL module without full AOSP tree on host
- CI/CD integration for automated builds

### Cloud Build Service
- Upload YAML model → get built VHAL binaries
- Pre-built AOSP build environment in cloud
- API for programmatic access

### Full Emulator Validation Pipeline
- Auto-launch Android emulator with generated VHAL
- Run test APK automatically
- Report pass/fail for all properties
- Integration with CI/CD

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
