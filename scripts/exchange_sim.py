import socket
import struct
import time
import random
import threading
import logging
import os
import sys

# ==============================================================================
#   TITAN MARKET SIMULATOR (ALL-IN-ONE)
# ==============================================================================
# MODES:
# 1. 'SIM'   : Smart Random Walk (Best for dev/demo)
# 2. 'FAKE'  : Generates random ITCH noise at high speed (Stress Test)
# 3. 'REPLAY': Replays a downloaded .bin file (Real Data)

MODE = 'SIM'  # Options: 'SIM', 'FAKE', 'REPLAY' 
REJECT_MODE = False  # Set True to test ArbSniper's reject handling
FILE_PATH = '01302020.NASDAQ_ITCH50' # Only used for 'REPLAY' mode

# CONFIG
MCAST_GRP = '224.0.2.1'
MCAST_PORT = 50000
OUCH_PORT = 60000
LOG_DIR = 'logs'
LOG_FILE = 'exchange.log'

# ITCH 5.0 FORMATS
ITCH_ADD_FMT  = '>cHHQQcI8sI'
ITCH_EXEC_FMT = '>cHHQQIQ'
ITCH_DEL_FMT  = '>cHHQQ'
ITCH_DIR_FMT = '>cHHQ8s'
OUCH_ENTER_FMT = '>c14scI8sI' 
OUCH_REJECT_FMT = '>c14sc'
OUCH_MSG_SIZE = 49

# SETUP
if not os.path.exists(LOG_DIR): os.makedirs(LOG_DIR)
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(threadName)s: %(message)s',
    handlers=[logging.FileHandler(os.path.join(LOG_DIR, LOG_FILE)), logging.StreamHandler()]
)

active_orders = {}
lock = threading.RLock()
sock_mcast = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
sock_mcast.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 1)

# --- HELPER: PACKET SENDER ---
def send_udp(pkt):
    sock_mcast.sendto(pkt, (MCAST_GRP, MCAST_PORT))

# --- THREAD 1: OUCH SERVER (Handles Trades & Rejects) ---
def ouch_server_thread():
    status = "(REJECT MODE)" if REJECT_MODE else "(NORMAL MODE)"
    print(f"🎯 OUCH Gateway {status} Listening on {OUCH_PORT}")
    
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(('0.0.0.0', OUCH_PORT))
        s.listen()
        conn, addr = s.accept()
        
        with conn:
            logging.info(f"✅ Titan Connected: {addr}")
            while True:
                data = conn.recv(1024)
                if not data: break
                
                if len(data) >= OUCH_MSG_SIZE:
                    try:
                        header = struct.unpack(OUCH_ENTER_FMT, data[:32])
                        token = header[1]
                        side = header[2].decode()
                        qty  = header[3]
                        price= header[5] / 10000.0
                        sym  = header[4].decode().strip().replace('\x00', '')

                        logging.info(f"⚡ RECV: {side} {qty} {sym} @ {price:.2f}")

                        # --- REJECT MODE ---
                        if REJECT_MODE:
                            rej = struct.pack(OUCH_REJECT_FMT, b'J', token, b'R')
                            conn.sendall(rej)
                            logging.warning(f"🚫 REJECTED Order {token.hex()}")
                            continue # Skip matching logic

                        # --- NORMAL MATCHING MODE ---
                        matched_id = None
                        with lock:
                            for oid, info in active_orders.items():
                                if info['sym'] != sym: continue
                                if side == 'B' and info['side'] == 'S' and price >= info['price']:
                                    matched_id = oid; break
                                elif side == 'S' and info['side'] == 'B' and price <= info['price']:
                                    matched_id = oid; break
                        
                        if matched_id:
                            logging.info(f"✅ MATCHED against #{matched_id}")
                            # Send Execution Msg
                            pkt = struct.pack(ITCH_EXEC_FMT, b'E', 1, 1, time.time_ns(), matched_id, qty, 12345)
                            send_udp(pkt)
                            # Update Local State
                            with lock:
                                if matched_id in active_orders:
                                    active_orders[matched_id]['qty'] -= qty
                                    if active_orders[matched_id]['qty'] <= 0: del active_orders[matched_id]
                        else:
                            logging.warning(f"⚠️ NO LIQUIDITY for {sym} @ {price}")

                    except Exception as e:
                        logging.error(f"OUCH Error: {e}")

