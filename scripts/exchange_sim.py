import socket
import struct
import time
import random
import threading
import queue

# --- CONFIGURATION ---
MCAST_GRP = '224.0.2.1'
MCAST_PORT = 50000
OUCH_PORT = 60000
INTERFACE_IP = '127.0.0.1'

# ITCH Formats
ITCH_ADD_FMT  = '>cHHQQcI8sI'   # Type 'A'
ITCH_EXEC_FMT = '>cHHQQIQ'      # Type 'E' (Order Executed)
ITCH_DEL_FMT  = '>cHHQQ'        # Type 'D' (Order Delete)

# OUCH Formats
# Type(c), Token(14s), Side(c), Shares(I), Symbol(8s), Price(I)
OUCH_ENTER_FMT = '>c14scI8sI' 
OUCH_MSG_SIZE = 49

# GLOBAL STATE (Shared between threads)
# Orders: { order_id: {'price': 150.00, 'qty': 100, 'side': 'B'} }
active_orders = {}
lock = threading.Lock()
sock_mcast = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
sock_mcast.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 1)

# --- HELPER FUNCTIONS ---
def send_itch_add(locate, order_id, side, symbol, qty, price):
    price_int = int(price * 10000)
    pkt = struct.pack(ITCH_ADD_FMT, b'A', locate, 1, time.time_ns(), order_id, side, qty, symbol.encode(), price_int)
    sock_mcast.sendto(pkt, (MCAST_GRP, MCAST_PORT))
    with lock:
        active_orders[order_id] = {'side': side, 'qty': qty, 'price': price, 'sym': symbol, 'locate': locate}

def send_itch_exec(order_id, exec_qty, match_id):
    # Notify market that order was filled
    pkt = struct.pack(ITCH_EXEC_FMT, b'E', 1, 1, time.time_ns(), order_id, exec_qty, match_id)
    sock_mcast.sendto(pkt, (MCAST_GRP, MCAST_PORT))
    
    with lock:
        if order_id in active_orders:
            # Reduce quantity or remove
            active_orders[order_id]['qty'] -= exec_qty
            if active_orders[order_id]['qty'] <= 0:
                del active_orders[order_id]

def send_itch_delete(order_id):
    pkt = struct.pack(ITCH_DEL_FMT, b'D', 1, 1, time.time_ns(), order_id)
    sock_mcast.sendto(pkt, (MCAST_GRP, MCAST_PORT))
    with lock:
        if order_id in active_orders:
            del active_orders[order_id]

# --- THREAD 1: OUCH SERVER (Receives Your Trades) ---
def ouch_server_thread():
    print(f"🎯 OUCH Gateway Listening on {OUCH_PORT}")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(('127.0.0.1', OUCH_PORT))
        s.listen()
        conn, addr = s.accept()
        with conn:
            print(f"✅ Titan Connected: {addr}")
            while True:
                data = conn.recv(1024)
                if not data: break
                
                # Assume 1 packet = 1 order for simplicity
                if len(data) >= OUCH_MSG_SIZE:
                    try:
                        # Parse the OUCH Order
                        header = struct.unpack(OUCH_ENTER_FMT, data[:32])
                        side = header[2].decode()
                        qty  = header[3]
                        price= header[5] / 10000.0
                        
                        print(f"⚡ [OUCH] RECEIVED: {side} {qty} @ {price:.2f}")

                        # MATCHING LOGIC (The "Exchange")
                        # If Titan Buys, we look for a matching Sell on the book
                        # For simplicity in this demo: We look for the ARB order
                        # We iterate through active orders to find a price match
                        matched_id = None
                        with lock:
                            for oid, info in active_orders.items():
                                # Simple Match: Price crosses
                                if side == 'B' and info['side'] == 'S' and price >= info['price']:
                                    matched_id = oid
                                    break
                                elif side == 'S' and info['side'] == 'B' and price <= info['price']:
                                    matched_id = oid
                                    break
                        
                        if matched_id:
                            print(f"✅ [MATCH] Titan hit Order #{matched_id}!")
                            # 1. Send Execution Update via ITCH (Removes liquidity from C++ Book)
                            send_itch_exec(matched_id, qty, 12345)
                        else:
                            print(f"⚠️ [REJECT] No liquidity found for {price}")

                    except Exception as e:
                        print(f"OUCH Error: {e}")

# --- THREAD 2: MARKET DATA (Generates Arbs) ---
def market_data_thread():
    print(f"🔥 Market Data Active on {MCAST_GRP}:{MCAST_PORT}")
    seq = 1000
    fair_price = 150.00
    
    while True:
        # 1. Cleanup Old Orders
        with lock:
            if len(active_orders) > 20:
                oldest = list(active_orders.keys())[0]
                send_itch_delete(oldest)

        # 2. Random Walk
        fair_price += random.uniform(-0.05, 0.05)
        fair_price = round(max(10.00, fair_price), 2)

        # 3. Create Opportunity (10% Chance)
        if random.random() < 0.10:
            # Create a Sell Order nicely below the Fair Price
            # This creates a crossed market against previous Bids
            ask_price = round(fair_price - 0.10, 2)
            print(f"🚨 [ARB] Opportunity Created: Sell @ {ask_price}")
            
            # Send Sell (Ask)
            send_itch_add(1, seq, b'S', 'AAPL', 100, ask_price)
            seq += 1
            
            # Wait for Titan to snipe it...
            time.sleep(0.5) 
        else:
            # Normal Updates
            bid = round(fair_price - 0.05, 2)
            ask = round(fair_price + 0.05, 2)
            send_itch_add(1, seq, b'B', 'AAPL', 100, bid)
            seq += 1
            send_itch_add(1, seq, b'S', 'AAPL', 100, ask)
            seq += 1
            
        time.sleep(0.1)

def main():
    # Start OUCH Thread
    t1 = threading.Thread(target=ouch_server_thread)
    t1.start()
    
    # Start Market Thread
    t2 = threading.Thread(target=market_data_thread)
    t2.start()

    t1.join()
    t2.join()

if __name__ == "__main__":
    main()