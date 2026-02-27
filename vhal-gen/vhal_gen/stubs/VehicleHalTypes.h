/*
 * Stub VehicleHalTypes.h — type definitions matching Android 14 AIDL spec.
 *
 * Shadows the real AOSP VehicleHalTypes.h (which #includes 100+ AIDL-generated
 * headers that only exist inside a full AOSP build tree).
 *
 * All types, field names, enum values, and defaults are derived from the
 * Android 14 (android-14.0.0_r1) AIDL interface definitions at:
 *   hardware/interfaces/automotive/vehicle/aidl/android/hardware/automotive/vehicle/
 * and the HAL implementation interface at:
 *   hardware/interfaces/automotive/vehicle/aidl/impl/hardware/include/IVehicleHardware.h
 *
 * This file is NOT shipped to the device; it is used exclusively by
 * `vhal-gen compile-check` / the "Compile Check (Stubs)" UI button.
 */
#pragma once

#include <cstdint>
#include <functional>
#include <memory>
#include <optional>
#include <string>
#include <vector>

// ═══════════════════════════════════════════════════════════════════════════
// AIDL-generated types — android-14.0.0 automotive/vehicle AIDL interface
// ═══════════════════════════════════════════════════════════════════════════

namespace aidl::android::hardware::automotive::vehicle {

// --- StatusCode.aidl -------------------------------------------------------
enum class StatusCode : int32_t {
    OK = 0,
    TRY_AGAIN = 1,
    INVALID_ARG = 2,
    NOT_AVAILABLE = 3,
    ACCESS_DENIED = 4,
    INTERNAL_ERROR = 5,
    NOT_AVAILABLE_DISABLED = 6,
    NOT_AVAILABLE_SPEED_LOW = 7,
    NOT_AVAILABLE_SPEED_HIGH = 8,
    NOT_AVAILABLE_POOR_VISIBILITY = 9,
    NOT_AVAILABLE_SAFETY = 10,
};

// --- VehiclePropertyAccess.aidl --------------------------------------------
enum class VehiclePropertyAccess : int32_t {
    NONE = 0x00,
    READ = 0x01,
    WRITE = 0x02,
    READ_WRITE = 0x03,
};

// --- VehiclePropertyChangeMode.aidl ----------------------------------------
enum class VehiclePropertyChangeMode : int32_t {
    STATIC = 0x00,
    ON_CHANGE = 0x01,
    CONTINUOUS = 0x02,
};

// --- VehiclePropertyStatus.aidl --------------------------------------------
enum class VehiclePropertyStatus : int32_t {
    AVAILABLE = 0x00,
    UNAVAILABLE = 0x01,
    ERROR = 0x02,
};

// --- RawPropValues.aidl ----------------------------------------------------
struct RawPropValues {
    std::vector<int32_t> int32Values = {};
    std::vector<float> floatValues;
    std::vector<int64_t> int64Values;
    std::vector<uint8_t> byteValues;
    std::string stringValue;
};

// --- VehiclePropValue.aidl -------------------------------------------------
struct VehiclePropValue {
    int64_t timestamp = 0;
    int32_t areaId = 0;
    int32_t prop = 0;
    VehiclePropertyStatus status = VehiclePropertyStatus::AVAILABLE;
    RawPropValues value;
};

// --- VehicleAreaConfig.aidl ------------------------------------------------
struct VehicleAreaConfig {
    int32_t areaId = 0;
    int32_t minInt32Value = 0;
    int32_t maxInt32Value = 0;
    int64_t minInt64Value = 0;
    int64_t maxInt64Value = 0;
    float minFloatValue = 0.0f;
    float maxFloatValue = 0.0f;
    // @nullable long[] supportedEnumValues — represented as optional
    std::optional<std::vector<int64_t>> supportedEnumValues;
};

// --- VehiclePropConfig.aidl ------------------------------------------------
struct VehiclePropConfig {
    int32_t prop = 0;
    VehiclePropertyAccess access = VehiclePropertyAccess::NONE;
    VehiclePropertyChangeMode changeMode = VehiclePropertyChangeMode::STATIC;
    std::vector<VehicleAreaConfig> areaConfigs;
    std::vector<int32_t> configArray;
    std::string configString;
    float minSampleRate = 0.0f;
    float maxSampleRate = 0.0f;
};

// --- GetValueRequest.aidl --------------------------------------------------
struct GetValueRequest {
    int64_t requestId = 0;
    VehiclePropValue prop;
};

// --- GetValueResult.aidl ---------------------------------------------------
struct GetValueResult {
    int64_t requestId = 0;
    StatusCode status = StatusCode::OK;
    // @nullable — may be absent when status != OK
    std::optional<VehiclePropValue> prop;
};

// --- SetValueRequest.aidl --------------------------------------------------
struct SetValueRequest {
    int64_t requestId = 0;
    VehiclePropValue value;
};

// --- SetValueResult.aidl ---------------------------------------------------
struct SetValueResult {
    int64_t requestId = 0;
    StatusCode status = StatusCode::OK;
};

// --- SubscribeOptions.aidl -------------------------------------------------
struct SubscribeOptions {
    int32_t propId = 0;
    std::vector<int32_t> areaIds;
    float sampleRate = 0.0f;
};

}  // namespace aidl::android::hardware::automotive::vehicle

