import socket
import struct
import time
import random
import threading
import sys
import argparse
import heapq
import collections

# ==============================================================================
#   TITAN EXCHANGE V17 (Fixed Starvation)
#   - Solves "Nothing Happening" in Stress Mode
#   - Adds explicit thread yielding to prevent GIL starvation
# ==============================================================================

MCAST_GRP  = '127.0.0.1'
MCAST_PORT = 50000
OUCH_PORT  = 60000

FILE_ITCH = 'itch.bin'
FILE_OUCH = 'ouch.bin'

# --- 1. UNIVERSE ---
SECTORS = {
    'TECH':   [1, 2, 3, 4, 5],
    'FINANCE':[6, 7, 8, 9, 10],
    'ENERGY': [11, 12, 13, 14, 15]
}

STOCKS = {
    1: 'AAPL', 2: 'MSFT', 3: 'GOOG', 4: 'NVDA', 5: 'TSLA',
    6: 'JPM',  7: 'BAC',  8: 'GS',   9: 'MS',   10: 'V',
    11: 'XOM', 12: 'CVX', 13: 'BP',  14: 'SHEL', 15: 'COP'
}

START_PRICES = {
    1: 150.00, 2: 310.00, 3: 2800.00, 4: 460.00, 5: 240.00,
    6: 140.00, 7: 35.00,  8: 350.00,  9: 90.00,  10: 230.00,
    11: 110.00, 12: 160.00, 13: 38.00, 14: 65.00, 15: 120.00
}

# Add 1000 Penny Stocks
for i in range(1000, 2000):
    STOCKS[i] = f"TITAN{i-1000:03d}"
    START_PRICES[i] = random.uniform(10.0, 50.0)

CURR_PRICES = START_PRICES.copy()
VOLUMES = {k: 0 for k in STOCKS}
SYM_TO_ID = {v: k for k, v in STOCKS.items()}

# --- BINARY FORMATS ---
FMT_ITCH_ADD   = '>cHHQQcI8sI'
FMT_ITCH_DIR   = '>cHHQ8s'
FMT_ITCH_EXEC  = '>cHHQQIQ'
FMT_OUCH_ENTER = '>c14scI8sI'
FMT_OUCH_EXEC  = '>c14sIQ'

# --- COLORS ---
C_RESET  = "\033[0m"
C_GREEN  = "\033[92m"
C_RED    = "\033[91m"
C_BLUE   = "\033[94m"
C_CYAN   = "\033[96m"
C_BOLD   = "\033[1m"
C_WHITE  = "\033[97m"

class Order:
    __slots__ = ['id', 'price', 'qty', 'side', 'timestamp', 'token', 'sock']
    def __init__(self, oid, price, qty, side, timestamp, token, sock):
        self.id, self.price, self.qty, self.side = oid, price, qty, side
        self.timestamp, self.token, self.sock = timestamp, token, sock
    
    def __lt__(self, other):
        if self.price != other.price: return self.price < other.price
        return self.timestamp < other.timestamp

