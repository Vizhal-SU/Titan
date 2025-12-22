import os
import subprocess
import pandas as pd
import struct
import sys

# --- CONFIGURATION ---
# 1. THE EXACT BINARY YOU FOUND
Q_BINARY = "/home/vizhal/.kx/bin/q"

# 2. LICENSE & SYSTEM PATHS
# We assume QHOME is the 'q' folder inside .kx (where q.k usually lives)
os.environ["QLIC"]  = "/home/vizhal/.kx"
os.environ["QHOME"] = "/home/vizhal/.kx/q"

ITCH_FILE = "logs/itch.bin"
TEMP_CSV  = "logs/temp_trade.csv"

print("--- TITAN ANALYTICS (NATIVE KDB+) ---")

# --- 1. PYTHON: PARSE C++ BINARY ---
print("[1] Python: Parsing C++ Binary Logs...")

if not os.path.exists(Q_BINARY):
    sys.exit(f"[!] ERROR: q binary still not found at {Q_BINARY}")

if not os.path.exists(ITCH_FILE):
    sys.exit(f"[!] ERROR: Log file not found at {ITCH_FILE}")

data = []
# 32-byte Titan Layout: Time(8) Sym(8) Px(4) Qty(4) Oid(4) Act(1) Side(1) Pad(2)
STRUCT_FMT = "<Q8sIII1s1s2x"
RECORD_SIZE = 32

with open(ITCH_FILE, "rb") as f:
    while True:
        chunk = f.read(RECORD_SIZE)
        if len(chunk) != RECORD_SIZE: break
        ts, sym, px, qty, oid, act, side = struct.unpack(STRUCT_FMT, chunk)
        data.append({
            "time": ts, 
            "sym": sym.decode('utf-8').strip(),
            "price": px, 
            "qty": qty, 
            "oid": oid, 
            "side": side.decode('utf-8')
        })

df = pd.DataFrame(data)
print(f"    Parsed {len(df)} rows.")

# Write CSV for kdb+ ingestion
df.to_csv(TEMP_CSV, index=False, header=False)

# --- 2. KDB+: EXECUTE ANALYTICS ---
print("\n[2] KDB+: Executing Native Engine...")

q_script = f"""
/ TITAN ANALYTICS SCRIPT
/ Schema: time(long) sym(sym) price(int) qty(int) oid(int) side(sym)
schema: "JSIIIS";

/ 1. LOAD CSV (Returns a List of Columns)
raw_cols: (schema; ",") 0: `:{TEMP_CSV};

/ 2. CREATE TABLE WITH NAMES (Critical Step)
/ We map the list of columns (!) to a list of names
trade: flip `time`sym`price`qty`oid`side ! raw_cols;

show "--- SAMPLE TRADES ---";
show 5#trade;

show "--- VOLUME BY SYMBOL ---";
show select sum qty by sym from trade;

show "--- VWAP (HFT Metric) ---";
show select vwap:(qty wsum price)%sum qty by sym from trade;

\\\\
"""

try:
    process = subprocess.run(
        [Q_BINARY], 
        input=q_script.encode('utf-8'), 
        env=os.environ, 
        capture_output=True
    )
    print(process.stdout.decode('utf-8'))
    
    if process.stderr:
        # Filter out the standard KX banner to see real errors
        errs = [l for l in process.stderr.decode('utf-8').split('\n') if 'KX Systems' not in l and l.strip()]
        if errs: print("[!] STDERR:", "\n".join(errs))

except Exception as e:
    print(f"[!] Execution Failed: {e}")

# Cleanup
if os.path.exists(TEMP_CSV): os.remove(TEMP_CSV)