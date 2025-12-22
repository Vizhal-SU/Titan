#pragma once
#include <cstdint>
#include <bit>
#include <algorithm> // For std::copy

// ==================================================================================
// CONCEPT: Zero-Copy Parsing & Memory Layout
// ==================================================================================
// WHY THIS MATTERS:
// Standard parsing (reading byte-by-byte) is slow because it involves many CPU 
// instructions and cache accesses. "Zero-Copy" means we tell the compiler: 
// "Don't read the bytes; just pretend this memory address holds this specific struct."
//
// THE TRAP (PADDING):
// Compilers naturally add "padding bytes" between fields to align them to 8-byte 
// boundaries for CPU efficiency. 
// Example: A 'char' (1 byte) followed by 'uint64_t' (8 bytes) usually gets 7 bytes 
// of invisible padding. 
// 
// THE FIX (__attribute__((packed))):
// We force the compiler to remove ALL padding. This ensures our struct in C++ memory
// matches the *exact* byte sequence arriving from the NASDAQ network cable.
// ==================================================================================

struct __attribute__((packed)) AddOrderMsg {
    char     msg_type;      // [Offset 0]  'A'
    uint16_t locate;        // [Offset 1]  Stock Locate (2 bytes)
    uint16_t tracking;      // [Offset 3]  Tracking Number
    uint64_t timestamp;     // [Offset 5]  Nanoseconds (Not aligned to 8!)
    uint64_t order_ref;     // [Offset 13] Unique Order ID (Not aligned!)
    char     side;          // [Offset 21] 'B' or 'S'
    uint32_t shares;        // [Offset 22] Quantity
    char     symbol[8];     // [Offset 26] ASCII Symbol
    uint32_t price;         // [Offset 34] Price (4 decimals)
};

struct __attribute__((packed)) DeleteOrderMsg {
    char     msg_type;      // 'D'
    uint16_t locate;
    uint16_t tracking;
    uint64_t timestamp;
    uint64_t order_ref;     // The ID to remove
};

struct __attribute__((packed)) OrderExecutedMsg {
    char     msg_type;      // 'E'
    uint16_t locate;
    uint16_t tracking;
    uint64_t timestamp;
    uint64_t order_ref;     // The ID that traded
    uint32_t executed_shares; // How many shares were eaten?
    uint64_t match_number;  // Unique Trade ID
};

// ==================================================================================
// CONCEPT: Endianness (Network vs. Host Byte Order)
// ==================================================================================
// PROBLEM:
// - Network (Big-Endian): Most significant byte comes FIRST (e.g., 1000 = 0x03 0xE8)
// - x86 CPU (Little-Endian): Least significant byte comes FIRST (e.g., 1000 = 0xE8 0x03)
// 
// If we interpret raw network bytes directly as an integer on x86, the value will be 
// backwards and massive. We MUST swap the bytes.
// ==================================================================================

inline void parse_add_order(const char* buffer, AddOrderMsg& out) {
    // 1. THE ZERO-COPY CAST
    // We treat the raw 'char*' pointer as an 'AddOrderMsg*' pointer.
    // Cost: 0 CPU Cycles (It's just a type re-interpretation).
    const auto* raw = reinterpret_cast<const AddOrderMsg*>(buffer);
    
    // 2. COPY & SWAP
    // We copy fields one-by-one, swapping endianness where necessary.
    out.msg_type = raw->msg_type; // 1 byte, no swap needed
    out.side     = raw->side;     // 1 byte, no swap needed
    
    // std::byteswap (C++23) compiles to a single CPU instruction (BSWAP on x86).
    out.locate    = std::byteswap(raw->locate);
    out.tracking  = std::byteswap(raw->tracking);
    out.timestamp = std::byteswap(raw->timestamp);
    out.order_ref = std::byteswap(raw->order_ref);
    out.shares    = std::byteswap(raw->shares);
    out.price     = std::byteswap(raw->price);
    
    // Copy the symbol array directly (memcpy equivalent)
    std::copy(std::begin(raw->symbol), std::end(raw->symbol), std::begin(out.symbol));
}

inline void parse_delete_order(const char* buffer, DeleteOrderMsg& out) {
    const auto* raw = reinterpret_cast<const DeleteOrderMsg*>(buffer);
    out.msg_type  = raw->msg_type;
    out.order_ref = std::byteswap(raw->order_ref);
    // We don't care about timestamp/tracking for this sim
}

inline void parse_order_executed(const char* buffer, OrderExecutedMsg& out) {
    const auto* raw = reinterpret_cast<const OrderExecutedMsg*>(buffer);
    out.msg_type        = raw->msg_type;
    out.order_ref       = std::byteswap(raw->order_ref);
    out.executed_shares = std::byteswap(raw->executed_shares);
}

// [Append this to Itch.hpp]

// ==================================================================================
// MESSAGE: Stock Directory ('R')
// ==================================================================================
// Sent at the start of the day to map "Locate IDs" (Integers) to "Ticker Symbols" (Strings).
struct __attribute__((packed)) DirectoryMsg {
    char     msg_type;      // 'R'
    uint16_t locate;        // Map this ID...
    uint16_t tracking;
    uint64_t timestamp;     // 6 bytes in spec, but we usually map 8 and mask, or ignore
    char     symbol[8];     // ...to this String "AAPL    "
    char     market_category;
    char     financial_status;
    uint32_t round_lot_size;
    char     round_lot_only;
    char     issue_classification;
    char     issue_subtype[2];
    char     authenticity;
    char     short_sale_threshold;
    char     ipo_flag;
    char     luld_tier;
    char     etp_flag;
    uint32_t etp_leverage;
    char     inverse_ind;
};

// Parser for Directory Message
inline void parse_directory(const char* buffer, DirectoryMsg& out) {
    const auto* raw = reinterpret_cast<const DirectoryMsg*>(buffer);
    
    out.msg_type = raw->msg_type;
    out.locate   = std::byteswap(raw->locate); // Critical: Swap ID
    
    // We only really care about the symbol for the directory
    std::copy(std::begin(raw->symbol), std::end(raw->symbol), std::begin(out.symbol));
    
    // Optional: Parse other fields if you need them for strategy logic
    out.round_lot_size = std::byteswap(raw->round_lot_size);
}