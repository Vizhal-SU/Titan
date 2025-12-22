#pragma once

#include <iostream>
#include <unordered_map>
#include <cstring> 
#include <algorithm>
#include <chrono>
#include "../book/OrderBook.hpp"
#include "../network/ExecutionGateway.hpp"
#include "../core/Logger.hpp"
#include "../core/SharedState.hpp" 

struct StrategyState {
    uint32_t last_fired_price = 0;
    uint64_t last_fired_ts = 0;
    double   avg_entry_price = 0.0;
    int16_t  shm_index = -1; 
};

class ArbSniper {
private:
    ExecutionGateway& gateway_;
    LockFreeQueue<TradeLog, 4096>& log_q_;
    PortfolioSnapshot* shm_; 
    
    std::unordered_map<std::string, StrategyState> states_;
    std::unordered_map<std::string, int> inventory_;

    static constexpr uint64_t COOLDOWN_NS = 500 * 1000000; 
    static constexpr uint32_t MIN_PROFIT_TICKS = 200;      
    static constexpr int      MAX_POSITION = 5000;        

public:
    explicit ArbSniper(ExecutionGateway& gateway, LockFreeQueue<TradeLog, 4096>& log_q, PortfolioSnapshot* shm) 
        : gateway_(gateway), log_q_(log_q), shm_(shm) {
        states_.reserve(100);
        if (shm_) {
            shm_->active_count = 0;
            shm_->global_pnl = 0.0;
            shm_->global_trades = 0;
            shm_->sequence_id = 0;
        }
    }

    [[gnu::always_inline]] 
    void on_book_update(const OrderBook& book, const std::string& symbol) {
        if (book.bids_empty() || book.asks_empty()) [[unlikely]] { return; }

        StrategyState& state = states_[symbol];
        if (shm_ && state.shm_index == -1) register_symbol(symbol, state);

        const auto best_bid = book.get_best_bid();
        const auto best_ask = book.get_best_ask();
        
        // GLOBAL COOLDOWN
        uint64_t now = std::chrono::steady_clock::now().time_since_epoch().count();
        if (best_ask.price == state.last_fired_price && now - state.last_fired_ts < COOLDOWN_NS) return;

        int current_qty = inventory_[symbol];
        bool traded = false;
        double pnl_change = 0.0;

        // --- 1. SELL LOGIC (Check this FIRST or INDEPENDENTLY) ---
        // If we have shares, can we sell for a profit right now?
        if (current_qty > 0) {
            // Calculate profit against our entry price
            int32_t potential_profit = (int32_t)best_bid.price - (int32_t)state.avg_entry_price;
            
            // FIX: If potential_profit > 0, TAKE IT. Don't wait for 200 ticks.
            // Pure Arbitrage = Risk Free Profit. Even 1 tick is good.
            if (potential_profit > 0.02) { 
                gateway_.shoot_order('S', best_bid.price, 100, symbol.c_str());
                inventory_[symbol] -= 100;
                
                pnl_change += (potential_profit / 10000.0) * 100; 
                traded = true;
                
                // Update stats immediately so we don't double-count inventory below
                current_qty -= 100; 
                
                log_trade('S', best_bid.price, 100, symbol);
            }
        }

        // --- 2. BUY LOGIC (Entry) ---
        // Check this SECOND. If we just sold, we might want to buy back immediately if arb exists.
        // REMOVED 'else' so this runs even if we just sold.
        if (best_bid.price > best_ask.price && current_qty < MAX_POSITION) {
            
            gateway_.shoot_order('B', best_ask.price, 100, symbol.c_str());
            
            // --- VWAP CALCULATION (The Fix) ---
            if (current_qty == 0) {
                // First trade: Set price directly
                state.avg_entry_price = best_ask.price;
            } else {
                // Averaging Down: ((Old * Qty) + (New * 100)) / (Qty + 100)
                double total_value = (state.avg_entry_price * current_qty) + (best_ask.price * 100.0);
                state.avg_entry_price = total_value / (current_qty + 100);
            }

            inventory_[symbol] += 100;
            
            // Moving Average Entry Price Logic
            // If starting from 0, entry is Ask. If scaling, average it.
            // Simplified: Reset entry price if we were flat.
            // if (current_qty == 0) state.avg_entry_price = best_ask.price; 
            
            traded = true;
            log_trade('B', best_ask.price, 100, symbol);
        }
        
        // --- POST TRADE UPDATES ---
        if (traded) {
            state.last_fired_price = best_ask.price; 
            state.last_fired_ts = now;

            if (shm_) {
                shm_->global_pnl += pnl_change;
                shm_->global_trades++;
                shm_->sequence_id++; 
                if (state.shm_index >= 0) {
                    PositionEntry& p = shm_->items[state.shm_index];
                    p.quantity = inventory_[symbol]; 
                    p.realized_pnl += pnl_change;
                    p.trade_count++;
                    p.avg_entry_px = state.avg_entry_price / 10000.0;
                }
            }
        }
    }

private:
    void register_symbol(const std::string& symbol, StrategyState& state) {
        if (shm_->active_count >= 64) return; 
        int idx = shm_->active_count++; 
        state.shm_index = idx;
        PositionEntry& p = shm_->items[idx];
        std::memset(p.symbol, ' ', 8);
        std::memcpy(p.symbol, symbol.c_str(), std::min((size_t)8, symbol.size()));
        p.quantity = 0;
        p.realized_pnl = 0.0;
        p.trade_count = 0;
        p.avg_entry_px = 0.0;
    }

    void log_trade(char side, uint32_t price, int qty, const std::string& symbol) {
        TradeLog log;
        log.timestamp = std::chrono::high_resolution_clock::now().time_since_epoch().count();
        log.order_id  = 9999; 
        log.price     = price; 
        log.quantity  = qty;
        log.action    = 'O'; 
        log.side      = side; 
        log.set_symbol(symbol); 
        log_q_.push(log);
    }
};