import socket
import struct
import time
import threading
import sys
import collections

# CONFIG
OUCH_PORT = 60000
FMT_OUCH_ENTER = '>c14scI8sI'
SZ_OUCH = 32

class DiagnosticExchange:
    def __init__(self):
        self.running = True
        self.lock = threading.Lock()
        
        # Counters
        self.conns = 0
        self.bytes_recv = 0
        self.orders_parsed = 0
        self.acks_sent = 0
        self.acks_blocked = 0

    def run_gateway(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        # s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1) # Optional
        s.bind(('0.0.0.0', OUCH_PORT))
        s.listen()
        print(f"[*] Gateway listening on {OUCH_PORT}")
        
        while self.running:
            conn, addr = s.accept()
            with self.lock: self.conns += 1
            print(f"[+] Connection accepted from {addr}")
            threading.Thread(target=self.handle_client, args=(conn,)).start()

    def handle_client(self, conn):
        # We simulate the Exchange reading logic here
        buffer = b''
        try:
            while self.running:
                data = conn.recv(65536)
                if not data: break
                
                with self.lock: self.bytes_recv += len(data)
                buffer += data
                
                while len(buffer) >= SZ_OUCH:
                    # 1. Parse (Simulate CPU load)
                    pkt = buffer[:SZ_OUCH]
                    h = struct.unpack(FMT_OUCH_ENTER, pkt)
                    
                    with self.lock: self.orders_parsed += 1
                    
                    # 2. Simulate ACK (The suspected DEADLOCK cause)
                    # We send back a dummy Execution Report (27 bytes)
                    # Uncommenting the lines below will likely cause the FREEZE
                    try:
                        # ack = b'E' + b'\x00'*26
                        # conn.send(ack) 
                        # with self.lock: self.acks_sent += 1
                        pass 
                    except BlockingIOError:
                        with self.lock: self.acks_blocked += 1
                    
                    buffer = buffer[SZ_OUCH:]
        except Exception as e:
            print(f"[-] Client Error: {e}")
        finally:
            conn.close()

    def monitor(self):
        print(f"{'TIME':<10} | {'RECV (MB)':<10} | {'ORDERS/s':<10} | {'ACKS SENT':<10}")
        print("-" * 50)
        last_orders = 0
        while self.running:
            time.sleep(1)
            curr = self.orders_parsed
            rate = curr - last_orders
            last_orders = curr
            mb = self.bytes_recv / 1024 / 1024
            print(f"{time.strftime('%H:%M:%S'):<10} | {mb:<10.2f} | {rate:<10} | {self.acks_sent}")

def run_stress_bot(bot_id):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.connect(('127.0.0.1', OUCH_PORT))
    except Exception as e:
        print(f"[!] Bot {bot_id} failed to connect: {e}")
        return

    print(f"[*] Bot {bot_id} connected & blasting...")
    
    # Pre-pack massive payload
    pkt = struct.pack(FMT_OUCH_ENTER, b'O', f"B{bot_id}".encode().ljust(14), b'B', 100, b'AAPL'.ljust(8), 1500000)
    payload = pkt * 100 # Send 100 orders at once
    
    while True:
        try:
            s.sendall(payload)
            # IMPORTANT: We are NOT reading here. 
            # If server sends ACKs, this socket's Recv Buffer fills up -> Server Block -> Deadlock.
        except: break

if __name__ == "__main__":
    ex = DiagnosticExchange()
    
    # 1. Start Server
    threading.Thread(target=ex.run_gateway, daemon=True).start()
    threading.Thread(target=ex.monitor, daemon=True).start()
    
    time.sleep(1)
    
    # 2. Start Bots
    for i in range(2):
        threading.Thread(target=run_stress_bot, args=(i,), daemon=True).start()
        
    try:
        while True: time.sleep(1)
    except KeyboardInterrupt: pass