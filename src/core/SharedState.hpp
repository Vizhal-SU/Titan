#pragma once
#include <cstdint>

// Fixed size snapshot for the viewer
struct BookSnapshot {
    uint32_t bid_prices[5];
    uint32_t bid_qtys[5];
    uint32_t ask_prices[5];
    uint32_t ask_qtys[5];
    uint64_t sequence_id; // To detect updates
};

// Global pointer for the engine to write to
inline BookSnapshot* shared_book_ptr = nullptr;