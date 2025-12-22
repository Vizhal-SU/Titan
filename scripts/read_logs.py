# import struct
# import sys

# # Usage: python3 read_logs.py itch.bin
# # Usage: python3 read_logs.py ouch.bin

# if len(sys.argv) < 2:
#     print("Usage: python3 read_logs.py <filename>")
#     sys.exit(1)

# FILENAME = sys.argv[1]
# FMT = 'QQIIcc' 
# SIZE = struct.calcsize(FMT)

# print(f"--- READING {FILENAME} ---")

# try:
#     with open(FILENAME, 'rb') as f:
#         while chunk := f.read(SIZE):
#             data = struct.unpack(FMT, chunk)
#             # 0=Time, 1=ID, 2=Price, 3=Qty, 4=Side, 5=Action
#             action = data[5].decode()
#             side   = data[4].decode()
#             price  = data[2] / 10000.0
            
#             if action == 'O':
#                 print(f"🚀 [ORDER] SENT {side} {data[3]} @ {price:.2f}")
#             elif action == 'A':
#                 print(f"   [ITCH] Add  #{data[1]} {side} @ {price:.2f}")
#             elif action == 'D':
#                 print(f"   [ITCH] Del  #{data[1]}")
#             elif action == 'E':
#                 print(f"   [ITCH] Exec #{data[1]} Qty: {data[3]}")
                
# except FileNotFoundError:
#     print("File not found. Run the engine first.")


import struct
import sys
import os

def read_binary_log(filepath):
    if not os.path.exists(filepath):
        print(f"File not found: {filepath}")
        return

    # STRUCT FORMAT:
    # Q = uint64_t (8 bytes) - Timestamp
    # Q = uint64_t (8 bytes) - Order ID
    # I = uint32_t (4 bytes) - Price
    # I = uint32_t (4 bytes) - Quantity
    # c = char     (1 byte)  - Action
    # c = char     (1 byte)  - Side
    # xx = 2 pad bytes       - SKIP C++ PADDING
    # 8s = char[8] (8 bytes) - Symbol
    # xxxx = 4 pad bytes?    - (Likely needed if sizeof(TradeLog) is 40)
    
    # Try this format first (Total 40 bytes)
    fmt = "QQIIccxx8sxxxx" 
    struct_size = struct.calcsize(fmt)
    
    print(f"Reading {filepath}...")
    print(f"Struct Size: {struct_size} bytes")
    print("-" * 80)
    print(f"{'TIMESTAMP':<20} | {'ID':<10} | {'SYM':<6} | {'SIDE':<4} | {'PRICE':<10} | {'QTY':<5}")
    print("-" * 80)

    n =20
    with open(filepath, "rb") as f:
        while n>0:
            n-=1
            chunk = f.read(struct_size)
            if not chunk: break
            if len(chunk) < struct_size: break # Incomplete entry

            try:
                # Unpack
                ts, oid, price, qty, action, side, symbol = struct.unpack(fmt, chunk)

                # Decode bytes to strings
                # valid actions are ASCII, so they shouldn't crash
                act_str = action.decode('utf-8', errors='replace') 
                side_str = side.decode('utf-8', errors='replace')
                sym_str = symbol.decode('utf-8', errors='replace').strip('\x00')

                # Format Price (Assuming ITCH 4 decimals)
                price_f = price / 10000.0

                print(f"{ts:<20} | {oid:<10} | {sym_str:<6} | {side_str:<4} | {price_f:<10.2f} | {qty:<5}")

            except struct.error:
                print("[ERROR] Struct alignment mismatch.")
                break

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 read_logs.py <logfile>")
    else:
        read_binary_log(sys.argv[1])