import struct
import os
import random
import math

# CONFIG
LOG_DIR = "/home/vizhal/cpp_projects/Titan/logs"
OUCH_FILE = os.path.join(LOG_DIR, "ouch.bin")
ITCH_FILE = os.path.join(LOG_DIR, "itch.bin")

# 32-Byte Format (Matches your C++ & Q exactly)
FMT = "<Q8sIIIcc2x"

def generate_jitter():
    os.makedirs(LOG_DIR, exist_ok=True)
    print(f"[*] Generating 10,000 jittery trades in {LOG_DIR}...")
    
    with open(OUCH_FILE, "wb") as f_ouch, open(ITCH_FILE, "wb") as f_itch:
        
        symbols = ["AAPL", "GOOG", "MSFT", "TSLA", "AMZN"]
        start_time = 14400000000000  # 04:00:00
        
        # GENERATE 10,000 TRADES
        for i in range(1, 10001):
            
            # 1. Randomized Latency (Target: 15us average, +/- 5us jitter)
            # We use 'gauss' to create a Bell Curve
            latency = int(random.gauss(15000, 5000)) 
            if latency < 100: latency = 100 # Minimum physics limit
            
            ts_sent = start_time + (i * 100000) # One trade every 100us
            ts_fill = ts_sent + latency
            
            # 2. Random Symbol & Price
            sym_str = random.choice(symbols)
            sym = sym_str.encode().ljust(8, b'\x00')
            
            # Price Walk (Random Walk)
            base_price = 1500000
            price_int = base_price + int(random.gauss(0, 5000))
            
            qty = random.randint(1, 10) * 100
            oid = i
            
            # 3. Write Binary
            # OUCH (Sent)
            f_ouch.write(struct.pack(FMT, ts_sent, sym, price_int, qty, oid, b'O', b'B'))
            
            # ITCH (Filled)
            f_itch.write(struct.pack(FMT, ts_fill, sym, price_int, qty, oid, b'A', b'B'))
            
    print("[+] Done. 10k trades with realistic noise generated.")

if __name__ == "__main__":
    generate_jitter()