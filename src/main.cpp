#include <iostream>
#include <thread>
#include <atomic>
#include <sys/mman.h>
#include <fcntl.h>
#include <unistd.h>

#include "core/SharedState.hpp"
#include "core/LockFreeQueue.hpp"
#include "core/CpuUtils.hpp"
#include "core/Logger.hpp"
#include "server/MarketDataFeed.hpp"
#include "server/StrategyEngine.hpp"

// Global Signals
std::atomic<bool> running{true};
LockFreeQueue<Event, 4096> event_queue;
LockFreeQueue<TradeLog, 4096> log_queue;

SharedBook* setup_shared_memory() {
    int shm_fd = shm_open("/titan_book", O_CREAT | O_RDWR, 0666);
    if (shm_fd == -1) { perror("shm_open"); exit(1); }
    // Truncate to 4096 bytes to fit the portfolio array
    if (ftruncate(shm_fd, 4096) == -1) { perror("ftruncate"); exit(1); }
    return (SharedBook*)mmap(0, 4096, PROT_READ | PROT_WRITE, MAP_SHARED, shm_fd, 0);
}

int main() {
    pin_thread_to_core(2); // Main thread management on Core 2

    // 1. SETUP SHARED MEMORY (Bridge to Python)
    SharedBook* shared_ptr = setup_shared_memory();
    // Initialize sequence to 0 so Python knows it's fresh
    shared_ptr->sequence_id = 0; 

    std::cout << "========================================" << std::endl;
    std::cout << "   TITAN HFT ENGINE v2.0 (MODULAR)      " << std::endl;
    std::cout << "========================================" << std::endl;

    // 2. INSTANTIATE MODULES
    MarketDataFeed feed(event_queue, running);
    StrategyEngine engine(event_queue, log_queue, running, shared_ptr);

    // 3. LAUNCH THREADS
    // Logger might be a separate thread or part of strategy
    std::thread logger_thread(run_logger, std::ref(log_queue)); 
    
    // Strategy (Consumer) starts first to be ready for data
    std::thread strategy_thread([&](){ engine.run(); });

    // Feed (Producer) starts last to begin pumping data
    std::thread feed_thread([&](){ feed.start(); });

    // 4. WAIT FOR SHUTDOWN
    // In a real app, we'd wait for SIGINT (Ctrl+C)
    feed_thread.join();
    strategy_thread.join();
    logger_thread.join();

    return 0;
}