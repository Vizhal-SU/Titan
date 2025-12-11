#pragma once
#include <pthread.h>
#include <iostream>
#include <vector>
#include <format>

inline void pin_thread_to_core(int core_id) {
    // 1. Create the CPU Set
    cpu_set_t cpuset;
    CPU_ZERO(&cpuset);
    CPU_SET(core_id, &cpuset);

    // 2. Pin the CURRENT thread
    pthread_t current_thread = pthread_self();
    int rc = pthread_setaffinity_np(current_thread, sizeof(cpu_set_t), &cpuset);

    if (rc != 0) {
        std::cerr << std::format("[SYSTEM] Failed to pin thread to Core {}: Error {}", core_id, rc) << std::endl;
    } else {
        std::cout << std::format("[SYSTEM] Thread successfully pinned to Core {}", core_id) << std::endl;
    }
}