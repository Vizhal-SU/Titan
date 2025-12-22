import os
import subprocess
import pandas as pd
import struct
import matplotlib.pyplot as plt
import seaborn as sns
import sys

# --- CONFIG ---
Q_BINARY = "/home/vizhal/.kx/bin/q" # <--- VERIFY THIS PATH
PROJECT_ROOT = "/home/vizhal/cpp_projects/Titan"
LOG_DIR = os.path.join(PROJECT_ROOT, "logs")
Q_SCRIPT = os.path.join(PROJECT_ROOT, "scripts/q/latency.q")
RESULT_CSV = os.path.join(LOG_DIR, "latency_stats.csv")

# ENV SETUP
os.environ["QLIC"] = "/home/vizhal/.kx"
os.environ["QHOME"] = "/home/vizhal/.kx/q"
os.environ["LOG_DIR"] = LOG_DIR
os.environ["OUT_CSV"] = RESULT_CSV

# --- 1. ETL HELPER (Same as before) ---
def parse_bin(filename, csv_name):
    bin_path = os.path.join(LOG_DIR, filename)
    csv_path = os.path.join(LOG_DIR, csv_name)
    if not os.path.exists(bin_path): return
    
    data = []
    RECORD_SIZE = 32
    with open(bin_path, "rb") as f:
        while chunk := f.read(RECORD_SIZE):
            if len(chunk) != RECORD_SIZE: break
            # Schema: Time(8) Sym(8) Px(4) Qty(4) Oid(4) Act(1) Side(1)
            ts, sym, px, qty, oid, act, side = struct.unpack("<Q8sIII1s1s2x", chunk)
            data.append((ts, sym.decode().strip(), px, qty, oid, act.decode(), side.decode()))
    
    pd.DataFrame(data).to_csv(csv_path, index=False, header=False)

print("[1] Staging Data...")
parse_bin("ouch.bin", "temp_ouch.csv")
parse_bin("itch.bin", "temp_itch.csv")

# --- 2. RUN KDB+ ---
print("[2] Running kdb+ Analytics Engine...")
try:
    subprocess.run([Q_BINARY, Q_SCRIPT], check=True, env=os.environ)
except subprocess.CalledProcessError as e:
    print(f"Error running Q: {e}")
    sys.exit(1)

# --- 3. PYTHON VISUALIZATION ---
print("[3] Generating Graphs...")

# Load the aggregated data from kdb+
if not os.path.exists(RESULT_CSV):
    sys.exit("No results generated from kdb+")

df = pd.read_csv(RESULT_CSV)

# Check if data exists
if df.empty:
    print("No filled orders found to graph.")
    sys.exit()

# Setup Plot
plt.figure(figsize=(12, 6))
sns.set_style("darkgrid")

# Create Bar Chart (Histogram)
# x = Latency Bucket, y = Count, hue = Symbol
sns.barplot(data=df, x="bucket", y="num_orders", hue="sym")

plt.title(f"Titan System Latency Distribution (Tick-to-Trade)", fontsize=16)
plt.xlabel("Latency (nanoseconds)", fontsize=12)
plt.ylabel("Frequency (Order Count)", fontsize=12)
plt.xticks(rotation=45)

# Save
output_img = os.path.join(LOG_DIR, "latency_histogram.png")
plt.savefig(output_img)
print(f"[SUCCESS] Graph saved to: {output_img}")