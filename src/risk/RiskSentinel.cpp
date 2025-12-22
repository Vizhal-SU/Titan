#include <iostream>
#include <thread>
#include <chrono>
#include <csignal>
#include <sys/mman.h>
#include <sys/stat.h>        /* For mode constants */
#include <fcntl.h>           /* For O_* constants */
#include <unistd.h>
#include <cstdlib>
#include <fstream>
#include <string>

// Include our Protocol
#include "../core/SharedState.hpp"

// --- CONFIGURATION ---
static constexpr double MAX_DAILY_LOSS = -5000.00; // Stop if we lose $5k
static constexpr int    MAX_INVENTORY  = 10000;    // Stop if we hold >10k shares total
static constexpr int    CHECK_INTERVAL_MS = 100;   // 10Hz check

// ANSI Colors for Scary Messages
#define RED     "\033[1;31m"
#define GREEN   "\033[1;32m"
#define RESET   "\033[0m"

pid_t get_engine_pid() {
    // Quick hack to find the PID of the running titan_engine
    // In production, the engine should write its PID to a file.
    char buf[512];
    FILE *cmd = popen("pidof titan_engine", "r");
    if (!cmd) return 0;
    if (fgets(buf, 512, cmd)) {
        pclose(cmd);
        return (pid_t)strtoul(buf, NULL, 10);
    }
    pclose(cmd);
    return 0;
}

int main() {
    std::cout << GREEN << "[SENTINEL] Risk Guardian Starting..." << RESET << std::endl;

    // 1. Connect to Shared Memory
    int shm_fd = shm_open("/titan_book", O_RDONLY, 0666);
    if (shm_fd == -1) {
        std::cerr << RED << "[ERROR] Could not open Shared Memory! Is Titan running?" << RESET << std::endl;
        return 1;
    }

    SharedBook* shm = (SharedBook*)mmap(0, 4096, PROT_READ, MAP_SHARED, shm_fd, 0);
    if (shm == MAP_FAILED) {
        perror("mmap");
        return 1;
    }

    std::cout << "[SENTINEL] Connected to Titan Memory." << std::endl;
    std::cout << "[SENTINEL] Limits: Loss < " << MAX_DAILY_LOSS << " | Inv > " << MAX_INVENTORY << std::endl;

    // 2. Monitoring Loop
    while (true) {
        // Find the Engine PID dynamically (in case you restart it)
        pid_t engine_pid = get_engine_pid();
        
        if (engine_pid == 0) {
            std::cout << "[SENTINEL] Waiting for Titan Engine..." << std::endl;
            std::this_thread::sleep_for(std::chrono::seconds(1));
            continue;
        }

        // --- THE CHECKS ---
        
        // A. PnL Check
        if (shm->global_pnl <= MAX_DAILY_LOSS) {
            std::cout << RED << "\n[RISK ALERT] MAX LOSS BREACHED: $" << shm->global_pnl << RESET << std::endl;
            std::cout << RED << "[KILL] TERMINATING ENGINE (PID " << engine_pid << ")..." << RESET << std::endl;
            
            kill(engine_pid, SIGTERM); // The Kill Switch
            break;
        }

        // B. Gross Inventory Check (Sum of absolute inventory)
        int total_exposure = 0;
        for (int i = 0; i < shm->active_count; i++) {
            total_exposure += std::abs(shm->items[i].quantity);
        }

        if (total_exposure > MAX_INVENTORY) {
            std::cout << RED << "\n[RISK ALERT] MAX INVENTORY BREACHED: " << total_exposure << " shares" << RESET << std::endl;
            std::cout << RED << "[KILL] TERMINATING ENGINE (PID " << engine_pid << ")..." << RESET << std::endl;
            
            kill(engine_pid, SIGTERM);
            break;
        }

        // Heartbeat log every 5 seconds (50 * 100ms)
        static int tick = 0;
        if (tick++ % 50 == 0) {
            std::cout << "[SENTINEL] Status OK. PnL: $" << shm->global_pnl 
                      << " | Exposure: " << total_exposure << "\r" << std::flush;
        }

        std::this_thread::sleep_for(std::chrono::milliseconds(CHECK_INTERVAL_MS));
    }

    return 0;
}
