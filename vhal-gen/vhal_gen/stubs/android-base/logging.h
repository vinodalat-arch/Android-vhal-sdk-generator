/*
 * Stub android-base/logging.h -- provides no-op LOG macros so generated
 * bridge code compiles locally without the Android logging library.
 *
 * Used exclusively for local compile-check; not shipped to device.
 */
#pragma once

#include <iostream>
#include <sstream>

namespace android::base {

enum LogSeverity { VERBOSE, DEBUG, INFO, WARNING, ERROR, FATAL };

// Sink that discards everything streamed into it.
class NullLogMessage {
  public:
    NullLogMessage() = default;
    ~NullLogMessage() = default;

    template <typename T>
    NullLogMessage& operator<<(const T&) { return *this; }

    // Support for manipulators like std::endl.
    NullLogMessage& operator<<(std::ostream& (*)(std::ostream&)) { return *this; }
};

inline void InitLogging(char** /*argv*/,
                        ...) {}  // variadic to accept any logger arg

// Logger type that AOSP code passes to InitLogging.
struct LogdLogger {
    void operator()(LogSeverity, const char*, unsigned int,
                    const char*) {}
};

}  // namespace android::base

// LOG(severity) expands to a discarding stream.
#define LOG(severity) ::android::base::NullLogMessage()

// ALOGI / ALOGE / etc. -- printf-style, just discard.
#define ALOGI(...) ((void)0)
#define ALOGD(...) ((void)0)
#define ALOGW(...) ((void)0)
#define ALOGE(...) ((void)0)
#define ALOGV(...) ((void)0)
