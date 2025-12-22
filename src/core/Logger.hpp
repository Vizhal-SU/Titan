#pragma once
#include <iostream>
#include <fstream>
#include <thread>
#include <atomic>
#include <vector>
#include <chrono>   // Added for sanity check timestamp
#include <cstring>  // Added for memset

#include "LockFreeQueue.hpp"
#include "TradeLog.hpp"
#include "CpuUtils.hpp"
#include "KdbLogger.hpp"

void run_logger(LockFreeQueue<TradeLog, 4096>& log_queue) {
    // 1. PIN TO CORE 4
    pin_thread_to_core(4); 
    std::cout << "[LOGGER] Thread Started on Core 4." << std::endl;

    // 2. OPEN FILES & CHECK ERRORS
    // NOTE: 'std::ios::trunc' clears the file so we can see new data clearly
    std::ofstream itch_file("logs/itch.bin", std::ios::binary | std::ios::out | std::ios::trunc);
    std::ofstream ouch_file("logs/ouch.bin", std::ios::binary | std::ios::out | std::ios::trunc);

    // CRITICAL: Check if files actually opened. 
    // If the folder "/logs" does not exist, these will FAIL silently.
    if (!itch_file.is_open()) {
        std::cerr << "!!! [CRITICAL] FAILED TO OPEN ../logs/itch.bin !!!" << std::endl;
        std::cerr << ">>> DOES THE DIRECTORY '../logs' EXIST?" << std::endl;
        return; 
    }
    if (!ouch_file.is_open()) {
        std::cerr << "!!! [CRITICAL] FAILED TO OPEN ../logs/ouch.bin !!!" << std::endl;
        return;
    }

    std::cout << "[LOGGER] Files opened successfully." << std::endl;

    // 3. SANITY CHECK: DIRECT WRITE (Bypass Queue)
    // std::cout << "[LOGGER] WRITING TEST ENTRY TO DISK..." << std::endl;
    
    // TradeLog dummy;
    // std::memset(&dummy, 0, sizeof(TradeLog)); // Zero out
    // dummy.action = 'A'; // 'A'dd
    // dummy.price = 12345;
    // dummy.quantity = 999;
    // dummy.set_symbol("TEST");

    // Force write immediately
    // itch_file.write(reinterpret_cast<const char*>(&dummy), sizeof(TradeLog));
    // itch_file.flush(); 

    // if (itch_file.good()) {
    //     std::cout << "[LOGGER] Test entry written! Check file size now." << std::endl;
    // } else {
    //     std::cerr << "[LOGGER] Write operation failed!" << std::endl;
    // }

    // 1. Instantiate and Connect to Kdb+ (runs once on thread start)
    KdbLogger kdb;
    kdb.connect(); 

    TradeLog log;
    while (true) {
        bool worked = false;
        while (log_queue.pop(log)) {
            worked = true;

            // --- PATH A: ORDER ENTRY (OUCH) ---
            if (log.action == 'O') {
                // 1. Write to Disk (Existing)
                ouch_file.write(reinterpret_cast<const char*>(&log), sizeof(TradeLog));
                
                // 2. Push to Kdb+ (New)
                // Note: We convert price int (454600) to double (45.46) for easier analytics
                kdb.log_ouch(
                    log.timestamp, 
                    log.symbol, 
                    log.price / 10000.0, 
                    log.quantity, 
                    log.side, 
                    log.order_id
                );
            } 
            
            // --- PATH B: MARKET DATA (ITCH) ---
            else {
                // 1. Write to Disk (Existing)
                itch_file.write(reinterpret_cast<const char*>(&log), sizeof(TradeLog));
                
                // 2. Push to Kdb+ (New)
                // Here 'log.action' acts as the Message Type ('A', 'E', 'D', etc.)
                kdb.log_itch(
                    log.timestamp, 
                    log.symbol, 
                    log.price / 10000.0, 
                    log.quantity, 
                    log.action,  // MsgType
                    log.side
                );
            }
        }
        
        // CPU Yield if queue is empty (prevents 100% CPU usage on logger thread)
        if (!worked) {
            std::this_thread::sleep_for(std::chrono::microseconds(1)); 
            // or std::this_thread::yield();
        }
    }
}