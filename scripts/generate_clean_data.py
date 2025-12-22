import struct
import os

# CONFIG
LOG_DIR = "/home/vizhal/cpp_projects/Titan/logs"
OUCH_FILE = os.path.join(LOG_DIR, "ouch.bin")
ITCH_FILE = os.path.join(LOG_DIR, "itch.bin")

# STRUCT FORMAT (32 Bytes)
# <   : Little Endian
# Q   : Timestamp (8)
# 8s  : Symbol (8)
# I   : Price (4) - unsigned int
# I   : Qty (4)
# I   : OID (4)
# c   : Action (1)
# c   : Side (1)
# 2x  : Pad (2) - Python will insert null bytes here
FMT = "<Q8sIIIcc2x"

def generate():
    os.makedirs(LOG_DIR, exist_ok=True)
    print(f"[*] Generating clean 32-byte binary logs in {LOG_DIR}...")
    
    with open(OUCH_FILE, "wb") as f_ouch, open(ITCH_FILE, "wb") as f_itch:
        
        symbols = ["AAPL", "GOOG", "MSFT", "TSLA", "AMZN"]
        start_time = 14400000000000  # 04:00:00 (Time since midnight)
        
        for i in range(1, 6):
            # DATA
            ts_sent = start_time + (i * 1000)
            ts_fill = ts_sent + 500
            sym = symbols[i-1].encode().ljust(8, b'\x00')
            
            # PRICE: $150.50 -> 1505000 (Fixed Point Integer)
            price_int = 1505000 + (i * 100) 
            qty = 100
            oid = i
            action = b'A' # Add
            side = b'B'   # Buy
            
            # WRITE OUCH
            f_ouch.write(struct.pack(FMT, ts_sent, sym, price_int, qty, oid, b'O', side))
            
            # WRITE ITCH
            f_itch.write(struct.pack(FMT, ts_fill, sym, price_int, qty, oid, b'A', side))
            
            print(f"    Created Order #{oid} for {symbols[i-1]}")

    print("[+] Done. Data matches TradeLog.hpp exactly.")

if __name__ == "__main__":
    generate()