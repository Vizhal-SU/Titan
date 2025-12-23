# ⚙️ Core Engine Architecture & Internals

**Titan Core** is a deterministic, ultra-low latency trading engine written in **C++17**. It is designed to minimize OS jitter, eliminate heap allocations on the hot path, and maximize CPU cache coherency.

---

## 1. Concurrency Model: The Lock-Free Ring Buffer

The heart of Titan's thread communication is a **Single-Producer Single-Consumer (SPSC) Lock-Free Ring Buffer**. This allows the Feed Handler thread to pass market data to the Strategy thread without ever triggering a kernel context switch (which costs ~3-5µs).

### **1.1 Architecture**
* **Type:** Fixed-size circular buffer (`std::array`).
* **Synchronization:** `std::atomic<size_t>` for head and tail indices.
* **Semantics:** * **Tail:** Only modified by Producer (Feed Handler).
    * **Head:** Only modified by Consumer (Strategy).

### **1.2 Critical Optimizations**

#### **A. Preventing False Sharing**
We use `alignas(64)` (hardware destructive interference size) to force the `head` and `tail` atomic variables onto separate CPU cache lines.
```cpp
template<typename T, size_t Size>
class RingBuffer {
    alignas(64) std::atomic<size_t> head_{0}; // Cache Line A
    alignas(64) std::atomic<size_t> tail_{0}; // Cache Line B (No contention)
    std::array<T, Size> buffer_;
};

```

* **Why:** If `head` and `tail` sit on the same cache line, Core 0 (Producer) writing to `tail` invalidates the cache line for Core 1 (Consumer) reading `head`. This "ping-ponging" forces data to go out to L3 cache or RAM, causing latency spikes of **20-100ns**. Separation keeps operations in L1 cache (~1ns).

#### **B. Memory Ordering (`std::memory_order`)**

We explicitly avoid the default `memory_order_seq_cst` (Sequential Consistency) because it issues heavy hardware memory fences.

* **Producer (Push):** Uses `std::memory_order_release`. This guarantees that the *data* is written to the buffer slot **before** the `tail` index is updated.
* **Consumer (Pop):** Uses `std::memory_order_acquire`. This guarantees that we read the `head` index **before** reading the data slot.
* **Result:** Correct visibility without the overhead of a global lock.

---

## 2. The Network Stack: `epoll` & Sockets

Titan manages its own TCP lifecycle using raw POSIX sockets, bypassing higher-level libraries (like ZeroMQ or Boost.Asio) to maintain deterministic control over the read/write cycle.

### **2.1 Event Loop (`epoll`)**

We use Linux's `epoll` in **Edge-Triggered (EPOLLET)** mode.

* **Why Edge-Triggered?** It notifies us *only* when new data arrives, reducing the number of syscalls compared to Level-Triggered (which keeps notifying as long as data exists).
* **Non-Blocking I/O:** All sockets are set to `O_NONBLOCK`. If a `read()` would block, we return immediately rather than putting the thread to sleep.

### **2.2 Zero-Copy Parsing**

Standard parsing copies bytes from the socket buffer to a local variable. Titan uses `reinterpret_cast` to overlay structs directly onto the buffer.

```cpp
// ❌ Bad (Copy)
ItchMsg msg;
std::memcpy(&msg, buffer, sizeof(msg));

// ✅ Good (Zero-Copy)
auto* msg = reinterpret_cast<const ItchMsg*>(buffer);

```

* **Constraint:** We use `#pragma pack(1)` on all protocol structs (ITCH/OUCH) to prevent the compiler from adding padding bytes, ensuring the memory layout matches the wire protocol exactly.

### **2.3 Latency Logic: Nagle's Algorithm**

We disable Nagle’s Algorithm using `setsockopt(fd, IPPROTO_TCP, TCP_NODELAY, ...)` on the outbound Order Entry socket.

* **Why:** Nagle buffers small packets to reduce bandwidth. In HFT, we cannot wait 40ms for the OS to bundle our order. We send immediately, even if the payload is tiny (e.g., 40 bytes).

---

## 3. Memory Management Strategy

**Golden Rule:** No `new`, `delete`, or `malloc` is allowed after the engine startup phase.

### **3.1 Object Pooling**

Dynamic allocation (`malloc`) involves traversing a free list and potentially locking the heap, which is non-deterministic.

* **Implementation:** Titan allocates a `std::vector<Order>` of 100,000 objects at startup.
* **Usage:** We maintain a `free_index`. Allocating is just `return &pool[free_index++]`. Deallocating is `free_index--`. This is O(1).

### **3.2 Stack vs. Heap**

Wherever possible, short-lived objects (like loop iterators or temporary pricing structs) are allocated on the **Stack**. Stack allocation essentially moves a pointer and is virtually free compared to Heap allocation.

---

## 4. Limit Order Book (LOB) Implementation

For the MVP, we utilize a `std::map`-based sparse book, but the architecture allows swapping for a dense vector-based book.

### **4.1 Data Structure**

* **Bids:** `std::map<double, double, std::greater<double>>` (Sorted Descending: Highest Bid First).
* **Asks:** `std::map<double, double>` (Sorted Ascending: Lowest Ask First).

### **4.2 Complexity**

* **Insertion/Update:** O(log N).
* **Top-of-Book Access:** O(1) via `.begin()`.
* **Trade-off:** While `std::map` is convenient, it suffers from poor cache locality because nodes are allocated randomly in memory.
* **Future Optimization:** Migration to a flat `std::vector` with binary search for insertion (O(N) move but O(1) cache hits) or a fixed-size price-level array (O(1) access).

---

## 5. Threading & CPU Pinning

Titan uses a **Thread-per-Core** architecture to minimize OS context switching.

### **5.1 Isolation**

* **Core 1:** Feed Handler (Network I/O).
* **Core 2:** Strategy Engine (Compute).
* **Core 3:** Logger (Disk/IPC I/O).

### **5.2 CPU Affinity**

We use `pthread_setaffinity_np` to pin threads to specific physical cores.

* **Why:** Prevents the OS scheduler from migrating the Strategy thread to a different core, which would result in a "Cold Cache" (L1/L2 cache misses) and a ~10-20µs latency penalty.

### **5.3 Busy Spinning**

The Strategy thread never sleeps (`sleep()` or `cond_wait`). It employs a **Busy Spin Loop** on the Ring Buffer.

```cpp
while (running_) {
    while (ring_buffer_.pop(msg)) {
        process(msg);
    }
    // No sleep() here! CPU stays hot (100% usage).
    std::this_thread::yield(); // Optional: purely to play nice with OS on localhost
}

```

* **Why:** Waking up a sleeping thread takes ~10-30µs. Spinning wastes energy but guarantees instant reaction time (nanoseconds).

---
