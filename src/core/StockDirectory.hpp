#pragma once
#include <array>
#include <cstring>
#include <vector>
#include <iostream>
#include "../parser/Itch.hpp"

class StockDirectory {
public:
    // 1. SINGLETON ACCESSOR (Meyers' Singleton)
    // Thread-safe in C++11+. Created on first use.
    static StockDirectory& instance() {
        static StockDirectory instance;
        return instance;
    }

    // Delete copy/move to prevent duplication
    StockDirectory(const StockDirectory&) = delete;
    void operator=(const StockDirectory&) = delete;

    // 2. DATA PROCESSING
    void on_directory_message(const DirectoryMsg& msg) {
        if (msg.locate >= 65536) return;

        // Copy 8 bytes from message
        std::memcpy(map_[msg.locate].name, msg.symbol, 8);
        
        // Null terminate and trim spaces
        map_[msg.locate].name[8] = '\0';
        for (int i = 7; i >= 0; --i) {
            if (map_[msg.locate].name[i] == ' ') map_[msg.locate].name[i] = '\0';
            else break;
        }

        active_ids_[msg.locate] = true;
    }

    const char* get_symbol(uint16_t locate) const {
        if (locate >= 65536 || !active_ids_[locate]) return "UNKNOWN";
        return map_[locate].name;
    }

private:
    // PRIVATE CONSTRUCTOR
    StockDirectory() : active_ids_(65536, false) {
        std::memset(&map_, 0, sizeof(map_));
    }

    struct SymbolEntry { char name[9]; };
    std::array<SymbolEntry, 65536> map_;
    std::vector<bool> active_ids_;
};