#pragma once

#include <vector>
#include <algorithm>
#include <iostream>
#include <format>
#include <optional>

// #include <flat_map> // C++23: Use this if available on your compiler
// For now, we simulate flat_map behavior using sorted vectors if headers are missing
// or use boost::container::flat_map in production.

#include "../parser/Itch.hpp"
#include "../core/SharedState.hpp"

// ==================================================================================
// ARCHITECTURE NOTE: Data-Oriented Design (DOD)
// We split the "Order" struct. We don't need 'side' or 'price' when we just want 
// to check if an ID exists.
// However, keeping them together fits in a single cache line (32 bytes), so we keep
// it simple for now. [cite: 825, 828]
// ==================================================================================

struct alignas(32) Order { // Force 32-byte alignment to fit 2 per 64-byte cache line
    uint64_t id;
    uint32_t price;
    uint32_t quantity;
    char     side; 
};

struct PriceLevel {
    uint32_t price;
    uint32_t total_qty;
};

class OrderBook {
private:
    // 1. THE PRICE LADDER (Contiguous Vectors)
    // Why Vector? Linear scan of top-of-book is the fastest possible operation 
    // due to hardware prefetching. [cite: 558]
    std::vector<PriceLevel> bids_;
    std::vector<PriceLevel> asks_;
    
    // 2. THE ORDER LOOKUP (C++23 Flat Map Simulation)
    // Instead of std::unordered_map (Node-based, Cache Misses),
    // we use a sorted vector. This IS a flat_map.
    // Latency: O(log N) but strictly Cache-Local.
    std::vector<Order> order_store_; 

public:
    // C++23: "deducing this" pattern could be used here for efficiency, 
    // but we stick to standard methods for clarity.

    std::optional<Order> add_order(const AddOrderMsg& msg) {
        // ---------------------------------------------------------
        // PART 1: Update Order Store (The Flat Map Insert)
        // ---------------------------------------------------------
        Order new_order{msg.order_ref, msg.price, msg.shares, msg.side};
        
        // Binary Search for insertion point (O(log N))
        // On modern CPUs, this beats Hash Map for N < 1000 due to cache locality.
        auto it = std::lower_bound(order_store_.begin(), order_store_.end(), new_order, 
            [](const Order& a, const Order& b) { return a.id < b.id; });

        if (it != order_store_.end() && it->id == msg.order_ref) [[unlikely]] {
            // Duplicate ID? HFT protocol violation. Log and ignore.
            return std::nullopt; 
        }
        
        // Insert into vector (O(N) - Worst case, but 'memmove' is optimized by CPU)
        order_store_.insert(it, new_order);

        // ---------------------------------------------------------
        // PART 2: Update Price Ladder (The Hot Path)
        // ---------------------------------------------------------
        auto& ladder = (msg.side == 'B') ? bids_ : asks_;
        
        // Optimization: Check Top of Book first (Most likely case)
        if (!ladder.empty() && ladder[0].price == msg.price) [[likely]] {
            ladder[0].total_qty += msg.shares;
            return std::nullopt;
        }

        // Linear Scan is faster than Binary Search for small arrays (N < 20 levels)
        bool found = false;
        for (auto& lvl : ladder) {
            if (lvl.price == msg.price) {
                lvl.total_qty += msg.shares;
                found = true;
                break;
            }
        }

        if (!found) {
            ladder.push_back({msg.price, msg.shares});
            // Re-sort needed. In production, we'd use insertion sort for small updates.
            if (msg.side == 'B') {
                std::sort(ladder.begin(), ladder.end(), 
                    [](const PriceLevel& a, const PriceLevel& b) { return a.price > b.price; });
            } else {
                std::sort(ladder.begin(), ladder.end(), 
                    [](const PriceLevel& a, const PriceLevel& b) { return a.price < b.price; });
            }
        }
        return new_order;
    }

    void execute_order(uint64_t order_id, uint32_t qty) {
        // FLAT MAP LOOKUP (Binary Search)
        auto it = std::lower_bound(order_store_.begin(), order_store_.end(), order_id, 
            [](const Order& o, uint64_t id) { return o.id < id; });

        if (it != order_store_.end() && it->id == order_id) [[likely]] {
            // Found it instantly in Cache L1/L2
            it->quantity -= qty;
            if (it->quantity == 0) {
                order_store_.erase(it); // O(N) shift, but contiguous memory is fast
            }
            // Update ladder logic omitted for brevity (similar to add)
        }
    }

