#pragma once
#include <cstdint>
#include <cstring>
#include <bit>

// ==================================================================================
// PROTOCOL: OUCH (Order Entry)
// The standard for sending orders to NASDAQ-style exchanges.
// ==================================================================================

struct __attribute__((packed)) EnterOrderMsg {
    char     type = 'O';            // 'O' = Enter Order
    char     token[14];             // Client Order ID (ASCII)
    char     side;                  // 'B' or 'S'
    uint32_t shares;                // Quantity
    char     symbol[8];             // Symbol
    uint32_t price;                 // Limit Price
    uint32_t time_in_force = 99999; // 0 = Day, 99999 = IOC (Immediate or Cancel)
    char     firm[4] = {'T', 'I', 'T', 'N'};      // MPID
    char     display = 'Y';
    char     capacity = 'P';        // Principal
    char     intermarket = 'N';
    uint32_t min_qty = 0;
    uint32_t cross_type = 0;
    char     customer_type = 'R';
};

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