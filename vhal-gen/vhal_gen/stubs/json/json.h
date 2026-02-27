/*
 * Stub json/json.h -- minimal jsoncpp API surface so generated bridge code
 * compiles locally. Only the members actually used by BridgeVehicleHardware
 * are provided.
 *
 * Used exclusively for local compile-check; not shipped to device.
 */
#pragma once

#include <cstddef>
#include <istream>
#include <memory>
#include <string>
#include <vector>

namespace Json {

class Value {
  public:
    Value() = default;
    Value(int) {}
    Value(const char*) {}
    Value(const std::string&) {}

    // Type checks
    bool isObject() const { return false; }
    bool isArray() const { return false; }
    bool isMember(const std::string&) const { return false; }
    bool isMember(const char*) const { return false; }

    // Accessors
    std::string asString() const { return {}; }
    int asInt() const { return 0; }
    float asFloat() const { return 0.0f; }
    double asDouble() const { return 0.0; }
    bool asBool() const { return false; }

    // Subscript
    Value operator[](const std::string&) const { return {}; }
    Value operator[](const char*) const { return {}; }
    Value operator[](int) const { return {}; }

    // Range-based for support (iterate over array elements)
    const Value* begin() const { return nullptr; }
    const Value* end() const { return nullptr; }

    std::size_t size() const { return 0; }
};

class CharReaderBuilder {
  public:
    CharReaderBuilder() = default;
};

// Free function used by BridgeVehicleHardware.cpp
inline bool parseFromStream(
        const CharReaderBuilder&, std::istream&, Value*, std::string*) {
    return true;
}

}  // namespace Json
