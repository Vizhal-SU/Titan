#pragma once
#include <atomic>
#include <vector>
#include <optional>
#include <cstddef>

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
    // Push (Called by Producer/Feed Thread)
    // Returns false if full
    bool push(const T& item) {
        const auto current_tail = tail_.load(std::memory_order_relaxed);
        const auto next_tail = (current_tail + 1) & (Size - 1);

        // Check if full: Next tail would hit Head
        // We load head with ACQUIRE to ensure we see the latest consumer updates
        if (next_tail == head_.load(std::memory_order_acquire)) {
            return false; // Queue Full
        }

        buffer_[current_tail] = item;
        
        // Commit the write: RELEASE ensures the item is visible before the tail moves
        tail_.store(next_tail, std::memory_order_release);
        return true;
    }

    // Pop (Called by Consumer/Strategy Thread)
    // Returns false if empty
    bool pop(T& item) {
        const auto current_head = head_.load(std::memory_order_relaxed);

        // Check if empty: Head caught up to Tail
        // We load tail with ACQUIRE to ensure we see the latest producer writes
        if (current_head == tail_.load(std::memory_order_acquire)) {
            return false; // Queue Empty
        }

        item = buffer_[current_head];

        // Move Head: RELEASE to signal we are done with this slot
        const auto next_head = (current_head + 1) & (Size - 1);
        head_.store(next_head, std::memory_order_release);
        return true;
    }

private:
    // DATA ALIGNMENT:
    // We force 'head' and 'tail' onto different 64-byte cache lines.
    // Why? If they share a line, Core 1 writing Tail will invalidate Core 2's cache
    // of Head, causing massive "False Sharing" latency spikes.

    alignas(64) std::atomic<size_t> head_{0};
    alignas(64) std::atomic<size_t> tail_{0};
    
    // The actual storage
    std::vector<T> buffer_{Size};
};