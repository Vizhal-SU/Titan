# ⚡ Titan: Ultra-Low Latency HFT Ecosystem

Titan is a purpose-built **High-Frequency Trading (HFT) Tickerplant and Execution Engine** designed to simulate the microstructure of modern electronic markets.

Unlike standard web applications, Titan is engineered for **determinism and nanosecond-level precision**. It simulates a complete exchange loop—from raw wire data to strategy execution and post-trade analytics—using a distributed architecture of C++, KDB+, and Python.

---

## 🚀 Key Performance Metrics
| Metric | Value | Context |
| :--- | :--- | :--- |
| **Wire-to-Wire Latency** | **~18 µs** | Time from Feed In $\to$ Strategy $\to$ Order Out (measured on localhost). |
| **Throughput** | **1.2M msgs/sec** | Peak message processing capability before Ring Buffer saturation. |
| **Jitter** | **< 4 µs** | 99th percentile variance under load (using spinlocks & CPU affinity). |

---

## 🛠 Technology Stack

### **1. Core Engine (The "Formula 1 Car")**
* **Language:** C++17 (Optimized for zero-copy & cache locality).
* **Networking:** Raw TCP Sockets with `epoll` (Linux) / `kqueue` (MacOS).
* **Concurrency:** Lock-free Single Producer Single Consumer (SPSC) Ring Buffers.
* **Protocols:** NASDAQ **ITCH 5.0** (Market Data) & **OUCH 4.2** (Order Entry).

### **2. Analytics & Data (The "Black Box")**
* **Database:** **KDB+/q** (Standard Time-Series DB in Tier-1 Banks).
* **Role:** Real-time Tickerplant (TP) capturing trades and order book updates.
* **Aggregation:** Server-side VWAP and OHLC calculation using vectorized q queries.

### **3. Simulation & Visualization**
* **Exchange Simulator:** Python 3.12 script generating realistic market microstructure (Poisson process order arrivals).
* **Dashboard:** **Streamlit** + **TradingView Lightweight Charts** (Canvas rendering) for zero-flicker, 60fps real-time visualization.

---

## 🏗 System Architecture
```mermaid
graph TD
    A[Exchange Sim (Python)] -->|TCP/ITCH| B(C++ Feed Handler)
    B -->|Ring Buffer| C{Strategy Engine}
    C -->|Decision Logic| D[Order Gateway]
    D -->|TCP/OUCH| A
    B -.->|Async Logging| E[KDB+ Tickerplant]
    E -->|IPC| F[Real-Time Dashboard]
```
---

## ⚡Quick Start
- Start KDB+ Tickerplant: `q scripts/db_init.q -p 5001`
- Launch Exchange Simulator: `python scripts/titan_exchange.py`
- Run Titan Engine: `./build/titan_engine`
- Visualize: `streamlit run scripts/dashboard.py`

