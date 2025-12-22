#pragma once
#include <cstdint>
#include "../parser/Itch.hpp"

// Fixed size entry for a single stock
struct PositionEntry {
    char     symbol[8];      // "NVDA    "
    int32_t  quantity;       // Current Inventory
    double   realized_pnl;   // Cash Banked
    double   avg_entry_px;   // For calculating Unrealized PnL
    uint32_t trade_count;    // Activity level
};

// The new "Lightweight" Snapshot (~3KB total)
struct PortfolioSnapshot {
    uint64_t sequence_id;    // Version number
    double   global_pnl;     // Sum of all PnL
    uint32_t global_trades;  // Sum of all trades
    
    // We support tracking up to 64 distinct stocks dynamically
    uint32_t active_count;   
    PositionEntry items[64]; 
};

using SharedBook = PortfolioSnapshot; // Alias for compatibility

struct Event {
    char type;
    union {
        AddOrderMsg add;
        DeleteOrderMsg del;
        OrderExecutedMsg exec;
    };
};