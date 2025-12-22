import struct
import sys
import os

# PATH TO YOUR MASSIVE BINARY FILE
# (Update this to point to your actual downloaded/extracted file)
FILE_PATH = '01302020.NASDAQ_ITCH50' 

def parse_itch_file(filename, num_messages=50):
    print(f"🔍 INSPECTING: {filename}")
    print(f"Reading first {num_messages} messages...\n")
    
    if not os.path.exists(filename):
        print("❌ File not found. Please check the path.")
        return

    try:
        with open(filename, 'rb') as f:
            for i in range(num_messages):
                # 1. READ LENGTH (2 Bytes, Big Endian)
                # NASDAQ files prefix every message with its length.
                len_bytes = f.read(2)
                if not len_bytes: break
                
                msg_len = struct.unpack('>H', len_bytes)[0]
                
                # 2. READ MESSAGE PAYLOAD
                msg_data = f.read(msg_len)
                if not msg_data: break
                
                # 3. DECODE MESSAGE TYPE (First byte)
                msg_type = chr(msg_data[0])
                
                print(f"[{i+1:>3}] Type: '{msg_type}' | Len: {msg_len} | ", end='')

                # --- DECODER LOGIC ---
                try:
                    # 'S' = System Event (Start of Day, etc.)
                    if msg_type == 'S':
                        # Format: Type(1) + StockLocate(2) + Tracking(2) + Time(6) + Event(1)
                        data = struct.unpack('>cHH6sc', msg_data)
                        event_code = data[4].decode()
                        print(f"System Event: {event_code}")

                    # 'R' = Stock Directory (Defines "Locate 1 = AAPL")
                    elif msg_type == 'R':
                        # Key fields: Locate(2), Stock(8)
                        # We skip some fields to just get the symbol
                        # Format: c(1) + H(2) + H(2) + 6s(Time) + 8s(Stock) + ... remainder
                        # We just unpack the first 19 bytes manually
                        header = struct.unpack('>cHH6s8s', msg_data[:19])
                        locate_id = header[1]
                        stock_sym = header[4].decode().strip()
                        print(f"✅ DIRECTORY: Locate {locate_id} = {stock_sym}")

                    # 'A' = Add Order (No MPID)
                    elif msg_type == 'A':
                        # Format: c(1)+H(2)+H(2)+6s(Time)+Q(Ref)+c(Side)+I(Shares)+8s(Sym)+I(Price)
                        fmt = '>cHH6sQcI8sI'
                        data = struct.unpack(fmt, msg_data)
                        
                        ref_id = data[4]
                        side   = data[5].decode()
                        shares = data[6]
                        sym    = data[7].decode().strip()
                        price  = data[8] / 10000.0
                        print(f"ADD ORDER: {side} {shares} {sym} @ ${price:.2f}")

                    # 'P' = Trade (Non-Cross) - Often used for hidden trades
                    elif msg_type == 'P':
                        fmt = '>cHH6sQcI8sIQ' # Simplified
                        data = struct.unpack(fmt, msg_data)
                        shares = data[6]
                        sym    = data[7].decode().strip()
                        price  = data[8] / 10000.0
                        print(f"TRADE: {shares} {sym} @ ${price:.2f}")

                    else:
                        print("(Other Message Type)")

                except Exception as e:
                    print(f"Error parsing body: {e}")

    except Exception as e:
        print(f"\n❌ CRITICAL ERROR: {e}")

if __name__ == "__main__":
    # You can pass the filename as an argument or edit FILE_PATH above
    target_file = sys.argv[1] if len(sys.argv) > 1 else FILE_PATH
    parse_itch_file(target_file, num_messages=100)