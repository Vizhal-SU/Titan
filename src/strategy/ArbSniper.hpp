#pragma once
#include <iostream>
#include <format>
#include "../book/OrderBook.hpp"
#include "../network/ExecutionGateway.hpp" // <--- Include Gateway
#include "../core/Logger.hpp"

// ==================================================================================
// STRATEGY: Crossed Market Arbitrage
// LOGIC: If (Best Bid >= Best Ask), we buy low and sell high instantly.
// ==================================================================================

class ArbSniper {
private:
    // Reference to the Book (The Strategy "reads" the book)
    // const OrderBook& book_; 
    ExecutionGateway& gateway_; // <--- Reference to Gateway

public:
    // Constructor: Link the strategy to a specific book
    explicit ArbSniper(ExecutionGateway& gateway) : gateway_(gateway) {}

    // The "Trigger" Function
    // Called immediately after the Book is updated.
    // [[gnu::always_inline]] forces the compiler to squash this into the main loop.

    [[gnu::always_inline]] 
    void on_book_update(const OrderBook& book, const std::string& symbol) {
        // 1. Check if we have both sides
        if (book.bids_empty() || book.asks_empty()) [[unlikely]] {
            return;
        }

        // 2. Get Top of Book (Fast Vector Access)
        const auto& best_bid = book.get_best_bid();
        const auto& best_ask = book.get_best_ask();

        // 3. The Alpha Signal (Crossed Market)
        if (best_bid.price >= best_ask.price) [[unlikely]] {
            // ARBITRAGE OPPORTUNITY!
            // In reality, we would send an OUCH packet here.
            // For now, we print the signal.
            
            uint32_t profit_per_share = best_bid.price - best_ask.price;
            uint32_t take_price = best_ask.price; // The price on the book
            gateway_.shoot_order('B', take_price, 100, "AAPL");

            TradeLog log;
            log.timestamp = 0; // Or current time
            log.order_id = 999; // Dummy ID for signal
            log.price = best_ask.price;
            log.quantity = 100;
            log.side = 'B';
            log.action = 'S'; // 'S' for Signal
            
            log_queue.push(log); // <--- Takes ~50 nanoseconds
            
            // std::cout << std::format(">>> [SNIPER] ARB SIGNAL! Buy @ {:.2f} / Sell @ {:.2f} | PnL: {:.2f}", best_ask.price / 10000.0, best_bid.price / 10000.0, profit_per_share / 10000.0) << std::endl;
        }
    }
};