    void print_top_of_book() const {
        if (bids_.empty() && asks_.empty()) return;

        std::string bid_str = bids_.empty() ? "---" : 
            std::format("{} @ {:.2f}", bids_[0].total_qty, bids_[0].price / 10000.0);
            
        std::string ask_str = asks_.empty() ? "---" : 
            std::format("{:.2f} @ {}", asks_[0].price / 10000.0, asks_[0].total_qty);

        std::cout << std::format("[BOOK] BID: [{}]  <-- SPREAD -->  ASK: [{}]", bid_str, ask_str) << std::endl;
    }

    std::optional<Order> cancel_order(const DeleteOrderMsg& msg) {
        // 1. Find the Order in our Store (Binary Search)
        // We need a dummy Order object to search by ID
        Order search_key{msg.order_ref, 0, 0, 0}; 
        
        auto it = std::lower_bound(order_store_.begin(), order_store_.end(), search_key, 
            [](const Order& a, const Order& b) { return a.id < b.id; });

        // If not found (or ID mismatch), ignore
        if (it == order_store_.end() || it->id != msg.order_ref) [[unlikely]] {
            return std::nullopt;
        }

        Order deleted_info = *it;

        // 2. Capture details before deleting
        uint32_t price = it->price;
        uint32_t qty   = it->quantity;
        char     side  = it->side;

        // 3. Remove from Order Store (Flat Map erase)
        // Note: Vector erase is O(N), but for small N (<10k) it's fast due to memmove optimization
        order_store_.erase(it);

        // 4. Update Price Ladder
        auto& ladder = (side == 'B') ? bids_ : asks_;
        
        // Find the price level
        for (auto lvl_it = ladder.begin(); lvl_it != ladder.end(); ++lvl_it) {
            if (lvl_it->price == price) {
                // Decrease Quantity
                if (lvl_it->total_qty >= qty) {
                    lvl_it->total_qty -= qty;
                } else {
                    lvl_it->total_qty = 0; // Safety catch
                }

                // 5. Cleanup Empty Levels (Critical for Strategy Speed)
                if (lvl_it->total_qty == 0) {
                    ladder.erase(lvl_it);
                }
                break; // Done
            }
        }
        return deleted_info;
    }
   
    void print_entire_book() const {
        std::cout << "\n======= MARKET DEPTH =======" << std::endl;
        std::cout << "   QTY   |   PRICE   | TYPE " << std::endl;
        std::cout << "---------+-----------+------" << std::endl;

        // 1. ASKS (Sell Orders)
        // Stored: Low -> High (Best -> Worst)
        // Print:  High -> Low (Worst -> Best)
        // We iterate backwards (rbegin -> rend) to show high prices at top
        for (auto it = asks_.rbegin(); it != asks_.rend(); ++it) {
             std::cout << std::format("{:8} | {:9.2f} | ASK  ", 
                                      it->total_qty, it->price / 10000.0) << std::endl;
        }

        std::cout << "---------+-----------+------  <-- SPREAD" << std::endl;

        // 2. BIDS (Buy Orders)
        // Stored: High -> Low (Best -> Worst)
        // Print:  High -> Low (Best -> Worst)
        // We iterate normally
        for (const auto& level : bids_) {
             std::cout << std::format("{:8} | {:9.2f} | BID  ", 
                                      level.total_qty, level.price / 10000.0) << std::endl;
        }
        std::cout << "============================" << std::endl;
    }

    void publish_snapshot() {
            if (!shared_book_ptr) return;

            // WRITE BIDS (Top 5)
            for (int i = 0; i < 5; ++i) {
                if (i < bids_.size()) {
                    shared_book_ptr->bid_prices[i] = bids_[i].price;
                    shared_book_ptr->bid_qtys[i]   = bids_[i].total_qty;
                } else {
                    shared_book_ptr->bid_prices[i] = 0;
                    shared_book_ptr->bid_qtys[i]   = 0;
                }
            }

            // WRITE ASKS (Top 5)
            for (int i = 0; i < 5; ++i) {
                if (i < asks_.size()) {
                    shared_book_ptr->ask_prices[i] = asks_[i].price;
                    shared_book_ptr->ask_qtys[i]   = asks_[i].total_qty;
                } else {
                    shared_book_ptr->ask_prices[i] = 0;
                    shared_book_ptr->ask_qtys[i]   = 0;
                }
            }
            
            shared_book_ptr->sequence_id++;
        }

    // Fast Read-Only Accessors for the Strategy
    // const& avoids copying the PriceLevel struct
    [[nodiscard]] bool bids_empty() const { return bids_.empty(); }
    [[nodiscard]] bool asks_empty() const { return asks_.empty(); }

    const PriceLevel& get_best_bid() const { return bids_[0]; }
    const PriceLevel& get_best_ask() const { return asks_[0]; }
};