#pragma once
#include <iostream>
#include <fstream>
#include <atomic>
#include <thread>
#include <chrono>
#include <filesystem>
#include "LockFreeQueue.hpp"
#include "TradeLog.hpp"
#include "CpuUtils.hpp"

// Tickerplant: Drains queue -> Writes to Binary Journal
void run_logger(LockFreeQueue<TradeLog, 4096>& log_queue, std::atomic<bool>& running) {
    pin_thread_to_core(4); 
    std::cout << "[TICKERPLANT] Journaler Started on Core 4." << std::endl;

    // 1. Ensure 'logs' directory exists relative to current run location
    if (!std::filesystem::exists("logs")) {
        std::filesystem::create_directory("logs");
        std::cout << "[TICKERPLANT] Created 'logs' directory." << std::endl;
    }

    // 2. Open files with simple relative paths
    // Since you run from Titan/, this puts them in Titan/logs/
    std::ofstream itch_file("logs/itch.bin", std::ios::binary | std::ios::out | std::ios::trunc);
    std::ofstream ouch_file("logs/ouch.bin", std::ios::binary | std::ios::out | std::ios::trunc);

    if (!itch_file.is_open() || !ouch_file.is_open()) {
        std::cerr << "!!! [CRITICAL] LOG FILE FAILURE. Check permissions. !!!" << std::endl;
        return;
    }

    TradeLog log;
    
    while (running) {
        bool worked = false;
        
        while (log_queue.pop(log)) {
            worked = true;
            if (log.action != 'O') {
                itch_file.write(reinterpret_cast<const char*>(&log), sizeof(TradeLog));
            } else {
                ouch_file.write(reinterpret_cast<const char*>(&log), sizeof(TradeLog));
            }
        }
        
        if (worked) {
            // FORCE FLUSH: Ensures data is physically written so KdbPublisher can read it immediately
            itch_file.flush(); 
            ouch_file.flush();
        } else {
            std::this_thread::sleep_for(std::chrono::microseconds(1)); 
        }
    }
    std::cout << "[TICKERPLANT] Exiting..." << std::endl;
}