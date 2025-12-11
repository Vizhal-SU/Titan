#include <iostream>
#include <vector>
#include <cstring>
#include <arpa/inet.h>
#include <sys/socket.h>
#include <unistd.h>
#include <format>

#include "parser/Itch.hpp"
#include "book/OrderBook.hpp"
#include "strategy/ArbSniper.hpp"
#include "network/ExecutionGateway.hpp"

constexpr int PORT = 50000;
constexpr const char* MULTICAST_IP = "224.0.2.1";
constexpr int BUFFER_SIZE = 1024;

int main() {
    // 1. Create UDP Socket
    int sock = socket(AF_INET, SOCK_DGRAM, 0);
    if (sock < 0) {
        perror("Socket creation failed");
        return 1;
    }

    // 2. Allow multiple listeners on the same port (SO_REUSEADDR)
    int reuse = 1;
    if (setsockopt(sock, SOL_SOCKET, SO_REUSEADDR, &reuse, sizeof(reuse)) < 0) {
        perror("Setting SO_REUSEADDR failed");
        return 1;
    }

    // 3. Bind to the Port
    struct sockaddr_in local_addr{};
    local_addr.sin_family = AF_INET;
    local_addr.sin_addr.s_addr = htonl(INADDR_ANY); // Listen on all interfaces
    local_addr.sin_port = htons(PORT);

    if (bind(sock, (struct sockaddr*)&local_addr, sizeof(local_addr)) < 0) {
        perror("Bind failed");
        return 1;
    }

    // 4. Join Multicast Group
    struct ip_mreq mreq{};
    mreq.imr_multiaddr.s_addr = inet_addr(MULTICAST_IP);
    mreq.imr_interface.s_addr = htonl(INADDR_ANY);

    if (setsockopt(sock, IPPROTO_IP, IP_ADD_MEMBERSHIP, &mreq, sizeof(mreq)) < 0) {
        perror("Multicast join failed");
        return 1;
    }

    std::cout << "listening for ITCH data on " << MULTICAST_IP << ":" << PORT << "..." << std::endl;


    // ==============================================================================
    // CONCEPT: The Hot Path (While Loop)
    // ==============================================================================
    // This loop is the "Heart" of the HFT system. 
    // RULE 1: No Memory Allocation (new/malloc) inside this loop.
    // RULE 2: No System Calls (printf, cout) on the critical path (we break this 
    //         only for this demo/debugging).
    // RULE 3: Keep the instruction cache hot (small, tight code).
    // ==============================================================================


    // Init Gateway
    ExecutionGateway gateway;
    // We will assume Python listens on Port 60000 (standard OUCH sim port)
    if (!gateway.connect_to_exchange("127.0.0.1", 60000)) {
        std::cerr << "WARNING: Could not connect to OUCH. Strategy will fire blanks." << std::endl;
    }


    // 5. Receive Loop
    char buffer[BUFFER_SIZE]; // Allocated on Stack (Fastest memory)
    OrderBook book;
    ArbSniper strategy(book, gateway); // Strategy instance


    while (true) {
        struct sockaddr_in sender_addr{};
        socklen_t sender_len = sizeof(sender_addr);
        
        // RECVFROM: In a real system, we would replace this with "Kernel Bypass"
        // (OpenOnload / DPDK) to read directly from the NIC's ring buffer,
        // skipping the OS interrupt overhead.
        
        ssize_t len = recvfrom(sock, buffer, BUFFER_SIZE, 0, 
                               (struct sockaddr*)&sender_addr, &sender_len);

        if (len > 0) {
            // 1. Check Message Type
            char msg_type = buffer[0];
            
            // Branch Prediction Hint: Most messages will be 'A' (Add Order) or 'E' (Exec).
            // We optimize for the common case.

            // ==================================================================
            // TRICK: Handling Packed Structs
            // ==================================================================
            // 'order.shares' is inside a packed struct, so it might be at an 
            // unaligned address (e.g., 0x...03 instead of 0x...04).
            // 
            // Creating a reference to it (const uint32_t&) is undefined behavior
            // on some CPUs (SIGBUS error).
            // 
            // FIX: static_cast<uint32_t>(...) forces a "Copy by Value", creating 
            // a temporary aligned variable on the stack that is safe to use.
            // ==================================================================

            if (msg_type == 'A') { // 'A' = Add Order
                AddOrderMsg order;
                parse_add_order(buffer, order);
                book.add_order(order);

                // RUN STRATEGY
                // This checks for arb immediately after the update
                strategy.on_book_update();
                
                // VISUALIZE
                // book.print_top_of_book();

                // // 3. Format Strings for display
                // std::string symbol(order.symbol, 8); // Convert char[8] to string
                // double real_price = order.price / 10000.0;
                
                // // 4. Print Readable Output
                // std::cout << std::format("[ITCH] OID:{} | {} {} | {} @ {:.2f}", 
                //         static_cast<uint64_t>(order.order_ref), // <--- CAST THIS
                //         (order.side == 'B' ? "BUY " : "SELL"), 
                //         symbol, 
                //         static_cast<uint32_t>(order.shares),    // <--- AND THIS
                //         real_price) 
                // << std::endl;
            }
            
            else if (msg_type == 'D') { // <--- NEW
                DeleteOrderMsg del;
                parse_delete_order(buffer, del);
                
                // Remove from book
                book.cancel_order(del);
                
                // Re-run strategy? 
                // Yes! Deleting a Best Bid might un-cross the market or reveal a new layer.
                strategy.on_book_update();
            }
        }
    }
    close(sock);
    return 0;
}