**Purpose:** Your cheat sheet. These are the answers that get you hired. Memorize the *concepts*, not just the text.

# 🎤 Interview Q&A Preparation

High-yield technical questions for HFT/Systems Developer roles.

---

## 🧠 C++ & Low-Level Systems

### **Q: Why did you use a Ring Buffer instead of `std::queue`?**
**A:** `std::queue` is not thread-safe by default, requiring a `std::mutex`. Locking a mutex involves a kernel syscall (~2µs overhead) and puts the thread to sleep if contended.
My Ring Buffer is **Lock-Free**. It uses C++11 `std::atomic` with `memory_order_acquire` and `memory_order_release`. This operates entirely in user-space using CPU registers, taking nanoseconds and guaranteeing that the consumer thread never sleeps waiting for a lock.

### **Q: What is "False Sharing" and did you handle it?**
**A:** False Sharing occurs when two atomic variables (like `head` and `tail`) sit on the same 64-byte Cache Line. If Core 1 writes to `head`, it invalidates the entire cache line for Core 2, forcing it to reload `tail` from RAM.
**My Fix:** I used `alignas(64)` on the head and tail indices to force them onto separate cache lines.

### **Q: TCP vs UDP for HFT?**
**A:**
* **Market Data (Feed):** Ideally **UDP Multicast**. It’s faster (no ACKs) and allows one-to-many distribution. If a packet is lost, we don't ask for a retransmit (too slow); we just use the next snapshot.
* **Order Entry:** Must be **TCP**. We cannot afford to "lose" an order packet. The exchange requires a guaranteed sequence. I optimized TCP by disabling Nagle's Algorithm (`TCP_NODELAY`) to prevent buffering.

---

## 🏛 Architecture & Design

### **Q: How do you handle a "Slow Consumer" (e.g., Logger falls behind)?**
**A:**
* **Scenario:** The Strategy is generating 1M msgs/sec, but KDB+ can only ingest 500k. The Ring Buffer fills up.
* **My Solution:** Since Logging is non-critical for the live trade, I implement a **Drop Strategy** or a **Coalescing Strategy** for the Logger queue only. The Strategy must *never* block waiting for the Logger.
* **For Critical Path:** If the *Order Gateway* is the slow consumer, we have a catastrophic hardware failure. The system enters a "Panic State" and halts trading.

### **Q: Why C++ for the Engine but Python for the Simulator?**
**A:**
* **C++:** Essential for the Engine because we need manual memory management and deterministic CPU cycles. Garbage Collection (Java/Python) stops the world, which is unacceptable.
* **Python:** Used for the Simulator because speed of *development* mattered more than speed of *execution*. Python allows me to rapidly model complex market scenarios (Poisson processes) using `numpy`.

---

## 📉 Quant & Data

### **Q: Why KDB+? Why not PostgreSQL/Timescale?**
**A:** KDB+ is a column-store database with a built-in vector processing engine (q). In HFT, we don't select single rows; we operate on time-slices (vectors) of prices. KDB+ maps these vectors directly to memory/disk, allowing for O(1) appending and incredibly fast aggregation (VWAP) without the overhead of SQL parsing or row-based retrieval.

### **Q: How did you verify your system's latency?**
**A:** I didn't just use `std::chrono`. I utilized **User-Space Timestamping**. I take a timestamp (`rdtsc` instruction) when the packet hits the `recv` buffer and another when it hits `send`. This measures the internal processing time excluding the network wire time.

You are absolutely correct. The database write itself is **not** in the critical "Tick-to-Trade" hot path.

However, the **choice of database dictates the efficiency of the Logger Thread**. If your Logger Thread is slow (because it's fighting with a heavy SQL driver), it will drain the Ring Buffer too slowly. If the Ring Buffer fills up, it **back-pressures the Strategy Thread**, causing the hot path to stall.



### **Q: Since logging is off the hot path, why does the database choice (KDB+ vs Postgres) matter?**

**A:**
While the database write is asynchronous, the **Logger Thread** shares CPU resources (L3 cache, memory bandwidth) with the Strategy Thread. A heavy database driver can cause "Noisy Neighbor" issues that bleed latency into the hot path.

1. **Ingestion Weight (The "Backpressure" Risk):**
* **Postgres:** Requires constructing complex SQL strings (`INSERT INTO...`) or using heavy drivers (libpq/ODBC) that perform many memory allocations. If the Logger Thread cannot keep up with 1 million messages/sec, the Ring Buffer fills up, forcing the Strategy Engine to stall.
* **KDB+:** The C API (`c.o`) is incredibly lightweight. It serializes a struct into a binary stream with almost zero CPU overhead. It drains the Ring Buffer faster than the Strategy can fill it, guaranteeing the hot path is never blocked.


2. **Analytical Latency (The Dashboard):**
* **Postgres + Python:** To calculate a live VWAP, I would have to fetch millions of rows to Python ("Data to Code"), serialize them over the network, and loop over them. This creates massive latency, making a real-time 60fps dashboard impossible.
* **KDB+ (q):** I use **Vectorization**. The query `wavg[weight;price]` compiles to SIMD instructions inside the DB's memory ("Code to Data"). I can aggregate 10 million rows in microseconds and send only the final result to the dashboard.



**Summary:** I chose KDB+ not just for storage speed, but because its lightweight ingestion protects my Engine from backpressure, and its server-side analytics enable the real-time visualization.

---

