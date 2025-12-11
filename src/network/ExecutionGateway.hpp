#pragma once
#include <sys/socket.h>
#include <arpa/inet.h>
#include <netinet/tcp.h> // For TCP_NODELAY
#include <unistd.h>
#include <iostream>
#include "../parser/Ouch.hpp"

class ExecutionGateway {
private:
    int sock_ = -1;
    uint64_t next_order_id_ = 1;
    bool connected_ = false;

public:
    bool connect_to_exchange(const char* ip, int port) {
        sock_ = socket(AF_INET, SOCK_STREAM, 0);
        if (sock_ < 0) return false;

        // 1. OPTIMIZATION: Disable Nagle's Algorithm
        // Without this, the OS waits to bundle small packets (adding 200ms latency!).
        // We want our 40-byte order to fly IMMEDIATELY.
        int flag = 1;
        setsockopt(sock_, IPPROTO_TCP, TCP_NODELAY, &flag, sizeof(flag));

        struct sockaddr_in addr{};
        addr.sin_family = AF_INET;
        addr.sin_port = htons(port);
        inet_pton(AF_INET, ip, &addr.sin_addr);

        if (connect(sock_, (struct sockaddr*)&addr, sizeof(addr)) < 0) {
            perror("[GATEWAY] Connection Failed");
            return false;
        }

        connected_ = true;
        std::cout << "[GATEWAY] Connected to OUCH Server at " << ip << ":" << port << std::endl;
        return true;
    }

    // The Trigger
    void shoot_order(char side, uint32_t price, uint32_t qty, const char* symbol) {
        if (!connected_) return;

        EnterOrderMsg msg{};
        format_enter_order(msg, next_order_id_++, side, qty, price, symbol);

        // Send raw bytes
        send(sock_, &msg, sizeof(msg), 0);
        
        // Log it (In real HFT, we log AFTER send to save nanoseconds)
        std::cout << ">>> [EXEC] FIRED! " << (side == 'B' ? "BUY " : "SELL") 
                  << qty << " @ " << (price / 10000.0) << std::endl;
    }
};