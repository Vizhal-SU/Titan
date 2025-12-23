#pragma once
#include <iostream>
#include <fstream>
#include <thread>
#include <atomic>
#include <vector>
#include <chrono> 
#include <cstring> 

#include "LockFreeQueue.hpp"
#include "TradeLog.hpp"
#include "CpuUtils.hpp"
#include "KdbLogger.hpp"

// UPDATED: Now accepts running flag
void run_logger(LockFreeQueue<TradeLog, 4096>& log_queue, std::atomic<bool>& running) {
    pin_thread_to_core(4); 
    std::cout << "[LOGGER] Thread Started on Core 4." << std::endl;

    std::ofstream itch_file("logs/itch.bin", std::ios::binary | std::ios::out | std::ios::trunc);
    std::ofstream ouch_file("logs/ouch.bin", std::ios::binary | std::ios::out | std::ios::trunc);

    if (!itch_file.is_open() || !ouch_file.is_open()) {
        std::cerr << "!!! [CRITICAL] LOG FILE FAILURE. Check directory permissions. !!!" << std::endl;
    }

    KdbLogger kdb;
    kdb.connect(); 

    TradeLog log;
    
    // UPDATED: Loop checks running flag
    while (running) {
        bool worked = false;
        
        // Drain queue as much as possible before yielding
        while (log_queue.pop(log)) {
            worked = true;

            if (log.action != 'O') {
                kdb.log_itch(log.timestamp, log.symbol, log.price / 10000.0, log.quantity, log.action, log.side);
            } else {
                kdb.log_ouch(log.timestamp, log.symbol, log.price / 10000.0, log.quantity, log.side, log.order_id);
            }
        }
        
        if (!worked) {
            std::this_thread::sleep_for(std::chrono::microseconds(10)); 
        }
    }
    std::cout << "[LOGGER] Thread exiting..." << std::endl;
}