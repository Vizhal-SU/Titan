import socket
import struct
import time
import threading
import logging
import sys
import os

# ==============================================================================
#   TITAN TAPE REPLAY (Clean Sequential Mode)
# ==============================================================================
# 1. Reads NASDAQ ITCH 5.0 file sequentially.
# 2. Transcodes 6-byte Timestamps -> 8-byte (for C++ compatibility).
# 3. Builds Symbol Map naturally from the 'R' messages at the start of the file.
# 4. Matches your OUCH orders against the tape.

FILE_PATH = "01302020.NASDAQ_ITCH50" 
PLAYBACK_SPEED = 1.0  # 1.0 = Realtime, 0.0 = Max Speed (Stress Test)

# NETWORKING
MCAST_GRP = '224.0.2.1'
MCAST_PORT = 50000
OUCH_PORT = 60000

# TITAN SIM PROTOCOL (8-byte Timestamp)
FMT_SIM_ADD   = '>cHHQQcI8sI'   # 38 Bytes
FMT_SIM_EXEC  = '>cHHQQIQ'      # 31 Bytes
FMT_SIM_DEL   = '>cHHQQ'        # 19 Bytes
FMT_SIM_DIR   = '>cHHQ8s'       # 17 Bytes

# REAL ITCH CONSTANTS
MSG_ADD_ORDER = b'A'
MSG_ADD_ORDER_MPID = b'F'
MSG_EXECUTE = b'E'
MSG_EXECUTE_PRICE = b'C'
MSG_TRADE = b'P'
MSG_DELETE = b'D'
MSG_CANCEL = b'X'
MSG_DIRECTORY = b'R'
MSG_SYSTEM_EVENT = b'S'

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

