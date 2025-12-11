#pragma once
#include <array>
#include <string>
#include <vector>
#include <iostream>

// Simple lookup: Locate ID -> Symbol Name
class StockDirectory {
private:
    // 65536 is the max number of Locates in NASDAQ spec
    // We store the string symbol for reporting/OUCH.
    std::array<std::string, 65536> id_to_symbol_;
    
    // We also need to know if a locate is active/valid
    std::vector<bool> active_ids_;

public:
    StockDirectory() : active_ids_(65536, false) {
        // PRE-LOAD: In a real system, we parse "Stock Directory" messages from ITCH.
        // For this sim, we hardcode a few.
        register_stock(1, "AAPL");
        register_stock(2, "MSFT");
        register_stock(3, "GOOG");
        register_stock(4, "TSLA");
    }

    void register_stock(uint16_t locate, const std::string& symbol) {
        if (locate >= 65536) return;
        id_to_symbol_[locate] = symbol;
        active_ids_[locate] = true;
        std::cout << "[DIR] Registered Locate " << locate << " => " << symbol << std::endl;
    }

    const std::string& get_symbol(uint16_t locate) const {
        // Return symbol or "UNKNOWN" if invalid
        static const std::string unknown = "UNKNOWN";
        if (locate >= 65536 || !active_ids_[locate]) return unknown;
        return id_to_symbol_[locate];
    }
};