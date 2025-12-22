import struct
import sys
import os

# CONFIGURATION
INPUT_FILE = '01302020.NASDAQ_ITCH50' 
OUTPUT_FILE = 'nasdaq_parsed.txt'
LIMIT = 1_000_000  # Limits to first 1 million messages (Safety). Set to None for ALL.

def convert():
    if not os.path.exists(INPUT_FILE):
        print(f"❌ Input file not found: {INPUT_FILE}")
        return

    print(f"🚀 Converting {INPUT_FILE} -> {OUTPUT_FILE}...")
    print(f"🛑 Limit: {LIMIT if LIMIT else 'NONE (Full File)'}")

    count = 0
    with open(INPUT_FILE, 'rb') as f_in, open(OUTPUT_FILE, 'w') as f_out:
        # Write Header
        f_out.write(f"{'MSG_NUM':<10} | {'TYPE':<4} | {'SYMBOL':<8} | {'PRICE':>10} | {'QTY':>6} | {'SIDE'}\n")
        f_out.write("-" * 60 + "\n")

        while True:
            # 1. Read Length (2 bytes)
            len_bytes = f_in.read(2)
            if not len_bytes: break
            msg_len = struct.unpack('>H', len_bytes)[0]
            
            # 2. Read Payload
            msg_data = f_in.read(msg_len)
            if not msg_data: break

            # 3. Parse Logic
            msg_type = chr(msg_data[0])
            
            try:
                # Stock Directory (R) - "Definition"
                if msg_type == 'R':
                    # Extract Locate(2) + ... + Stock(8) at offset 11
                    data = struct.unpack('>cHH6s8s', msg_data[:19])
                    loc = data[1]
                    sym = data[4].decode().strip()
                    f_out.write(f"{count:<10} | {'DIR':<4} | {sym:<8} | {'-':>10} | {'-':>6} | {'-'}\n")

                # Add Order (A) - "Trade"
                elif msg_type == 'A':
                    # Offset 0-19: Type, Loc, Track, Time, Ref, Side, Shares, Sym, Price
                    fmt = '>cHH6sQcI8sI'
                    data = struct.unpack(fmt, msg_data)
                    
                    side = data[5].decode()
                    shares = data[6]
                    sym = data[7].decode().strip()
                    price = data[8] / 10000.0
                    
                    f_out.write(f"{count:<10} | {'ADD':<4} | {sym:<8} | {price:>10.2f} | {shares:>6} | {side}\n")

                # Trade Executed (E)
                elif msg_type == 'E':
                    # ... add logic if needed ...
                    pass

            except Exception:
                pass # Skip corrupt/complex msgs

            count += 1
            if count % 100000 == 0:
                print(f"\rParsed {count} messages...", end='')
            
            # STOPPER
            if LIMIT and count >= LIMIT:
                print(f"\n✋ Reached limit of {LIMIT} lines.")
                break

    print(f"\n✅ Done! Saved to {OUTPUT_FILE}")

if __name__ == "__main__":
    convert()