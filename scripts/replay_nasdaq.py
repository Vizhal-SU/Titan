import socket
import struct
import time
import os
import sys

# --- CONFIGURATION ---
MCAST_GRP = '224.0.2.1'
MCAST_PORT = 50000

# Name of your extracted NASDAQ file
FILE_PATH = 'scripts/01302020.NASDAQ_ITCH50' 

# Speed Control:
# 0 = Max Speed (Stress Test)
# 0.0001 = Slow enough to watch logs
THROTTLE = 0 

def replay():
    print(f"[REPLAYER] Opening dataset: {FILE_PATH}")
    
    # 1. Setup UDP Multicast Socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 1)

    # 2. Open File
    if not os.path.exists(FILE_PATH):
        print(f"❌ Error: File '{FILE_PATH}' not found in current directory.")
        return

    try:
        with open(FILE_PATH, 'rb') as f:
            counter = 0
            start_time = time.time()
            
            while True:
                # 3. Read Header (2 bytes) -> Message Length
                # NASDAQ binary files prefix every message with a 2-byte integer (Big Endian)
                len_bytes = f.read(2)
                if not len_bytes: 
                    break # End of file
                
                msg_len = struct.unpack('>H', len_bytes)[0]
                
                # 4. Read Payload (The actual ITCH message)
                msg_data = f.read(msg_len)
                if not msg_data: 
                    break # Should not happen unless file is corrupted

                # 5. Send to Titan Engine
                sock.sendto(msg_data, (MCAST_GRP, MCAST_PORT))
                
                counter += 1
                
                # 6. Progress & Throttle
                if counter % 50000 == 0:
                    elapsed = time.time() - start_time
                    rate = counter / elapsed if elapsed > 0 else 0
                    print(f"\r[REPLAYER] Sent {counter} msgs | Rate: {rate:.0f} msgs/sec", end='')
                    
                    if THROTTLE > 0:
                        time.sleep(THROTTLE)

    except KeyboardInterrupt:
        print("\n[REPLAYER] Stopped by user.")
    
    print("\n[REPLAYER] Done.")

if __name__ == "__main__":
    replay()