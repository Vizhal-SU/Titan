#include <iostream>
#include <thread>
#include <atomic>
#include <csignal> // Required for signal handling
#include <sys/mman.h>
#include <fcntl.h>
#include <unistd.h>

#include "core/SharedState.hpp"
#include "core/LockFreeQueue.hpp"
#include "core/CpuUtils.hpp"
#include "core/Logger.hpp"
#include "server/MarketDataFeed.hpp"
#include "server/StrategyEngine.hpp"
#include "core/KdbPublisher.hpp"

// Global Signals
std::atomic<bool> running{true};
LockFreeQueue<Event, 4096> event_queue;
LockFreeQueue<TradeLog, 4096> log_queue;

// 1. SIGNAL HANDLER
void signal_handler(int signum) {
    std::cout << "\n[TITAN] Signal " << signum << " received. Initiating shutdown..." << std::endl;
    running = false; // This breaks the loops in all threads
}

SharedBook* setup_shared_memory() {
    int shm_fd = shm_open("/titan_book", O_CREAT | O_RDWR, 0666);
    if (shm_fd == -1) { perror("shm_open"); exit(1); }
    if (ftruncate(shm_fd, 4096) == -1) { perror("ftruncate"); exit(1); }
    return (SharedBook*)mmap(0, 4096, PROT_READ | PROT_WRITE, MAP_SHARED, shm_fd, 0);
}

int main() {
    // 2. REGISTER SIGNALS
    std::signal(SIGPIPE, SIG_IGN);
    std::signal(SIGINT, signal_handler);  // Ctrl+C
    std::signal(SIGTERM, signal_handler); // Kill command

    pin_thread_to_core(2); 

    SharedBook* shared_ptr = setup_shared_memory();
    shared_ptr->sequence_id = 0; 

    std::cout << "========================================" << std::endl;
    std::cout << "   TITAN HFT ENGINE v2.0 (MODULAR)      " << std::endl;
    std::cout << "========================================" << std::endl;

    MarketDataFeed feed(event_queue, running);
    StrategyEngine engine(event_queue, log_queue, running, shared_ptr);

    // 3. LAUNCH THREADS (Pass running to logger!)
    std::thread logger_thread(run_logger, std::ref(log_queue), std::ref(running)); 
    std::thread strategy_thread([&](){ engine.run(); });
    std::thread publisherThread(run_publisher, std::ref(running));
    std::thread feed_thread([&](){ feed.start(); });

    std::cout << "[MAIN] Engine running. Press Ctrl+C to stop." << std::endl;

    // 4. NON-BLOCKING WAIT LOOP
    // Instead of join() immediately, we loop until signal is caught
    while(running) {
        std::this_thread::sleep_for(std::chrono::milliseconds(100));
    }

    std::cout << "[MAIN] Shutdown signal detected. Waiting for threads..." << std::endl;

    // 5. JOIN THREADS
    if (feed_thread.joinable()) feed_thread.join();
    std::cout << "[MAIN] Feed stopped." << std::endl;

    if (strategy_thread.joinable()) strategy_thread.join();
    std::cout << "[MAIN] Strategy stopped." << std::endl;

    if (logger_thread.joinable()) logger_thread.join();
    std::cout << "[MAIN] Logger stopped." << std::endl;

    if (publisherThread.joinable()) publisherThread.join();
    std::cout << "[MAIN] Publisher stopped." << std::endl;

    return 0;
}