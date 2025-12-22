#pragma once
#include "../include/c.h" 
#include <cstring>
#include <iostream>
#include <chrono>

// 1970 to 2000 offset in nanoseconds
constexpr long long KDB_EPOCH_OFFSET = 946684800000000000LL;

class KdbLogger {
    int handle = -1;
    long last_retry_time = 0;

public:
    KdbLogger() {
        // Don't connect in constructor. Wait for first log call or explicit connect.
        handle = -1;
    }

    ~KdbLogger() {
        if (handle > 0) kclose(handle);
    }

    void connect() {
        // Attempt connection to localhost:5001
        // Note: Casts to (char*) are required for legacy C API
        handle = khpu((char*)"127.0.0.1", 5001, (char*)"titan:hft");
        
        if (handle > 0) {
            std::cout << "[KDB] Connected to Analytics Engine on :5001" << std::endl;
        }
    }

    // Helper to manage connection state (Auto-Reconnect)
    bool ensure_connected() {
        if (handle > 0) return true;

        // Simple Rate Limit: Retry only once every 2 seconds
        long now = std::chrono::steady_clock::now().time_since_epoch().count();
        if (now - last_retry_time < 2000000000L) return false;
        
        last_retry_time = now;
        connect();
        return (handle > 0);
    }

    void log_ouch(long long ns_time, const char* raw_sym, double price, int size, char side, long order_id) {
        if (!ensure_connected()) return;

        // --- SEGFAULT FIX: Sanitize Symbol ---
        char safe_sym[9]; 
        std::memcpy(safe_sym, raw_sym, 8);
        safe_sym[8] = '\0'; // Force Null-Termination
        
        long long kdb_time = ns_time - KDB_EPOCH_OFFSET;

        // Async send: .u.upd[`orders; (time; sym; price; size; side; id)]
        K result = k(-handle, (char*)".u.upd", (char*)"orders", knk(6,
            ktj(-KN, kdb_time),
            ks(safe_sym),    // Safe, null-terminated string
            kf(price),
            ki(size),
            kc(side),
            kj(order_id)
        ), (K)0);
        
        // If result is null/error (network issue), reset handle to force reconnect next time
        if (result == 0) { 
             std::cerr << "[KDB] Connection Lost." << std::endl;
             kclose(handle); 
             handle = -1; 
        }
    }

    void log_itch(long long ns_time, const char* raw_sym, double price, int size, char msg_type, char side) {
        if (!ensure_connected()) return;

        // --- SEGFAULT FIX ---
        char safe_sym[9];
        std::memcpy(safe_sym, raw_sym, 8);
        safe_sym[8] = '\0';

        long long kdb_time = ns_time - KDB_EPOCH_OFFSET;

        K result = k(-handle, (char*)".u.upd", (char*)"market", knk(6,
            ktj(-KN, kdb_time),
            ks(safe_sym),
            kf(price),
            ki(size),
            kc(msg_type),
            kc(side)
        ), (K)0);

         if (result == 0) { 
             kclose(handle); 
             handle = -1; 
        }
    }
};