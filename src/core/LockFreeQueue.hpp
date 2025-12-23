#pragma once
#include <atomic>
#include <vector>
#include <optional>
#include <cstddef>
#include <emmintrin.h> // REQUIRED for _mm_pause()

// ==================================================================================
// ARCHITECTURE: Lock-Free SPSC Ring Buffer
// ==================================================================================
// 1. Single Producer (Feed Thread) -> Writes to Tail
// 2. Single Consumer (Strategy Thread) -> Reads from Head
// 3. No Mutexes. Uses atomic loads/stores with Acquire/Release semantics.
// 4. Fixed Size (Power of 2) for fast bitwise wrapping.
// ==================================================================================

template <typename T, size_t Size = 1024>
class LockFreeQueue {
    static_assert((Size & (Size - 1)) == 0, "Size must be a power of 2");

public:
    // -----------------------------------------------------------------------
    // CORE NON-BLOCKING API (Try once, return immediately)
    // -----------------------------------------------------------------------

    // Returns false if full
    bool push(const T& item) {
        const auto current_tail = tail_.load(std::memory_order_relaxed);
        const auto next_tail = (current_tail + 1) & (Size - 1);

        // Check if full: Next tail would hit Head
        if (next_tail == head_.load(std::memory_order_acquire)) {
            return false; // Queue Full
        }

        buffer_[current_tail] = item;
        
        // Commit the write
        tail_.store(next_tail, std::memory_order_release);
        return true;
    }

    // Returns false if empty
    bool pop(T& item) {
        const auto current_head = head_.load(std::memory_order_relaxed);

        // Check if empty: Head caught up to Tail
        if (current_head == tail_.load(std::memory_order_acquire)) {
            return false; // Queue Empty
        }

        item = buffer_[current_head];

        // Move Head
        const auto next_head = (current_head + 1) & (Size - 1);
        head_.store(next_head, std::memory_order_release);
        return true;
    }

    // -----------------------------------------------------------------------
    // NEW: SAFE BLOCKING API (Prevents Deadlock)
    // -----------------------------------------------------------------------
    
    // Spins until space is available OR 'running' flag is set to false.
    // Returns: true if pushed, false if shutdown signal received.
    bool push_blocking(const T& item, const std::atomic<bool>& running) {
        while (running) {
            if (push(item)) return true;
            _mm_pause(); // Vital: Tells CPU to relax during spin (saves power/latency)
        }
        return false; // Shutdown detected
    }

    // Spins until data is available OR 'running' flag is set to false.
    // Returns: true if popped, false if shutdown signal received.
    bool pop_blocking(T& item, const std::atomic<bool>& running) {
        while (running) {
            if (pop(item)) return true;
            _mm_pause();
        }
        return false; // Shutdown detected
    }

private:
    // DATA ALIGNMENT to prevent False Sharing
    alignas(64) std::atomic<size_t> head_{0};
    alignas(64) std::atomic<size_t> tail_{0};
    
    std::vector<T> buffer_{Size};
};