class TitanTapeReplay:
    def __init__(self):
        self.running = True
        self.lock = threading.RLock()
        self.symbol_map = {}   # "AAPL" -> LocateID
        self.last_prices = {}  # LocateID -> Price
        self.user_orders = {}  # Your OUCH orders { LocateID: [Order...] }

        self.sock_mcast = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        self.sock_mcast.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 1)

    def send_itch(self, pkt):
        try: self.sock_mcast.sendto(pkt, (MCAST_GRP, MCAST_PORT))
        except: pass

    def send_ouch(self, sock, pkt):
        try: sock.send(pkt)
        except: pass

    # --- MATCHING ENGINE (Passive Orders) ---
    def check_match(self, locate, tape_price):
        if locate not in self.user_orders: return
        orders_to_fill = []
        with self.lock:
            # Iterate backwards to allow safe deletion
            for i in range(len(self.user_orders[locate]) - 1, -1, -1):
                order = self.user_orders[locate][i]
                
                # Check Limit Logic
                if (order['side'] == 'B' and tape_price <= order['price']) or \
                   (order['side'] == 'S' and tape_price >= order['price']):
                    orders_to_fill.append(order)
                    del self.user_orders[locate][i]

        for order in orders_to_fill:
            match_id = int(time.time_ns()) % 1000000
            logging.info(f"⚡ BOT FILLED @ {tape_price:.2f} (Token: {order['token'].hex()})")
            
            # Send OUCH Confirmation
            pkt = struct.pack('>c14sIQ', b'E', order['token'], order['qty'], match_id)
            self.send_ouch(order['sock'], pkt)

    # --- REPLAY LOGIC ---
    def run_replay(self):
        if not os.path.exists(FILE_PATH):
            logging.error(f"File {FILE_PATH} not found!")
            return

        logging.info(f"📂 Opening {FILE_PATH}...")
        f = open(FILE_PATH, 'rb')
        msg_count = 0
        
        while self.running:
            # Read ITCH Length (2 bytes)
            len_chunk = f.read(2)
            if not len_chunk: break
            msg_len = int.from_bytes(len_chunk, 'big')
            
            # Read Message Body
            msg_bytes = f.read(msg_len)
            if not msg_bytes: break

            msg_type = msg_bytes[0:1]

            try:
                # ---------------------------------------------------------
                # 1. DIRECTORY ('R') - Start of File
                # ---------------------------------------------------------
                if msg_type == MSG_DIRECTORY:
                    # Real ITCH 'R' (39 bytes): Loc(2) Track(2) Time(6) Stock(8) ...
                    loc = int.from_bytes(msg_bytes[1:3], 'big')
                    track = int.from_bytes(msg_bytes[3:5], 'big')
                    ts = int.from_bytes(msg_bytes[5:11], 'big')
                    stock = msg_bytes[11:19]
                    
                    # Store locally
                    sym_str = stock.decode().strip()
                    self.symbol_map[sym_str] = loc

                    # Transcode to Sim Format (8-byte TS) & Broadcast
                    pkt = struct.pack(FMT_SIM_DIR, b'R', loc, track, ts, stock)
                    self.send_itch(pkt)

                # ---------------------------------------------------------
                # 2. ADD ORDER ('A')
                # ---------------------------------------------------------
                elif msg_type == MSG_ADD_ORDER:
                    # Parse Real (6-byte TS)
                    loc = int.from_bytes(msg_bytes[1:3], 'big')
                    track = int.from_bytes(msg_bytes[3:5], 'big')
                    ts = int.from_bytes(msg_bytes[5:11], 'big')
                    ref = int.from_bytes(msg_bytes[11:19], 'big')
                    side = msg_bytes[19:20]
                    shares = int.from_bytes(msg_bytes[20:24], 'big')
                    sym = msg_bytes[24:32]
                    price = int.from_bytes(msg_bytes[32:36], 'big')

                    # Pack Sim (8-byte TS)
                    pkt = struct.pack(FMT_SIM_ADD, b'A', loc, track, ts, ref, side, shares, sym, price)
                    self.send_itch(pkt)

                # ---------------------------------------------------------
                # 3. EXECUTE ('E')
                # ---------------------------------------------------------
                elif msg_type == MSG_EXECUTE:
                    loc = int.from_bytes(msg_bytes[1:3], 'big')
                    track = int.from_bytes(msg_bytes[3:5], 'big')
                    ts = int.from_bytes(msg_bytes[5:11], 'big')
                    ref = int.from_bytes(msg_bytes[11:19], 'big')
                    qty = int.from_bytes(msg_bytes[19:23], 'big')
                    match = int.from_bytes(msg_bytes[23:31], 'big')

                    pkt = struct.pack(FMT_SIM_EXEC, b'E', loc, track, ts, ref, qty, match)
                    self.send_itch(pkt)

                # ---------------------------------------------------------
                # 4. DELETE ('D')
                # ---------------------------------------------------------
                elif msg_type == MSG_DELETE:
                    loc = int.from_bytes(msg_bytes[1:3], 'big')
                    track = int.from_bytes(msg_bytes[3:5], 'big')
                    ts = int.from_bytes(msg_bytes[5:11], 'big')
                    ref = int.from_bytes(msg_bytes[11:19], 'big')

                    pkt = struct.pack(FMT_SIM_DEL, b'D', loc, track, ts, ref)
                    self.send_itch(pkt)

                # ---------------------------------------------------------
                # 5. TRADE ('P') - Matching Logic Only
                # ---------------------------------------------------------
                elif msg_type == MSG_TRADE:
                    loc = int.from_bytes(msg_bytes[1:3], 'big')
                    # Price is at offset 24 for 'P' messages
                    price = int.from_bytes(msg_bytes[24:28], 'big') / 10000.0
                    
                    self.last_prices[loc] = price
                    self.check_match(loc, price)

            except Exception:
                pass 

            # Simple Throttling
            msg_count += 1
            if msg_count % 2000 == 0:
                time.sleep(0.0005 * (1.0/PLAYBACK_SPEED if PLAYBACK_SPEED > 0 else 0))
                if msg_count % 100000 == 0:
                    logging.info(f"Replayed {msg_count} msgs... (Found {len(self.symbol_map)} Symbols)")

        f.close()
        logging.info("End of Tape.")

    # --- OUCH GATEWAY (Standard) ---
    def run_gateway(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(('0.0.0.0', OUCH_PORT))
            s.listen()
            logging.info(f"🎯 OUCH Gateway Listening on {OUCH_PORT}")
            while self.running:
                conn, addr = s.accept()
                threading.Thread(target=self.handle_client, args=(conn,)).start()

    def handle_client(self, conn):
        with conn:
            while self.running:
                try:
                    data = conn.recv(1024)
                    if not data: break
                    if len(data) < 49: continue
                    
                    h = struct.unpack('>c14scI8sI', data[:32])
                    token, side, qty, sym_bytes, price_int = h[1], h[2].decode(), h[3], h[4], h[5]
                    sym = sym_bytes.decode().strip().replace('\x00','')
                    price = price_int / 10000.0
                    
                    loc = self.symbol_map.get(sym)
                    
                    if loc:
                        logging.info(f"⚡ RECV: {side} {sym} @ {price:.2f}")
                        
                        # Check Tape for Immediate Fill
                        last_px = self.last_prices.get(loc)
                        if last_px and ((side=='B' and price >= last_px) or (side=='S' and price <= last_px)):
                            match_id = int(time.time_ns()) % 1000000
                            pkt = struct.pack('>c14sIQ', b'E', token, qty, match_id)
                            self.send_ouch(conn, pkt)
                        else:
                            logging.info(f"📌 BOOKED: Waiting for Tape...")
                            with self.lock:
                                if loc not in self.user_orders: self.user_orders[loc] = []
                                self.user_orders[loc].append({'token': token, 'side': side, 'price': price, 'qty': qty, 'sock': conn})
                    else:
                        logging.warning(f"⚠️ Unknown Symbol: {sym} (Wait for Directory Msg)")

                except: break

if __name__ == "__main__":
    time.sleep(5)
    replay = TitanTapeReplay()
    threading.Thread(target=replay.run_replay).start()
    threading.Thread(target=replay.run_gateway).start()