class TitanExchange:
    def __init__(self, stress_mode=False):
        self.books = {i: {'B': [], 'S': []} for i in STOCKS}
        self.lock = threading.RLock()
        self.running = True
        self.stress_mode = stress_mode
        
        self.msg_log = collections.deque(maxlen=7)
        self.ops_counter = 0
        self.bytes_received = 0 # New Debug Counter
        self.active_clients = 0
        self.feed_active = False
        self.feed_start_event = threading.Event()

        with open(FILE_ITCH, 'wb'): pass
        with open(FILE_OUCH, 'wb'): pass
        self.f_itch = open(FILE_ITCH, 'ab')
        self.f_ouch = open(FILE_OUCH, 'ab')

        self.sock_mcast = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        # self.sock_mcast.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_LOOP, 1)
        # self.sock_mcast.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)

        if not self.stress_mode:
            self.log_ui(f"{C_WHITE}System Initialized. Universe: {len(STOCKS)} Stocks.{C_RESET}")

    def log_ui(self, msg):
        if self.stress_mode: return
        ts = time.strftime("%H:%M:%S")
        self.msg_log.append(f"[{ts}] {msg}")

    def send_itch(self, pkt):
        self.f_itch.write(pkt)
        if not self.stress_mode: 
            self.f_itch.flush()

        try: self.sock_mcast.sendto(pkt, (MCAST_GRP, MCAST_PORT))
        except: pass

    def send_ouch(self, sock, pkt):
        self.f_ouch.write(pkt); self.f_ouch.flush()
        if sock:
            try: sock.send(pkt)
            except: pass

    # --- ENGINE ---
    def process_order(self, side, price, qty, loc_id, sym_str, sock=None, token=None):
        self.ops_counter += 1
        if isinstance(sym_str, str): sym_bytes = sym_str.encode().ljust(8)
        else: sym_bytes = sym_str

        with self.lock:
            book = self.books[loc_id]
            opp_side = 'S' if side == 'B' else 'B'
            
            while qty > 0 and book[opp_side]:
                best = book[opp_side][0]
                if side == 'B':
                    if price < best.price: break 
                else: 
                    if price > -best.price: break

                exec_qty = min(qty, best.qty)
                match_id = int(time.time_ns()) % 1000000000
                VOLUMES[loc_id] += exec_qty
                
                self.send_itch(struct.pack(FMT_ITCH_EXEC, b'E', loc_id, 1, time.time_ns(), best.id, exec_qty, match_id))
                if best.sock: self.send_ouch(best.sock, struct.pack(FMT_OUCH_EXEC, b'E', best.token, exec_qty, match_id))
                if sock:
                    self.send_ouch(sock, struct.pack(FMT_OUCH_EXEC, b'E', token, exec_qty, match_id))
                    if not self.stress_mode:
                        p = best.price if opp_side == 'S' else -best.price
                        if side == 'B': self.log_ui(f"{C_GREEN}📈 BUY FILL: {sym_str} {exec_qty} @ {p:.2f}{C_RESET}")
                        else: self.log_ui(f"{C_RED}📉 SELL FILL: {sym_str} {exec_qty} @ {p:.2f}{C_RESET}")

                best.qty -= exec_qty
                qty -= exec_qty
                if best.qty == 0: heapq.heappop(book[opp_side])
            
            if qty > 0:
                new_id = int(time.time_ns()) % 1000000000
                store_price = price if side == 'S' else -price
                heapq.heappush(book[side], Order(new_id, store_price, qty, side, time.time_ns(), token, sock))
                self.send_itch(struct.pack(FMT_ITCH_ADD, b'A', loc_id, 1, time.time_ns(), new_id, side.encode(), qty, sym_bytes, int(price*10000)))

    # --- GATEWAY (Fixed Fragmentation) ---
    def run_gateway(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            s.bind(('0.0.0.0', OUCH_PORT))
            s.listen()
            while self.running:
                conn, addr = s.accept()
                if not self.feed_active: self.feed_start_event.set()
                if not self.stress_mode: self.log_ui(f"{C_WHITE}Client Connected: {addr[0]}{C_RESET}")
                self.active_clients += 1
                threading.Thread(target=self.handle_client, args=(conn,)).start()

    def handle_client(self, conn):
        conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        buffer = b''
        try:
            while self.running:
                # Increased buffer size for stress mode
                data = conn.recv(32768)
                if not data: break
                
                self.bytes_received += len(data) # Debug Stat
                buffer += data 
                
                while len(buffer) >= 32:
                    pkt = buffer[:32]
                    h = struct.unpack(FMT_OUCH_ENTER, pkt)
                    token, side = h[1], h[2].decode()
                    sym = h[4].decode().strip().replace('\x00','')
                    price = h[5] / 10000.0
                    loc = SYM_TO_ID.get(sym, 0)
                    if loc: self.process_order(side, price, h[3], loc, sym, conn, token)
                    buffer = buffer[32:]
        except: pass
        self.active_clients -= 1

    # --- THREADS & UI ---
    def run_directory(self):
        if not self.stress_mode: self.feed_start_event.wait()
        else: time.sleep(1); self.feed_active = True
        while self.running:
            count = 0
            for loc, sym in STOCKS.items():
                self.send_itch(struct.pack(FMT_ITCH_DIR, b'R', loc, 1, time.time_ns(), sym.encode().ljust(8)))
                count += 1
                if count % 100 == 0: time.sleep(0.01)
            time.sleep(5.0 if self.stress_mode else 1.0)

    def run_sim(self):
        if not self.stress_mode: self.feed_start_event.wait()
        sim_ids = list(STOCKS.keys()) if self.stress_mode else list(range(1, 16))
        while self.running:
            for _ in range(50): 
                loc = random.choice(sim_ids)
                CURR_PRICES[loc] += random.uniform(-0.05, 0.05)
                if CURR_PRICES[loc] < 1.0: CURR_PRICES[loc] = 1.0
                center = round(CURR_PRICES[loc], 2)
                side = 'B' if random.random() > 0.5 else 'S'
                price = round(center - 0.05, 2) if side == 'B' else round(center + 0.05, 2)
                self.process_order(side, price, 100, loc, STOCKS[loc])
            time.sleep(0.001 if self.stress_mode else 0.05)

    def run_ui(self):
        sys.stdout.write("\033[?25l")
        last_ops = 0
        while self.running:
            curr = self.ops_counter
            self.tps = curr - last_ops
            last_ops = curr
            out = "\033[H\033[J"
            status = f"{C_GREEN}● LIVE{C_RESET}" if self.feed_active else f"{C_RED}● WAITING{C_RESET}"
            out += f"{C_BOLD}{C_BLUE}╔════════════════════════════════════════════════════════════════╗{C_RESET}\n"
            out += f"{C_BOLD}{C_BLUE}║  TITAN EXCHANGE V17    {status:<20} Clients: {self.active_clients:<2} ║{C_RESET}\n"
            out += f"{C_BOLD}{C_BLUE}╚════════════════════════════════════════════════════════════════╝{C_RESET}\n"
            out += f"{C_BOLD}{'SYMBOL':<8} {'PRICE':<10} {'%CHG':<8} {'VOL':<8} {'SECTOR'}{C_RESET}\n"
            out += f"{C_CYAN}{'-'*64}{C_RESET}\n"
            for sector, ids in SECTORS.items():
                for i in ids:
                    sym, price, start = STOCKS[i], CURR_PRICES[i], START_PRICES[i]
                    pct = ((price - start) / start) * 100
                    color = C_GREEN if pct >= 0 else C_RED
                    out += f"{sym:<8} {price:<10.2f} {color}{('+' if pct>=0 else '')}{pct:.2f}%{C_RESET}   {VOLUMES[i]:<8} {sector}\n"
                out += f"{C_CYAN}{'-'*64}{C_RESET}\n"
            out += f"\n{C_BOLD}>> TRADE LOG (TPS: {self.tps}){C_RESET}\n"
            for log in self.msg_log: out += f"{log}\n"
            sys.stdout.write(out)
            sys.stdout.flush()
            time.sleep(0.1)

    def run_monitor(self):
        print(f"{'TIME':<10} | {'TPS':<10} | {'RX (MB)':<10} | {'CLIENTS'}")
        print("-" * 50)
        last_ops = 0
        while self.running:
            time.sleep(1)
            curr = self.ops_counter
            tps = curr - last_ops
            last_ops = curr
            rx_mb = self.bytes_received / 1024 / 1024
            print(f"{time.strftime('%H:%M:%S'):<10} | {tps:<10} | {rx_mb:<10.2f} | {self.active_clients}")

def run_stress_bot(bid):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try: s.connect(('127.0.0.1', OUCH_PORT))
    except: return
    syms = [STOCKS[i] for i in range(1, 16)]
    # Pre-pack 1000 orders
    orders = []
    for _ in range(1000):
        sym = random.choice(syms).encode().ljust(8)
        pkt = struct.pack(FMT_OUCH_ENTER, b'O', f"B{bid}".encode().ljust(14), b'B', 100, sym, 1500000)
        orders.append(pkt)
    idx = 0
    while True:
        try:
            # Send batch
            s.sendall(b''.join(orders[idx:idx+50]))
            idx = (idx+50)%1000
            # THE FIX: Yield to let Gateway Thread process recv()
            time.sleep(0.0001) 
        except: break

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--stress', action='store_true', help="Run High-Speed Stress Test")
    args = parser.parse_args()
    sys.setrecursionlimit(2000)
    ex = TitanExchange(stress_mode=args.stress)
    
    threading.Thread(target=ex.run_directory, daemon=True).start()
    threading.Thread(target=ex.run_sim, daemon=True).start()
    threading.Thread(target=ex.run_gateway, daemon=True).start()

    if args.stress:
        threading.Thread(target=ex.run_monitor, daemon=True).start()
        time.sleep(2)
        print("🔥 Launching 4 Stress Bots...")
        for i in range(4): threading.Thread(target=run_stress_bot, args=(i,), daemon=True).start()
        try: 
            while True: time.sleep(1)
        except KeyboardInterrupt: pass
    else:
        try: ex.run_ui()
        except KeyboardInterrupt:
            sys.stdout.write("\033[?25h")
            print("\nShutdown.")