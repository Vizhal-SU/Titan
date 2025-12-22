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
        LockFreeQueue<TradeLog, 4096>& log_q, // <--- ACCEPT REF
        std::atomic<bool>& running, 
        SharedBook* shared_mem )
    : queue_(queue), log_q_(log_q), running_(running), shared_snapshot_(shared_mem) {}

    void run() {
        pin_thread_to_core(3); 
        std::cout << "[STRATEGY] Engine Active on Core 3" << std::endl;

        ExecutionGateway gateway(log_q_);
        gateway.connect_to_exchange("127.0.0.1", 60000);
        
        // 65536 OrderBooks are created here via Default Constructor
        std::vector<OrderBook> books(65536); 

        // FIX: Configure the existing book instead of overwriting it
        // (Because OrderBook cannot be moved due to atomic spinlock)
        // books[1].set_shared_memory(shared_snapshot_);

        StockDirectory& directory = StockDirectory::instance();
        ArbSniper sniper(gateway, log_q_, shared_snapshot_);
        Event evt;

        // INIT: Start with Locate 1
        uint32_t current_locate = 1;
        // if (shared_snapshot_) {
        //     books[current_locate].set_shared_memory(shared_snapshot_);
        //     shared_snapshot_->active_locate = current_locate;
        //     shared_snapshot_->command_locate = current_locate; // Sync init
        // }

        while (running_) {
            // --- 1. CHECK FOR COMMANDS FROM PYTHON ---
            // if (shared_snapshot_) {
            //     uint32_t requested = shared_snapshot_->command_locate;
                
            //     // If Python asked for a different stock (and it's valid)
            //     if (requested != current_locate && requested > 0 && requested < 65536) {
                    
            //         // A. Detach old book
            //         books[current_locate].set_shared_memory(nullptr);
                    
            //         // B. Switch target
            //         current_locate = requested;
                    
            //         // C. Attach new book
            //         books[current_locate].set_shared_memory(shared_snapshot_);
                    
            //         // D. Confirm switch to Python
            //         shared_snapshot_->active_locate = current_locate;
            //     }
            // }
            
            while (queue_.pop(evt)) {
                uint16_t loc = 0;
                TradeLog log; // Create the log object
                bool should_log = false;

                if (evt.type == 'A') {
                    loc = evt.add.locate;
                    books[loc].add_order(evt.add);
                    log.timestamp = evt.add.timestamp;
                    log.order_id  = evt.add.order_ref;
                    log.price     = evt.add.price;
                    log.quantity  = evt.add.shares;
                    log.action    = 'A'; // 'A'dd
                    log.side      = evt.add.side;
                    log.set_symbol(directory.get_symbol(loc)); // Requires your new TradeLog
                    should_log = true;
                } 
                else if (evt.type == 'D') {
                    loc = evt.del.locate;
                    books[loc].cancel_order(evt.del);
                    log.timestamp = evt.del.timestamp;
                    log.order_id  = evt.del.order_ref;
                    log.price     = 0; // Deletes often don't have price, or you fetch from book
                    log.quantity  = 0; 
                    log.action    = 'D'; // 'D'elete
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
                    log.action    = 'E'; // 'E'xecute
                    log.side      = ' ';
                    log.set_symbol(directory.get_symbol(loc));
                    should_log = true;
                }

                if (loc > 0) {
                    sniper.on_book_update(books[loc], directory.get_symbol(loc));
                }
                if (should_log) {
                    log_q_.push(log);
                }
            }
        }
    }
};