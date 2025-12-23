
# 📊 Quantitative Analytics & Data Engineering

Titan utilizes **KDB+ (q)**, the industry-standard time-series database for high-frequency trading, to bridge the gap between raw C++ execution speed and human-readable analytics.

---

## 1. The Tickerplant Architecture (TP)

The KDB+ component operates as a **Linear Log Replayer** and **Real-Time Aggregator**. It decouples the trading engine from the dashboard, ensuring that heavy analytical queries never block the strategy thread.

### **1.1 Data Ingestion (IPC)**
The C++ Logger thread sends data asynchronously to KDB+ using the `c.o` (kdb+ C API) interface.
* **Function:** `.u.upd[table_name; data_list]`
* **Protocol:** Q IPC (TCP serialization).
* **Async:** The C++ engine does *not* wait for an acknowledgement (`k(-fd, ...)`), ensuring zero latency impact on the logger thread.

### **1.2 Schema Design**
We utilize strictly typed schemas to enable vectorization.

```q
/ Market Data Table (Ticks)
market:([] 
    time:`timestamp$(); 
    sym:`symbol$(); 
    price:`float$(); 
    size:`long$(); 
    side:`char$()
)

/ Orders Table (Execution Reconcilliation)
orders:([] 
    time:`timestamp$(); 
    orderID:`long$(); 
    clOrdID:`symbol$(); 
    price:`float$(); 
    qty:`long$(); 
    state:`symbol$()
)

```

* **Columnar Storage:** Unlike SQL (row-based), KDB+ stores `price` as a contiguous array of floats. Calculating `avg price` involves loading a single vector into the CPU cache, enabling SIMD (Single Instruction Multiple Data) execution.

---

## 2. Server-Side Aggregation (Anti-Aliasing)

A raw HFT feed generates millions of rows per hour. Rendering this raw data in a browser would crash the DOM. Titan implements **Dynamic Binning** to solve this.

### **2.1 The "Barcode" Problem**

Plotting 50,000 trades on a 1000-pixel wide screen results in "visual aliasing," where multiple data points fight for the same pixel, creating a solid wall of color (the "barcode effect").

### **2.2 The Solution: `xbar` Dynamic Querying**

We push the aggregation down to the database using q's `xbar` (floor/binning) function. The bin size changes dynamically based on the user's selected time window.

```q
/ Q Query for Dynamic OHLC (Open-High-Low-Close)
/ Variables: 
/   bin_size: 0D00:00:01 (1s) or 0D00:00:15 (15s)
/   lookback: cutoff timestamp

select 
    open:first price, 
    high:max price, 
    low:min price, 
    close:last price, 
    volume:sum size 
by time:bin_size xbar time 
from market 
where sym=sym_input, time > lookback

```

* **Efficiency:** KDB+ performs this aggregation across millions of rows in **microseconds** because the `time` column is sorted (using the attribute ``s#` implicitly), allowing binary search traversal.

---

## 3. Real-Time Dashboard Engineering

The dashboard is built with **Streamlit** and **TradingView Lightweight Charts**, optimized for zero-flicker updates.

### **3.1 The "Flicker" Challenge**

Standard Streamlit apps re-render the entire page logic on every update, causing UI flashing.

* **Solution:** We use `st.fragment` (Partial Re-renders) to isolate the chart component.
* **Outcome:** Only the chart JSON payload is updated over the websocket; the rest of the page (sidebar, header) remains static.

### **3.2 Dual-Axis Scaling**

* **Price:** ~$150.00
* **Volume:** ~10,000,000 shares
* **Challenge:** Plotting these on the same axis flattens the price line.
* **Implementation:** We implemented **Overlay Scaling** in the TradingView config, binding Volume to a separate, invisible scale compressed to the bottom 15% of the chart.

---


