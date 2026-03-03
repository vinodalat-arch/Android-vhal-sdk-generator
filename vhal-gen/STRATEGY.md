# VHAL SDK Generator — Design & Strategy Analysis

## Current Architecture

```
FLYNC YAML → Parser → Classifier → Generator → Compile Check
                         │
              ┌──────────┴──────────┐
              │ 14 exact-match rules │ ← only path to standard AOSP properties
              │ 266 property IDs     │ ← complete catalog (fixed 2026-03-03)
              │ Vendor fallback      │ ← silent, no warnings
              └─────────────────────┘
```

### What Works Well

- Parser is complete and self-contained (YAML → FlyncModel)
- Code generation is template-driven, no external reads
- Compile check works offline via 6 stub headers (macOS + Linux)
- Vendor ID allocation is deterministic (counter-based, idempotent)
- All 266 AOSP property IDs correct and baked into `standard_properties.py`
- No LLM/ML dependencies — entire pipeline is deterministic

### What Is Broken or Missing

| # | Finding | Severity |
|---|---------|----------|
| 1 | Only **14 of 266** standard properties have mapping rules (5.3% coverage) | CRITICAL |
| 2 | Vendor fallback is **silent** — no warning when a signal should be standard but isn't matched | HIGH |
| 3 | No **property metadata** beyond IDs (type, area, access, change_mode, defaults) for 266 properties | HIGH |
| 4 | `--vhal-dir` is required but is only an **output target** — nothing is read from it that isn't stubbed | MEDIUM |
| 5 | Area-specific handling exists only for **DOOR_LOCK** — no SEAT/WINDOW/MIRROR/WHEEL support | MEDIUM |
| 6 | Dispatcher only handles **INT32 and BOOLEAN** — no FLOAT dispatch in daemon code | MEDIUM |
| 7 | Vendor properties always get **GLOBAL area** and **ON_CHANGE mode** — no variation possible | MEDIUM |
| 8 | No validation that a mapping rule's `property_name` exists in `STANDARD_PROPERTIES` | LOW |

### Current Signal Inventory (flync-model-dev-2)

- **10 PDUs, 68 signals total** (61 after skipping crc16/counter housekeeping)
- **14 signals → 10 standard AOSP properties** (lights, doors, speed, night mode)
- **47 signals → 26 vendor properties** (silent fallback)
- Only categories covered: exterior lighting, door locks, vehicle speed, night mode
- Missing: HVAC, powertrain, chassis, infotainment, safety, seats, windows, mirrors

---

## Strategic Options

### Option A: Enriched Property Catalog + Pattern Rules

**Approach:** Augment `standard_properties.py` with full metadata (type, area, access, change_mode) for all 266 properties. Add pattern-based matching rules alongside exact-match rules. Add a suggestion engine that warns when vendor-fallback signals look like they should be standard.

**Changes:**

1. `standard_properties.py` becomes a rich metadata catalog:

```python
STANDARD_PROPERTIES = {
    "DOOR_LOCK": {
        "id": 0x16200B02,
        "type": VehiclePropertyType.BOOLEAN,
        "area": VehicleArea.DOOR,
        "access": VehiclePropertyAccess.READ_WRITE,
        "change_mode": VehiclePropertyChangeMode.ON_CHANGE,
        "keywords": ["door", "lock", "unlock"],
    },
    "HVAC_FAN_SPEED": {
        "id": 0x15400500,
        "type": VehiclePropertyType.INT32,
        "area": VehicleArea.SEAT,
        "access": VehiclePropertyAccess.READ_WRITE,
        "change_mode": VehiclePropertyChangeMode.ON_CHANGE,
        "keywords": ["fan", "speed", "hvac", "blower"],
    },
    # ... all 266
}
```

2. `mapping_rules.py` gains pattern rules:

```python
PATTERN_RULES = [
    {"pattern": r".*[Dd]oor.*[Ll]ock.*", "property_name": "DOOR_LOCK"},
    {"pattern": r".*[Ff]an.*[Ss]peed.*", "property_name": "HVAC_FAN_SPEED"},
    {"pattern": r".*[Tt]ire.*[Pp]ress.*", "property_name": "TIRE_PRESSURE"},
    # ...
]
```

3. `signal_classifier.py` becomes 3-phase:
   - Phase 1: Exact match (existing, highest priority)
   - Phase 2: Pattern match (new, yields **suggestion** not auto-map)
   - Phase 3: Vendor fallback (existing, lowest priority)

4. Classifier emits warnings:

```
WARNING: Signal "u8_FanSpeed_req" has no exact rule but matches pattern for HVAC_FAN_SPEED.
         Add to EXACT_MATCH_RULES to use standard property.
```

**Benefits:**
- Complete AOSP awareness (266 properties with full metadata)
- Pattern matching catches likely standard properties (deterministic regex, no LLM)
- Warnings prevent silent vendor fallback for signals that should be standard
- New rules are easy to add (one dict entry per signal)
- Property metadata enables auto-validation (rule says BOOLEAN but AOSP expects INT32 → error)

**Effort:** Medium (2-3 days)

---

### Option B: VHAL Scaffold — Eliminate `--vhal-dir` Requirement

**Approach:** Ship a minimal AOSP VHAL scaffold inside the package so the generator can produce a complete, buildable VHAL tree from scratch without needing a pre-cloned AOSP source.

**Changes:**

