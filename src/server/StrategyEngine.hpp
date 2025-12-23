#pragma once

#include <vector>
#include <thread>
#include <atomic>
#include "../book/OrderBook.hpp"
#include "../strategy/ArbSniper.hpp"
#include "../network/ExecutionGateway.hpp"
#include "../core/LockFreeQueue.hpp"
#include "../core/CpuUtils.hpp"
#include "../core/SharedState.hpp"
#include "../core/StockDirectory.hpp"

class StrategyEngine {
    LockFreeQueue<Event, 4096>& queue_;
    LockFreeQueue<TradeLog, 4096>& log_q_;
    std::atomic<bool>& running_;
    SharedBook* shared_snapshot_; 

public:
    StrategyEngine(LockFreeQueue<Event, 4096>& queue, 
        LockFreeQueue<TradeLog, 4096>& log_q, 
        std::atomic<bool>& running, 
        SharedBook* shared_mem )
    : queue_(queue), log_q_(log_q), running_(running), shared_snapshot_(shared_mem) {}

    void run() {
        pin_thread_to_core(3); 
        std::cout << "[STRATEGY] Engine Active on Core 3" << std::endl;

        ExecutionGateway gateway(log_q_);
        gateway.connect_to_exchange("127.0.0.1", 60000);
        
        // 65536 OrderBooks are created here via Default Constructor
        // Allocating this on stack/heap is fine, it's ~100MB
        std::vector<OrderBook> books(65536); 

        StockDirectory& directory = StockDirectory::instance();
        ArbSniper sniper(gateway, log_q_, shared_snapshot_);
        Event evt;

        while (running_) {
            
            // Consume events from Feed
            // Note: queue_.pop() is non-blocking. If empty, we loop back to 'while(running_)'
            // This acts as a busy-wait loop, which is desired for HFT strategy (Low Latency).
            while (queue_.pop(evt)) {
                
                uint16_t loc = 0;
                TradeLog log; 
                bool should_log = false;

                if (evt.type == 'A') {
                    loc = evt.add.locate;
                    books[loc].add_order(evt.add);
                    
                    log.timestamp = evt.add.timestamp;
                    log.order_id  = evt.add.order_ref;
                    log.price     = evt.add.price;
                    log.quantity  = evt.add.shares;
                    log.action    = 'A'; 
                    log.side      = evt.add.side;
                    log.set_symbol(directory.get_symbol(loc)); 
                    should_log = true;
                } 
                else if (evt.type == 'D') {
                    loc = evt.del.locate;
                    books[loc].cancel_order(evt.del);
                    
                    log.timestamp = evt.del.timestamp;
                    log.order_id  = evt.del.order_ref;
                    log.price     = 0; 
                    log.quantity  = 0; 
                    log.action    = 'D'; 
                    log.side      = '-';
                    log.set_symbol(directory.get_symbol(loc));
                    should_log = true;
                }
                else if (evt.type == 'E') {
                    loc = evt.exec.locate;
                    books[loc].execute_order(evt.exec);
                    
                    log.timestamp = evt.exec.timestamp;
                    log.order_id  = evt.exec.order_ref;
                    log.price     = 0; 
                    log.quantity  = evt.exec.executed_shares;
                    log.action    = 'E';
                    log.side      = ' ';
                    log.set_symbol(directory.get_symbol(loc));
                    should_log = true;
                }

                // Run Strategy Logic
                if (loc > 0) {
                    sniper.on_book_update(books[loc], directory.get_symbol(loc));
                }

                // Log the event
                if (should_log) {
                    // CRITICAL FIX: Blocking Push
                    // If Logger is stuck (KDB full), we WAIT here.
                    // This creates backpressure so we don't drop logs.
                    if (!log_q_.push_blocking(log, running_)) {
                        goto shutdown; // Break out of everything if running_ becomes false
                    }
                }
            }
            
            // Optional: CPU Relax if queue is empty to save power?
            // For pure HFT, remove this. For dev/testing, keep it.
             _mm_pause(); 
        }
        
    shutdown:
        std::cout << "[STRATEGY] Thread Exiting..." << std::endl;
    }
};