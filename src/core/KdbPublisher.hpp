#pragma once
#include <iostream>
#include <fstream>
#include <thread>
#include <atomic>
#include <filesystem>
#include "TradeLog.hpp"
#include "KdbLogger.hpp"

void run_publisher(std::atomic<bool>& running) {
    std::cout << "[PUBLISHER] KDB Publisher Started." << std::endl;
    
    KdbLogger kdb;
    kdb.connect();

    // Open the journals
    std::filesystem::path current_path = std::filesystem::current_path();
    std::filesystem::path log_dir = "logs"; 
    
    std::ifstream itch_file(log_dir / "itch.bin", std::ios::binary);
    std::ifstream ouch_file(log_dir / "ouch.bin", std::ios::binary);
    
    TradeLog log;
    
    while (running) {
        // --- 1. CONNECTION KEEPALIVE ---
        if (!kdb.ensure_connected()) {
             // Optional: std::cout << "Waiting..." << std::endl;
        }

        // --- 2. PROCESS OUCH (PRIORITY) ---
        // We always drain orders completely because they are low volume and critical.
        bool orders_processed = false;
        while (ouch_file.read(reinterpret_cast<char*>(&log), sizeof(TradeLog))) {
            orders_processed = true;
            // Debug print to confirm you are seeing orders
            std::cout << "[PUB] Reading Order: " << log.order_id << std::endl;
            kdb.log_ouch(log.timestamp, log.symbol, log.price / 10000.0, log.quantity, log.side, log.order_id);
        }
        if (ouch_file.eof()) ouch_file.clear();


        // --- 3. PROCESS ITCH (BOUNDED) ---
        // CRITICAL FIX: Limit this loop! 
        // If we don't limit this, a large backlog will starve the Orders.
        int itch_limit = 1000; 
        bool market_active = false;

        while (itch_limit > 0 && itch_file.read(reinterpret_cast<char*>(&log), sizeof(TradeLog))) {
            market_active = true;
            itch_limit--; // Decrement quota
            kdb.log_itch(log.timestamp, log.symbol, log.price / 10000.0, log.quantity, log.action, log.side);
        }
        if (itch_file.eof()) itch_file.clear();


        // --- 4. SMART FLUSH & SLEEP ---
        if (!market_active && !orders_processed) {
            // CASE A: TOTAL IDLE
            // No data flowing at all. Force flush stragglers and sleep to save CPU.
            kdb.flush_market();
            std::this_thread::sleep_for(std::chrono::microseconds(100));
        } 
        else if (!market_active) {
            // CASE B: MARKET STOPPED / ORDERS ONLY
            // We read some orders, or we finished the market file. 
            // Flush any partial market batch so dashboards update.
            kdb.flush_market();
        }
        // CASE C: BUSY (market_active == true)
        // We hit the itch_limit (1000). Do NOT force flush.
        // Let the KdbLogger internal batch logic handle efficient sending.
    }
}