1. Ship scaffold files in `vhal_gen/scaffold/`:
   - `VehicleService.cpp` (pre-patched to use BridgeVehicleHardware)
   - `vhal/Android.bp` (pre-patched with bridge deps)
   - `hardware/include/IVehicleHardware.h` (real header, not stub)
   - Directory structure matching `impl/bridge/`, `impl/vhal/`

2. Generator gains `--output-dir` mode:

```bash
# Current (requires AOSP checkout):
vhal-gen generate model/ --vhal-dir /path/to/aosp/automotive/vehicle/aidl

# New (fully standalone):
vhal-gen generate model/ --output-dir output/my-vhal
```

3. Scaffold auto-copied when `--output-dir` used instead of `--vhal-dir`.

**Benefits:**
- Zero AOSP dependency for generate + compile-check
- Users don't need to clone 50MB of AOSP source just to run the generator
- Scaffold versioned with the tool (always compatible)
- `--vhal-dir` still works for users who have an AOSP checkout

**Effort:** Low (1 day)

---

### Option C: Full Property Metadata from AIDL Spec (One-Time Extraction)

**Approach:** Parse the AOSP `VehicleProperty.aidl` comments and `emu_metadata` JSON to extract complete metadata for all 266 properties — not just IDs but type, area, access, change mode, units, min/max ranges — and bake it all into the tool.

**Changes:**

1. One-time script produces `aosp_property_catalog.py`:

```python
PROPERTY_CATALOG = {
    "PERF_VEHICLE_SPEED": PropertyDef(
        id=0x11600207,
        type=VehiclePropertyType.FLOAT,
        area=VehicleArea.GLOBAL,
        access=VehiclePropertyAccess.READ,
        change_mode=VehiclePropertyChangeMode.CONTINUOUS,
        unit="m/s",
        min_value=0.0,
        max_value=200.0,
        description="Speed of the vehicle in meters per second",
        data_enum=None,
    ),
    "HVAC_FAN_SPEED": PropertyDef(
        id=0x15400500,
        type=VehiclePropertyType.INT32,
        area=VehicleArea.SEAT,
        access=VehiclePropertyAccess.READ_WRITE,
        change_mode=VehiclePropertyChangeMode.ON_CHANGE,
        unit=None,
        min_value=0,
        max_value=10,
        description="Fan speed setting",
        data_enum=None,
    ),
    # ... all 266 with full metadata
}
```

2. Classifier uses catalog to auto-fill type/area/access when creating rules (rules become simpler — just signal_name → property_name).

3. Validation at classify time:
   - Rule says `type: BOOLEAN` but catalog says `type: INT32` → ERROR
   - Rule says `area: GLOBAL` but catalog says `area: DOOR` → WARNING
   - Rule's `change_mode` doesn't match catalog → WARNING

**Benefits:**
- Gold-standard property definitions baked into the tool
- Rules become simpler (just signal_name → property_name, metadata auto-filled from catalog)
- Cross-validation catches config errors at classify time, not at runtime on emulator
- Foundation for Option A's pattern matching (keywords extracted from descriptions)

**Effort:** Medium (2-3 days)

---

### Option D: Interactive Rule Builder in Streamlit UI

**Approach:** Add a "Signal Mapping" tab to Streamlit that shows unmatched signals alongside the 266 AOSP properties, letting the user create mapping rules through a UI instead of editing Python files.

**Changes:**

1. New Streamlit tab: "Signal Mapping"
   - Left column: Unmatched vendor signals from current model
   - Right column: Searchable AOSP property list (266 entries)
   - User selects signal → property mapping
   - UI generates the rule entry
   - "Save Rules" writes to a YAML sidecar file

2. Export/import rules as YAML (not hardcoded Python):

```yaml
mappings:
  - signal: "u8_FanSpeed_req"
    property: "HVAC_FAN_SPEED"
    area: SEAT
    area_id: 0
  - signal: "bo_ParkBrake_Sts"
    property: "PARKING_BRAKE_ON"
```

3. Rules file alongside model (not in package code):
   - `model_dir/mapping_overrides.yaml`
   - Loaded at classify time, merged with built-in EXACT_MATCH_RULES

**Benefits:**
- Non-developers can create mappings without editing Python
- Rules travel with the model (version-controlled alongside YAML)
- Built-in rules still work as defaults
- Per-project customization without forking the tool

**Effort:** Medium (2-3 days)

---

## Recommendation

### Phase 1 (Immediate): Option C + Option B

- **Option C** — Extract full property metadata catalog for all 266 properties. This is the foundation everything else builds on. Rules become simpler, validation catches errors early, and the tool has complete AOSP awareness.
- **Option B** — Add scaffold mode to eliminate the last AOSP source dependency. Generator works fully standalone with `--output-dir`.
- **Result:** Tool is truly self-contained for parse → classify → generate → compile-check. No AOSP checkout needed. No LLM. No network.

### Phase 2 (Next Sprint): Option A

- Pattern rules + suggestion warnings built on top of Phase 1's metadata catalog.
- Prevents silent vendor fallback for signals that should be standard.
- Deterministic regex matching — no LLM/ML.
- **Result:** Classifier actively helps users find correct AOSP mappings instead of silently falling back to vendor IDs.

### Phase 3 (When Model Grows Beyond 100 Signals): Option D

- Interactive rule builder in Streamlit UI.
- YAML sidecar rules enable per-project customization.
- **Result:** Scales to many users and models without code changes.

### Principles

All four options are **100% deterministic** — no LLM/ML dependencies anywhere. Classification remains: exact-match → pattern-match → vendor-fallback, all via static dict/regex lookup. The tool stays fully self-contained from YAML input through compile check.
