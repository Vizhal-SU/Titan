import streamlit as st
import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt
import os
import struct
import subprocess
import time

# --- CONFIGURATION ---
# Adjust these paths to match your environment
PROJECT_ROOT = "/home/vizhal/cpp_projects/Titan"
LOG_DIR      = os.path.join(PROJECT_ROOT, "logs")
Q_BINARY     = "/home/vizhal/.kx/bin/q"  # Verify this path!

# Environment setup for KDB+
os.environ["QLIC"]    = "/home/vizhal/.kx"
os.environ["QHOME"]   = "/home/vizhal/.kx/q"
os.environ["LOG_DIR"] = LOG_DIR

st.set_page_config(page_title="Titan Live Monitor", layout="wide")
st.title("⚡ Titan HFT Execution Monitor")

# --- 1. ETL LAYER (Python) ---
# Reads Binary -> Writes Raw CSV -> KDB+ does the math
def parse_bin_logs():
    """Parses C++ binary logs into temporary CSVs for KDB ingestion."""
    
    files = [("ouch.bin", "temp_ouch.csv"), ("itch.bin", "temp_itch.csv")]
    
    # STRUCT FORMAT (32 Bytes Total)
    # <  : Little Endian
    # Q  : Timestamp (8 bytes)
    # 8s : Symbol (8 bytes)
    # i  : Price (4 bytes) - Read as Int (KDB will scale it)
    # i  : Qty (4 bytes)
    # i  : OrderID (4 bytes)
    # 1s : Action (1 byte)
    # 1s : Side (1 byte)
    # 2x : Padding (2 bytes) - CRITICAL: Skips the C++ alignment bytes
    record_fmt = "<Q8siii1s1s2x" 
    record_size = 32
    
    for bin_file, csv_file in files:
        bin_path = os.path.join(LOG_DIR, bin_file)
        csv_path = os.path.join(LOG_DIR, csv_file)
        
        if not os.path.exists(bin_path):
            continue
            
        data = []
        try:
            with open(bin_path, "rb") as f:
                while chunk := f.read(record_size):
                    if len(chunk) != record_size: break
                    
                    # Unpack Raw Data
                    ts, sym, px, qty, oid, act, side = struct.unpack(record_fmt, chunk)
                    
                    # Clean Strings
                    sym_str = sym.decode('utf-8', errors='ignore').strip('\x00')
                    act_str = act.decode('utf-8', errors='ignore')
                    side_str = side.decode('utf-8', errors='ignore')
                    
                    # Append RAW values (KDB+ will handle Time Modulo and Price Scaling)
                    data.append((ts, sym_str, px, qty, oid, act_str, side_str))
        
            # Write to CSV (No Header, KDB+ schema handles it)
            if data:
                pd.DataFrame(data).to_csv(csv_path, index=False, header=False)
                
        except Exception as e:
            # Fail silently on file contention (C++ writing while we read)
            pass

# --- 2. ANALYTICS LAYER (KDB+) ---
def run_q(script_name, output_csv):
    """Runs a Q engine and returns the results."""
    script_path = os.path.join(PROJECT_ROOT, "scripts/q", script_name)
    csv_path = os.path.join(LOG_DIR, output_csv)
    
    # Pass output path to Q via Environment Variable
    env = os.environ.copy()
    env["OUT_CSV"] = csv_path
    
    try:
        subprocess.run([Q_BINARY, script_path], check=True, env=env, capture_output=True)
        # Check if file exists and has data (avoid empty CSV errors)
        if os.path.exists(csv_path) and os.path.getsize(csv_path) > 0:
            return pd.read_csv(csv_path)
    except subprocess.CalledProcessError as e:
        # Optional: Print Q errors to streamlit for debugging
        # st.error(f"Q Error: {e.stderr.decode()}")
        pass
        
    return pd.DataFrame() # Return empty DF on failure

# --- 3. UI LAYER (Streamlit) ---
# Create layout placeholders
col1, col2 = st.columns(2)
with col1:
    st.subheader("Tick-to-Trade Latency (µs)")
    lat_chart = st.empty()

with col2:
    st.subheader("Real-Time PnL ($)")
    pnl_chart = st.empty()

metrics_container = st.empty()

# Main Event Loop
while True:
    # A. Run ETL
    parse_bin_logs()
    
    # B. Update PnL
    df_pnl = run_q("pnl.q", "stats_pnl.csv")
    if not df_pnl.empty:
        # Metrics Row
        latest = df_pnl.iloc[-1]
        with metrics_container.container():
            m1, m2, m3 = st.columns(3)
            # Format PnL nicely (e.g. $1,250.50)
            m1.metric("Total PnL", f"${latest['cum_pnl']:,.2f}") 
            m2.metric("Inventory", f"{latest['inventory']} shares")
            m3.metric("Trades", len(df_pnl))
        
        # PnL Chart
        # Reset index to use 'Trade Number' as X-axis
        df_pnl = df_pnl.reset_index()
        fig2, ax2 = plt.subplots(figsize=(6, 3))
        sns.lineplot(data=df_pnl, x="index", y="cum_pnl", hue="sym", ax=ax2, linewidth=2)
        ax2.set_xlabel("Trade Count")
        ax2.set_ylabel("PnL ($)")
        ax2.legend(loc='upper left', bbox_to_anchor=(1, 1), fontsize='small')
        pnl_chart.pyplot(fig2)
        plt.close(fig2)

    # C. Update Latency
    df_lat = run_q("latency.q", "stats_latency.csv")
    if not df_lat.empty:
        # Convert Nanoseconds to Microseconds for display
        df_lat["latency_us"] = df_lat["bucket"] / 1000.0
        
        fig1, ax1 = plt.subplots(figsize=(6, 3))
        # Barplot is safer than KDE for sparse data
        sns.barplot(data=df_lat, x="latency_us", y="num_orders", hue="sym", ax=ax1)
        
        # Format X-axis to be readable
        ax1.set_xlabel("Latency (Microseconds)")
        ax1.set_ylabel("Count")
        # Only show every nth label if crowded
        for label in ax1.get_xticklabels():
            label.set_rotation(45)
            
        lat_chart.pyplot(fig1)
        plt.close(fig1)

    # Refresh Rate
    time.sleep(1)