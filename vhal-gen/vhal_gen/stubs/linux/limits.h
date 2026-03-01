// Stub linux/limits.h for macOS compile check.
// On Linux these are defined in <linux/limits.h>; on macOS they come
// from <limits.h> / <sys/syslimits.h>.
// Also provides struct itimerspec (Linux <time.h>) used by iceoryx.
#pragma once

#include <limits.h>
#include <time.h>

#ifndef PATH_MAX
#define PATH_MAX 4096
#endif

// struct itimerspec is defined in <time.h> on Linux but not on macOS.
// iceoryx iox::Duration has a constructor that takes itimerspec by reference.
#ifndef __linux__
#ifndef _STRUCT_ITIMERSPEC
#define _STRUCT_ITIMERSPEC
struct itimerspec {
    struct timespec it_interval;
    struct timespec it_value;
};
#endif
#endif
