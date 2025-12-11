#pragma once
#include <iostream>
#include <fstream>
#include <thread>
#include <atomic>
#include <vector>
#include "LockFreeQueue.hpp"
#include "TradeLog.hpp"
#include "CpuUtils.hpp"

// A 4MB buffer for the queue should be plenty
LockFreeQueue<TradeLog, 4096> log_queue;

void run_logger() {
    // 1. PIN TO CORE 4 (Keep it away from Strategy)
    pin_thread_to_core(4); 
    std::cout << "[LOGGER] Thread Started on Core 4. Writing to 'trades.bin'..." << std::endl;

    // 2. Open Binary File
    // std::ios::binary is crucial. No text formatting. Raw bytes.
    std::ofstream file("trades.bin", std::ios::binary | std::ios::out | std::ios::app);

    TradeLog log;
    
    // 3. The Drain Loop
    while (true) {
        // Pop from queue
        while (log_queue.pop(log)) {
            // Write raw bytes to disk buffer
            file.write(reinterpret_cast<const char*>(&log), sizeof(TradeLog));
        }
        
        // Flush periodically (e.g., if queue is empty) to ensure data hits disk
        file.flush();
        
        // Sleep if empty to save CPU (Logger doesn't need to spin 100%)
        std::this_thread::sleep_for(std::chrono::milliseconds(1));
    }
}