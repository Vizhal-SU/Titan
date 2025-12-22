#pragma once
#include <cstdint>
#include <cstring>
#include <string_view>
#include <algorithm>

// ALIGNMENT: 32 bytes
// - Fits 2 items per 64-byte Cache Line. 
// - Good compromise: Reduces False Sharing compared to packed arrays, 
//   but doubles cache density compared to alignas(64).
#pragma pack(push, 1)
struct TradeLog {
    
    // 1. 64-bit blocks (16 bytes)
    uint64_t timestamp;      // Offset 0  (8 bytes)
    char     symbol[8];      // Offset 8  (8 bytes) - Moved here to align
    
    // 2. 32-bit blocks (12 bytes)
    uint32_t price;          // Offset 16 (4 bytes)
    uint32_t quantity;       // Offset 20 (4 bytes)
    uint32_t order_id;       // Offset 24 (4 bytes) - CHANGED to 32-bit
    
    // 3. Byte blocks + Explicit Padding (4 bytes)
    char     action;         // Offset 28 (1 byte)
    char     side;           // Offset 29 (1 byte)
    char     _pad[2];        // Offset 30 (2 bytes) - Explicit garbage for 32-byte total
    
    // TOTAL SIZE: 32 Bytes.

    // -------------------------------------------------------------
    // Helper Methods (Same as before)
    // -------------------------------------------------------------
    
    void set_symbol(std::string_view s) {
        std::memset(symbol, ' ', 8);
        if (!s.empty()) {
            std::memcpy(symbol, s.data(), std::min(s.size(), size_t(8)));
        }
    }

    std::string_view get_symbol() const {
        const char* end = symbol + 8;
        while (end > symbol && *(end - 1) == ' ') end--;
        return std::string_view(symbol, end - symbol);
    }
};
#pragma pack(pop)

// Compile-time check to ensure no surprises
static_assert(sizeof(TradeLog) == 32, "TradeLog must be exactly 32 bytes!");