# --- THREAD 2: MARKET DATA (The 3 Modes) ---
def market_data_thread():
    print(f"🔥 Market Feed Started: MODE={MODE}")
    time.sleep(1) 

    # --- MODE 1: REPLAY FILE ---
    if MODE == 'REPLAY':
        if not os.path.exists(FILE_PATH):
            print(f"❌ Error: File {FILE_PATH} not found.")
            return
        
        with open(FILE_PATH, 'rb') as f:
            print(f"📂 Replaying {FILE_PATH}...")
            count = 0
            while True:
                len_bytes = f.read(2)
                if not len_bytes: break
                msg_len = struct.unpack('>H', len_bytes)[0]
                msg_data = f.read(msg_len)
                if not msg_data: break
                
                send_udp(msg_data)
                count += 1
                if count % 10000 == 0: print(f"\rSent {count} msgs...", end='')
                # time.sleep(0.00001) # Uncomment to slow down

    # --- MODE 2: FAKE NOISE GENERATOR ---
    elif MODE == 'FAKE':
        print("🔨 Generating Synthetic High-Load Traffic...")
        seq = 1
        while True:
            # Generate valid-looking garbage fast
            pkt = struct.pack(ITCH_ADD_FMT, b'A', 1, 1, time.time_ns(), seq, 
                              b'B' if random.random()>0.5 else b'S', 100, b'TEST', int(random.uniform(100,200)*10000))
            send_udp(pkt)
            seq += 1
            if seq % 10000 == 0: print(f"\rGenerated {seq} msgs...", end='')
            time.sleep(0.0001)

    # --- MODE 3: SMART SIM (Default) ---
    else:
        stocks = {
        1: {'sym': 'AAPL', 'price': 150.00}, 
        2: {'sym': 'MSFT', 'price': 280.00},
        3: {'sym': 'TSLA', 'price': 700.00},
        4: {'sym': 'NVDA', 'price': 450.00}
        }

        print("📢 Broadcasting Stock Directory...")
        for loc, info in stocks.items():
            # Pack the Directory Message
            # 'R' = Directory, loc = Stock ID, info['sym'] = Text Symbol
            pkt = struct.pack(
                ITCH_DIR_FMT, 
                b'R',           # Msg Type
                loc,            # Stock Locate ID
                1,              # Tracking
                time.time_ns(), # Timestamp
                info['sym'].encode().ljust(8) # Symbol (Padded to 8 bytes)
            )
            send_udp(pkt)
            logging.info(f"Dict: ID {loc} -> {info['sym']}")
            time.sleep(0.01) # Small gap to ensure C++ receives them cleanly

        print("✅ Directory Sent. Starting Trading Session...")
        time.sleep(1) # Give C++ time to process the map

        seq = 1000
        while True:
            # Pick random stock
            loc = random.choice(list(stocks.keys()))
            s = stocks[loc]
            
            # Random Walk
            s['price'] += random.uniform(-0.10, 0.10)
            price = round(s['price'], 2)
            
            # Publish Order
            side = b'B' if random.random() > 0.5 else b'S'
            pkt = struct.pack(ITCH_ADD_FMT, b'A', loc, 1, time.time_ns(), seq, side, 100, s['sym'].encode().ljust(8), int(price*10000))
            send_udp(pkt)
            
            # Save to internal state so OUCH can match it
            with lock:
                active_orders[seq] = {'side': side.decode(), 'qty': 100, 'price': price, 'sym': s['sym'], 'locate': loc}
            
            seq += 1
            
            # Create Arb Opportunity occasionally
            if random.random() < 0.05:
                # Cross the market
                arb_price = round(price - 0.50, 2)
                arb_pkt = struct.pack(ITCH_ADD_FMT, b'A', loc, 1, time.time_ns(), seq, b'S', 100, s['sym'].encode().ljust(8), int(arb_price*10000))
                send_udp(arb_pkt)
                with lock:
                    active_orders[seq] = {'side': 'S', 'qty': 100, 'price': arb_price, 'sym': s['sym'], 'locate': loc}
                seq += 1
                logging.info(f"🚨 ARB OPPORTUNITY: {s['sym']} Sell @ {arb_price}")
                time.sleep(0.5) # Give time to snipe

            time.sleep(0.01) # Readable speed

def main():
    t1 = threading.Thread(target=ouch_server_thread)
    t2 = threading.Thread(target=market_data_thread)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

if __name__ == "__main__":
    main()