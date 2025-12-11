#include <iostream>
#include <vector>
#include <cstring>
#include <arpa/inet.h>
#include <sys/socket.h>
#include <unistd.h>
#include <format>
#include <thread>
#include <atomic>
#include <chrono>
#include <sys/mman.h>
#include <fcntl.h>


#include "parser/Itch.hpp"
#include "parser/Ouch.hpp"
#include "book/OrderBook.hpp"
#include "strategy/ArbSniper.hpp"
#include "network/ExecutionGateway.hpp"
#include "core/LockFreeQueue.hpp"
#include "core/CpuUtils.hpp"
#include "core/Logger.hpp"
#include "core/SharedState.hpp"
#include "core/StockDirectory.hpp"

constexpr int PORT = 50000;
constexpr const char* MULTICAST_IP = "224.0.2.1";
constexpr int BUFFER_SIZE = 1024;


// --- INTERNAL QUEUE MESSAGE ---
// We don't push raw network packets (char buffer) into the queue because
// that requires copying 1024 bytes.
// Instead, we parse slightly earlier and push a tiny struct.
struct Event {
    char type; // 'A', 'D', 'E'
    union {
        AddOrderMsg add;
        DeleteOrderMsg del;
        OrderExecutedMsg exec;
    };
};


// GLOBAL QUEUE (Connecting the two threads)
// Size 4096 is plenty for this simulation.
LockFreeQueue<Event, 4096> event_queue;
std::atomic<bool> running{true};

// --- STRATEGY THREAD (CONSUMER) ---
void run_strategy() {
    pin_thread_to_core(3);
    std::cout << "[STRATEGY] Thread Started on Core 3" << std::endl;
    
    // Local Objects (Thread-Local is fast!)
    ExecutionGateway gateway;
    gateway.connect_to_exchange("127.0.0.1", 60000);
    
    std::vector<OrderBook> books(65536);    // we allocate 65536 books. This uses ~10MB of RAM. Cheap.
    StockDirectory directory;   // The Directory (Maps ID -> Name)
    
    ArbSniper sniper(gateway);
    
    Event evt;
    
    while (running) {
        // Busy Spin: In HFT, we never sleep. We spin.
        // If queue is empty, we just check again instantly.
        while (event_queue.pop(evt)) {
            // DISPATCHER: Route msg to the correct book using O(1) Indexing
            uint16_t locate_id = 0; 
            
            if (evt.type == 'A') {
                locate_id = evt.add.locate;
                auto new_order =  books[locate_id].add_order(evt.add);
                // sniper.on_book_update();

                TradeLog log;
                log.timestamp = evt.add.timestamp;
                log.order_id = evt.add.order_ref;
                log.price = new_order->price;
                log.quantity = new_order->quantity;
                log.side = new_order->side;
                log.action = 'A'; // 'A' for Add
                
                log_queue.push(log);
            } 
            else if (evt.type == 'D') {
                locate_id = evt.del.locate;
                auto removed_order = books[locate_id].cancel_order(evt.del);
                // sniper.on_book_update();

                TradeLog log;
                log.timestamp = evt.del.timestamp; // Use exchange timestamp
                log.order_id = evt.del.order_ref;
                log.action = 'C'; 
                log.price = removed_order->price;     // <--- Extracted from Book
                log.quantity = removed_order->quantity; // <--- Extracted from Book
                log.side = removed_order->side;       // <--- Extracted from Book
                log_queue.push(log);
            }

            if (locate_id > 0) {
                const std::string& sym = directory.get_symbol(locate_id);
                sniper.on_book_update(books[locate_id], sym);
            }
        }
        // book.publish_snapshot();
        // CPU Relaxation (Optional: prevents burning 100% CPU on laptop)
        // In Prod, we remove this. On laptop, keep it to save battery.
        // std::this_thread::yield(); 
    }
}


int main() {
    pin_thread_to_core(2);
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


    // 1. Create Shared Memory Object
    int shm_fd = shm_open("/titan_book", O_CREAT | O_RDWR, 0666);
    if (shm_fd == -1) {
        perror("shm_open failed");
        return 1;
    }

    // FIX: Check the return value of ftruncate
    if (ftruncate(shm_fd, sizeof(BookSnapshot)) == -1) {
        perror("ftruncate failed");
        return 1;
    }
    
    // 2. Map it
    shared_book_ptr = (BookSnapshot*)mmap(0, sizeof(BookSnapshot), PROT_READ | PROT_WRITE, MAP_SHARED, shm_fd, 0);

    std::thread logger_thread(run_logger);
    std::thread strategy_thread(run_strategy);
    std::cout << "[FEED] Listening for UDP..." << std::endl;

    char buffer[BUFFER_SIZE]; // Allocated on Stack (Fastest memory)

    // ==============================================================================
    // CONCEPT: The Hot Path (While Loop)
    // ==============================================================================
    // This loop is the "Heart" of the HFT system. 
    // RULE 1: No Memory Allocation (new/malloc) inside this loop.
    // RULE 2: No System Calls (printf, cout) on the critical path (we break this 
    //         only for this demo/debugging).
    // RULE 3: Keep the instruction cache hot (small, tight code).
    // ==============================================================================



    while (true) {
        // struct sockaddr_in sender_addr{};
        // socklen_t sender_len = sizeof(sender_addr);
        
        // RECVFROM: In a real system, we would replace this with "Kernel Bypass"
        // (OpenOnload / DPDK) to read directly from the NIC's ring buffer,
        // skipping the OS interrupt overhead.
        
        ssize_t len = recvfrom(sock, buffer, BUFFER_SIZE, MSG_DONTWAIT, nullptr, nullptr);

        if (len > 0) {
            // 1. Check Message Type
            char msg_type = buffer[0];
            Event evt;
            evt.type = msg_type;
            
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

            
            // Zero-Copy Parse -> Copy small struct to Queue
            if (msg_type == 'A') {
                parse_add_order(buffer, evt.add);
                event_queue.push(evt); // <--- Push to Ring Buffer
            } 
            else if (msg_type == 'D') {
                parse_delete_order(buffer, evt.del);
                event_queue.push(evt);
            }
        }
    }
    running = false;
    strategy_thread.join();
    close(sock);
    return 0;
}