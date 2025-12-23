### 2. `Architecture.md`
**Purpose:** The "System Design" deep dive. Use this to answer questions like *"How do your components talk to each other?"*

```markdown
# 🏛 System Architecture & Design Choices

Titan is architected as a **Distributed Event-Driven System**. It decouples the critical path (trading) from the analytical path (logging) to ensure zero interference with strategy latency.

---

## 1. Data Flow Pipeline

### **Phase 1: Ingestion ( The Feed Handler)**
* **Source:** A TCP stream mimicking the NASDAQ ITCH 5.0 multicast feed.
* **Mechanism:**
    * Uses `epoll` (Edge-Triggered) to wake up only when data is available on the socket.
    * **Zero-Copy Parsing:** Instead of copying bytes to new structs, we cast `reinterpret_cast<ItchMsg*>(buffer)` directly over the raw receive buffer.
* **Handoff:** Parsed messages are pushed into a **Lock-Free Ring Buffer** (`std::atomic` head/tail indices). This allows the Feed Handler thread to immediately return to listening without waiting for the Strategy to process the message.

### **Phase 2: The Critical Path (Strategy Engine)**
* **Execution:** Pinned to an isolated CPU core to prevent OS context switching.
* **Logic:**
    1.  Polls the Ring Buffer.
    2.  Updates the internal Limit Order Book (LOB) state (Bids/Asks).
    3.  Evaluates signals (e.g., *Momentum Skew* or *Order Imbalance*).
    4.  **Action:** If a signal triggers, it constructs an OUCH order packet and writes directly to the outbound TCP socket buffer.
* **Constraint:** No memory allocation (`new`/`malloc`) is allowed here. All objects are pre-allocated at startup.

### **Phase 3: The Analytical Path (KDB+ Logging)**
* **Decoupling:** Logging is slow (disk I/O). We must never log on the strategy thread.
* **Solution:** A secondary Ring Buffer connects the Strategy to a separate **Logger Thread**.
* **KDB+ Interface:** The Logger Thread formats data into `k` objects (KDB+ C API) and flushes them to the Tickerplant process asynchronously over IPC.

---

## 2. Key Design Decisions

### **Why Ring Buffers instead of `std::queue`?**
* `std::queue` uses a `std::mutex` for thread safety. Locking a mutex requires a kernel syscall, which takes **~1-3 µs**.
* **Titan's Ring Buffer:** Uses atomic `load/store` with `memory_order_acquire/release`. This operates entirely in user-space CPU registers, taking **~10-50 nanoseconds**.

### **Why KDB+/q?**
* SQL databases are row-based and slow for time-series aggregation.
* KDB+ is column-oriented and vector-processing based.
* **Example:** Calculating VWAP for 1 million trades takes milliseconds in Python but microseconds in KDB+, allowing the dashboard to query the DB 60 times a second without lag.

### **Why Custom TCP instead of ZeroMQ/gRPC?**
* Libraries like ZeroMQ manage their own background threads and queues, introducing unpredictable "jitter" (latency spikes).
* By writing raw socket code, we control exactly when data is read and written, ensuring deterministic behavior.

---