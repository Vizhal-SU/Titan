#pragma once
#include "../include/c.h" 
#include <cstring>
#include <iostream>
#include <chrono>

constexpr long long KDB_EPOCH_OFFSET = 946684800000000000LL;

class KdbLogger {
    int handle = -1;
    long last_retry_time = 0;

public:
    KdbLogger() { handle = -1; }

    ~KdbLogger() {
        if (handle > 0) kclose(handle);
    }

    void connect() {
        std::cout << "[KDB] Connecting to 127.0.0.1:5001..." << std::endl;
        // NOTE: khpu is blocking. If this hangs, ensure KDB is running.
        handle = khpu((char*)"127.0.0.1", 5001, (char*)"titan:hft");
        
        if (handle > 0) {
            std::cout << "[KDB] SUCCESS: Connected to Analytics Engine." << std::endl;
        } else {
            std::cerr << "[KDB] ERROR: Connection failed. Is the q process running?" << std::endl;
        }
    }

    bool ensure_connected() {
        if (handle > 0) return true;
        long now = std::chrono::steady_clock::now().time_since_epoch().count();
        if (now - last_retry_time < 2000000000L) return false;
        last_retry_time = now;
        connect();
        return (handle > 0);
    }

    // Helper function to trim trailing spaces in-place (optional, or inline it)
    void trim_trailing_spaces(char* str, int length) {
        for (int i = length - 1; i >= 0; --i) {
            if (str[i] == ' ') {
                str[i] = '\0';
            } else {
                break;
            }
        }
    }

    void log_ouch(long long ns_time, const char* raw_sym, double price, int size, char side, long order_id) {
        if (!ensure_connected()) return;

        // 1. COPY RAW BYTES
        char safe_sym[9]; 
        std::memcpy(safe_sym, raw_sym, 8);
        safe_sym[8] = '\0'; // Safety null-terminator

        // 2. CRITICAL FIX: TRIM TRAILING SPACES
        // Iterate backwards. If space, replace with null-terminator. Stop at first char.
        for (int i = 7; i >= 0; --i) {
            if (safe_sym[i] == ' ') {
                safe_sym[i] = '\0';
            } else {
                break; 
            }
        }

        long long kdb_time = ns_time - KDB_EPOCH_OFFSET;

        // 3. SEND TO KDB (Now safe_sym is "AAPL" not "AAPL    ")
        K result = k(-handle, (char*)".u.upd", ks((char*)"orders"), knk(6,
            ktj(-KP, kdb_time),
            ks(safe_sym),  // <--- This now creates `AAPL`
            kf(price),
            ki(size),
            kc(side),
            kj(order_id)
        ), (K)0);
        
        if (result == 0) { 
            std::cerr << "[KDB] Write Error!" << std::endl;
            kclose(handle); 
            handle = -1; 
        }
    }

    void log_itch(long long ns_time, const char* raw_sym, double price, int size, char msg_type, char side) {
        if (!ensure_connected()) return;

        // 1. COPY RAW BYTES
        char safe_sym[9];
        std::memcpy(safe_sym, raw_sym, 8);
        safe_sym[8] = '\0';

        // 2. CRITICAL FIX: TRIM TRAILING SPACES
        for (int i = 7; i >= 0; --i) {
            if (safe_sym[i] == ' ') {
                safe_sym[i] = '\0';
            } else {
                break; 
            }
        }

        long long kdb_time = ns_time - KDB_EPOCH_OFFSET;

        // 3. SEND TO KDB
        K result = k(-handle, (char*)".u.upd", ks((char*)"market"), knk(6,
            ktj(-KP, kdb_time),
            ks(safe_sym),  // <--- This now creates `AAPL`
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

