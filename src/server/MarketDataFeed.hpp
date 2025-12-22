#pragma once

#include <iostream>
#include <vector>
#include <cstring>
#include <arpa/inet.h>
#include <sys/socket.h>
#include <unistd.h>
#include <atomic>
#include "../core/LockFreeQueue.hpp"
#include "../core/SharedState.hpp"
#include "../core/StockDirectory.hpp"
#include "../parser/Itch.hpp"

constexpr int PORT = 50000;
constexpr const char* MULTICAST_IP = "127.0.0.1";
constexpr int BUFFER_SIZE = 1024;

class MarketDataFeed {
    int sock;
    LockFreeQueue<Event, 4096>& queue_;
    std::atomic<bool>& running_;

public:
    MarketDataFeed(LockFreeQueue<Event, 4096>& queue, std::atomic<bool>& running) 
        : queue_(queue), running_(running) {
        setup_socket();
    }

    ~MarketDataFeed() {
        close(sock);
    }

    void start() {
        std::cout << "[FEED] Listening on " << MULTICAST_IP << ":" << PORT << std::endl;
        char buffer[BUFFER_SIZE];

        while (running_) {
            // BLOCKING READ (with timeout or non-blocking in real prod)
            ssize_t len = recvfrom(sock, buffer, BUFFER_SIZE, 0, nullptr, nullptr);

            if (len > 0) {
                Event evt;
                evt.type = buffer[0];

                // Optimistic parsing: Assume 'A' (Add) is most common
                if (evt.type == 'A') {
                    parse_add_order(buffer, evt.add);
                    queue_.push(evt); 
                } 
                else if (evt.type == 'D') {
                    parse_delete_order(buffer, evt.del);
                    queue_.push(evt);
                }
                else if (evt.type == 'E') {
                    parse_order_executed(buffer, evt.exec);
                    queue_.push(evt);
                }
                else if (evt.type == 'R') {
                    DirectoryMsg dir_msg;
                    parse_directory(buffer, dir_msg);
                    StockDirectory::instance().on_directory_message(dir_msg);
                }
            }
        }
    }

private:
    void setup_socket() {
        sock = socket(AF_INET, SOCK_DGRAM, 0);
        if (sock < 0) { 
            perror("Socket creation failed"); 
            exit(1); 
        }

        int reuse = 1;
        setsockopt(sock, SOL_SOCKET, SO_REUSEADDR, &reuse, sizeof(reuse));

        struct sockaddr_in local_addr{};
        local_addr.sin_family = AF_INET;
        local_addr.sin_addr.s_addr = inet_addr("127.0.0.1");
        local_addr.sin_port = htons(PORT);
        if (bind(sock, (struct sockaddr*)&local_addr, sizeof(local_addr)) < 0) {
            perror("Bind failed");
            exit(1);
        }
        // struct ip_mreq mreq{};
        // mreq.imr_multiaddr.s_addr = inet_addr(MULTICAST_IP);
        // // mreq.imr_interface.s_addr = htonl(INADDR_ANY);
        // mreq.imr_interface.s_addr = inet_addr("127.0.0.1");
        // setsockopt(sock, IPPROTO_IP, IP_ADD_MEMBERSHIP, &mreq, sizeof(mreq));
        std::cout << "[FEED] Socket bound to 127.0.0.1:" << PORT << " (Unicast Mode)" << std::endl;
    }
};