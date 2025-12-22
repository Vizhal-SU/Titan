#pragma once

#include <vector>
#include <algorithm>
#include <optional>
#include <atomic> 
#include "../parser/Itch.hpp"
#include "../core/SharedState.hpp"

struct alignas(32) Order { 
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
    std::vector<PriceLevel> bids_;
    std::vector<PriceLevel> asks_;
    std::vector<Order> order_store_; 

    // SPINLOCK: Non-copyable, Non-movable
    mutable std::atomic_flag spinlock = ATOMIC_FLAG_INIT;

    SharedBook* shared_book_ptr = nullptr;

public:
    // Default Constructor (needed for vector resizing)
    explicit OrderBook(SharedBook* shared_ptr = nullptr) 
        : shared_book_ptr(shared_ptr) {
            bids_.reserve(50);
            asks_.reserve(50);
            order_store_.reserve(10000);
    }

    // NEW: Setter to attach Shared Memory after construction
    void set_shared_memory(SharedBook* ptr) {
        lock(); // Lock to ensure we don't publish while writing
        shared_book_ptr = ptr;
        
        // CRITICAL FIX: Force an immediate update so the viewer sees the 
        // current state of this book instantly, without waiting for a new order.
        if (shared_book_ptr) {
            // publish_snapshot_internal();
        }
        unlock();
    }

    // --- LOCKING ---
    void lock() const {
        while (spinlock.test_and_set(std::memory_order_acquire)) {
            #if defined(__cpp_lib_atomic_wait)
                spinlock.wait(true, std::memory_order_relaxed); // C++20 Standard
            #endif
        }
    }

    void unlock() const {
        spinlock.clear(std::memory_order_release);
        #if defined(__cpp_lib_atomic_wait)
            spinlock.notify_one(); // C++20 Standard
        #endif
    }

    // --- LOGIC ---
    std::optional<Order> add_order(const AddOrderMsg& msg) {
        lock(); 
        
        Order new_order{msg.order_ref, msg.price, msg.shares, msg.side};
        auto it = std::lower_bound(order_store_.begin(), order_store_.end(), new_order, 
            [](const Order& a, const Order& b) { return a.id < b.id; });

        if (it != order_store_.end() && it->id == msg.order_ref) [[unlikely]] {
            unlock(); return std::nullopt; 
        }
        order_store_.insert(it, new_order);

        auto& ladder = (msg.side == 'B') ? bids_ : asks_;
        
        if (!ladder.empty() && ladder[0].price == msg.price) [[likely]] {
            ladder[0].total_qty += msg.shares;
        } else {
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
                if (msg.side == 'B') {
                    std::sort(ladder.begin(), ladder.end(), [](const PriceLevel& a, const PriceLevel& b) { return a.price > b.price; });
                } else {
                    std::sort(ladder.begin(), ladder.end(), [](const PriceLevel& a, const PriceLevel& b) { return a.price < b.price; });
                }
            }
        }

        // publish_snapshot_internal(); 
        unlock();
        return new_order;
    }

    void execute_order(const OrderExecutedMsg& msg) {
        DeleteOrderMsg del_proxy;
        del_proxy.order_ref = msg.order_ref;
        cancel_order(del_proxy); 
    }

    std::optional<Order> cancel_order(const DeleteOrderMsg& msg) {
        lock(); 

        Order search_key{msg.order_ref, 0, 0, 0}; 
        auto it = std::lower_bound(order_store_.begin(), order_store_.end(), search_key, 
            [](const Order& a, const Order& b) { return a.id < b.id; });

        if (it == order_store_.end() || it->id != msg.order_ref) [[unlikely]] {
            unlock(); return std::nullopt;
        }

        Order deleted_info = *it;
        uint32_t price = it->price;
        uint32_t qty   = it->quantity;
        char     side  = it->side;

        order_store_.erase(it);

        auto& ladder = (side == 'B') ? bids_ : asks_;
        for (auto lvl_it = ladder.begin(); lvl_it != ladder.end(); ++lvl_it) {
            if (lvl_it->price == price) {
                if (lvl_it->total_qty >= qty) lvl_it->total_qty -= qty;
                else lvl_it->total_qty = 0; 

                if (lvl_it->total_qty == 0) ladder.erase(lvl_it);
                break; 
            }
        }

        // publish_snapshot_internal();
        unlock(); 
        return deleted_info;
    }

    // --- ACCESSORS FOR STRATEGY (RESTORED) ---
    // Note: These return COPIES of the structs. This is safe.
    // Returning references would be dangerous because we release the lock immediately.
    
    [[nodiscard]] bool bids_empty() const { 
        lock();
        bool empty = bids_.empty(); 
        unlock();
        return empty;
    }
    
    [[nodiscard]] bool asks_empty() const { 
        lock();
        bool empty = asks_.empty();
        unlock();
        return empty;
    }

    PriceLevel get_best_bid() const { 
        lock();
        PriceLevel ret = bids_.empty() ? PriceLevel{0,0} : bids_[0];
        unlock();
        return ret;
    }

    PriceLevel get_best_ask() const { 
        lock();
        PriceLevel ret = asks_.empty() ? PriceLevel{0,0} : asks_[0];
        unlock();
        return ret;
    }

private:
    // void publish_snapshot_internal() {
    //     if (!shared_book_ptr) return;

    //     for (int i = 0; i < 5; ++i) {
    //         if (i < bids_.size()) {
    //             shared_book_ptr->bid_prices[i] = bids_[i].price;
    //             shared_book_ptr->bid_qtys[i]   = bids_[i].total_qty;
    //         } else {
    //             shared_book_ptr->bid_prices[i] = 0; shared_book_ptr->bid_qtys[i] = 0;
    //         }
            
    //         if (i < asks_.size()) {
    //             shared_book_ptr->ask_prices[i] = asks_[i].price;
    //             shared_book_ptr->ask_qtys[i]   = asks_[i].total_qty;
    //         } else {
    //             shared_book_ptr->ask_prices[i] = 0; shared_book_ptr->ask_qtys[i] = 0;
    //         }
    //     }
    //     shared_book_ptr->sequence_id++;
    // }
};