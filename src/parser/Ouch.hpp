#pragma once
#include <cstdint>
#include <cstring>
#include <bit>

// ==================================================================================
// PROTOCOL: OUCH (Order Entry)
// The standard for sending orders to NASDAQ-style exchanges.
// ==================================================================================

struct __attribute__((packed)) EnterOrderMsg {
    char    type = 'O';            // 1 byte
    char    token[14];             // 14 bytes
    char    side;                  // 1 byte
    uint32_t shares;               // 4 bytes
    char    symbol[8];             // 8 bytes
    uint32_t price;                // 4 bytes

};
// TOTAL SIZE: 32 Bytes (Matches Python exactly)

// Helper to format the packet for the wire (Host -> Network Byte Order)
inline void format_enter_order(EnterOrderMsg& msg, 
                               uint64_t order_id, 
                               char side, 
                               uint32_t shares, 
                               uint32_t price, 
                               const char* symbol) 
{
    msg.type = 'O';
    
    // Create a Token (e.g., "TITAN-1001")
    std::snprintf(msg.token, sizeof(msg.token), "TITN-%lu", order_id);
    
    msg.side = side;
    
    // HTONL (Host to Network Long) - Swap bytes for network
    msg.shares = std::byteswap(shares);
    msg.price  = std::byteswap(price);
    
    // Copy Symbol (Pad with spaces)
    std::memset(msg.symbol, ' ', 8);
    std::memcpy(msg.symbol, symbol, std::strlen(symbol));
}