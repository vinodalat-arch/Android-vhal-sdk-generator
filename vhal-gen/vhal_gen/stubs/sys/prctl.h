/*
 * Stub <sys/prctl.h> for macOS compile-check.
 * On Android/Linux this is provided by bionic/glibc.
 */
#pragma once

#define PR_SET_PDEATHSIG 1

inline int prctl(int, ...) { return 0; }
