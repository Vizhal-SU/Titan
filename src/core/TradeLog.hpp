#pragma once
#include <cstdint>

// A compact struct to record what happened.
// We log this to disk purely for analytics/audit.
struct __attribute__((packed)) TradeLog {
    uint64_t timestamp;  // When did we decide?
    uint64_t order_id;   // What order?
    uint32_t price;      // What price?
    uint32_t quantity;   // How many?
    char     side;       // 'B' or 'S'
    char     action;     // 'F' (Fill), 'C' (Cancel), 'S' (Signal)
};