// ═══════════════════════════════════════════════════════════════════════════
// IVehicleHardware — HAL implementation interface (A14)
// Source: impl/hardware/include/IVehicleHardware.h
// ═══════════════════════════════════════════════════════════════════════════

namespace android::hardware::automotive::vehicle {

using ::aidl::android::hardware::automotive::vehicle::GetValueRequest;
using ::aidl::android::hardware::automotive::vehicle::GetValueResult;
using ::aidl::android::hardware::automotive::vehicle::SetValueRequest;
using ::aidl::android::hardware::automotive::vehicle::SetValueResult;
using ::aidl::android::hardware::automotive::vehicle::StatusCode;
using ::aidl::android::hardware::automotive::vehicle::SubscribeOptions;
using ::aidl::android::hardware::automotive::vehicle::VehiclePropConfig;
using ::aidl::android::hardware::automotive::vehicle::VehiclePropValue;

// --- DumpResult (from IVehicleHardware.h) ----------------------------------
struct DumpResult {
    bool callerShouldDumpState = false;
    std::string buffer;
    bool refreshPropertyConfigs = false;
};

// --- SetValueErrorEvent (from IVehicleHardware.h) --------------------------
struct SetValueErrorEvent {
    StatusCode errorCode;
    int32_t propId;
    int32_t areaId;
};

// --- Callback type aliases (from IVehicleHardware.h) -----------------------
using GetValuesCallback = std::function<void(std::vector<GetValueResult>)>;
using SetValuesCallback = std::function<void(std::vector<SetValueResult>)>;
using PropertyChangeCallback = std::function<void(std::vector<VehiclePropValue>)>;
using PropertySetErrorCallback = std::function<void(std::vector<SetValueErrorEvent>)>;

// --- IVehicleHardware abstract class (from IVehicleHardware.h) -------------
class IVehicleHardware {
  public:
    virtual ~IVehicleHardware() = default;

    virtual std::vector<VehiclePropConfig> getAllPropertyConfigs() const = 0;

    virtual StatusCode getValues(
            std::shared_ptr<const GetValuesCallback> callback,
            const std::vector<GetValueRequest>& requests) const = 0;

    virtual StatusCode setValues(
            std::shared_ptr<const SetValuesCallback> callback,
            const std::vector<SetValueRequest>& requests) = 0;

    virtual DumpResult dump(const std::vector<std::string>& options) = 0;

    virtual StatusCode checkHealth() = 0;

    virtual void registerOnPropertyChangeEvent(
            std::unique_ptr<const PropertyChangeCallback> callback) = 0;

    virtual void registerOnPropertySetErrorEvent(
            std::unique_ptr<const PropertySetErrorCallback> callback) = 0;

    // Non-pure virtual in A14 — default returns OK.
    virtual StatusCode updateSampleRate(
            int32_t /* propId */, int32_t /* areaId */, float /* sampleRate */) {
        return StatusCode::OK;
    }
};

}  // namespace android::hardware::automotive::vehicle
