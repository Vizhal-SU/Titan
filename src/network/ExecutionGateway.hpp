#pragma once
#include <sys/socket.h>
#include <arpa/inet.h>
#include <netinet/tcp.h>
#include <unistd.h>
#include <iostream>
#include <thread>
#include <atomic>
#include <cstring>
#include <chrono>
#include "../parser/Ouch.hpp"

// --- 1. ADD 64-BIT SWAP HELPER ---
// Standard ntohl is only 32-bit. This handles the 64-bit MatchID.
inline uint64_t ntohll(uint64_t value) {
    static const int num = 42;
    if (*(const char*)&num == 42) { // Little Endian detection (Intel/AMD)
        const uint32_t high_part = ntohl(static_cast<uint32_t>(value >> 32));
        const uint32_t low_part = ntohl(static_cast<uint32_t>(value & 0xFFFFFFFFLL));
        return (static_cast<uint64_t>(low_part) << 32) | high_part;
    } else {
        return value; // Big Endian machine (Network order), no swap needed
    }
}

// --- 2. PACK THE STRUCT ---
// Critical: Tells compiler NOT to add padding bytes. Matches Python '>c14sIQ'
#pragma pack(push, 1)
struct ExecutionReport {
    char type;           // 'E'
    char token[14];      // The order ID you sent
    uint32_t qty;        // Executed Quantity (Big Endian)
    uint64_t match_id;   // Exchange Match ID (Big Endian)
};
#pragma pack(pop)

class ExecutionGateway {
private:
    int sock_ = -1;
    uint64_t next_order_id_ = 1;
    bool connected_ = false;
    LockFreeQueue<TradeLog, 4096>& log_q_;
    
    std::thread listener_thread_;
    std::atomic<bool> running_{false};

    // The Listener Loop (Runs in background)
    void listen_loop() {
        // We know the simulator always sends fixed-size Execution Reports (27 bytes usually, or sizeof struct)
        constexpr size_t EXPECTED_SIZE = sizeof(ExecutionReport);
        uint8_t buffer[EXPECTED_SIZE]; // Exact size buffer
        
        while (running_) {
            size_t total_received = 0;
            
            // --- THE FIX: LOOP UNTIL FULL ---
            // Keep reading until we have exactly EXPECTED_SIZE bytes
            while (total_received < EXPECTED_SIZE) {
                ssize_t n = recv(sock_, 
                                buffer + total_received,      // distinct write position
                                EXPECTED_SIZE - total_received, // remaining bytes needed
                                0);
                
                if (n <= 0) {
                    if (running_) std::cerr << "[GATEWAY] Disconnected!" << std::endl;
                    running_ = false;
                    return;
                }
                total_received += n;
            }

            if (buffer[0] == 'E') {
                auto* exec = reinterpret_cast<ExecutionReport*>(buffer);
                
                // Safe Token Handling
                char safe_token[15];
                std::memcpy(safe_token, exec->token, 14);
                safe_token[14] = '\0';

                // Network to Host Conversions
                uint32_t qty = ntohl(exec->qty);
                uint64_t match_id = ntohll(exec->match_id); // USE NEW HELPER

                // std::cout << ">>> [REAL TRADE] CONFIRMED! Token: " << safe_token << " | Qty: " << qty << " | MatchID: " << match_id << std::endl;
            }
        }
    }

public:
    ExecutionGateway(LockFreeQueue<TradeLog, 4096>& log_q) : log_q_(log_q) {}

    ~ExecutionGateway() {
        running_ = false;
        if (sock_ >= 0) {
            shutdown(sock_, SHUT_RDWR); // Force wake up recv()
            close(sock_);
        }
        if (listener_thread_.joinable()) listener_thread_.join();
    }

    bool connect_to_exchange(const char* ip, int port) {
        sock_ = socket(AF_INET, SOCK_STREAM, 0);
        if (sock_ < 0) return false;

        int flag = 1;
        setsockopt(sock_, IPPROTO_TCP, TCP_NODELAY, &flag, sizeof(flag));

        struct sockaddr_in addr{};
        addr.sin_family = AF_INET;
        addr.sin_port = htons(port);
        inet_pton(AF_INET, ip, &addr.sin_addr);

        while (connect(sock_, (struct sockaddr*)&addr, sizeof(addr)) < 0) {
            perror("[GATEWAY] Connection Failed");
            sleep(5);
            continue; 
        }

        connected_ = true;
        std::cout << "[GATEWAY] Connected to OUCH Server at " << ip << ":" << port << std::endl;

        running_ = true;
        listener_thread_ = std::thread(&ExecutionGateway::listen_loop, this);

        return true;
    }

    void shoot_order(char side, uint32_t price, uint32_t qty, const char* symbol) {
        if (!connected_) return;

        std::this_thread::sleep_for(std::chrono::microseconds(1000));

        EnterOrderMsg msg{};
        format_enter_order(msg, next_order_id_++, side, qty, price, symbol);

        send(sock_, &msg, sizeof(msg), 0);
        
        TradeLog log;
        log.timestamp = std::chrono::high_resolution_clock::now().time_since_epoch().count();
        log.order_id  = next_order_id_ - 1; 
        log.price     = price;
        log.quantity  = qty;
        log.action    = 'O'; 
        log.side      = side; 
        log.set_symbol(symbol); 

        log_q_.push(log);
        
        // std::cout << ">>> [EXEC] FIRED! " << symbol <<  (side == 'B' ? " BUY " : " SELL ") << qty << " @ " << (price / 10000.0) << std::endl;
        
        // sleep(1); 
    }
};