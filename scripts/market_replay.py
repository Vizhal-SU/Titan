import socket
import struct
import time
import random

# Configuration
MCAST_GRP = '224.0.2.1'
MCAST_PORT = 50000
INTERFACE_IP = '127.0.0.1' 

# Formats
ITCH_ADD_FMT  = '>cHHQQcI8sI'
ITCH_DEL_FMT  = '>cHHQQ'
ITCH_EXEC_FMT = '>cHHQQIQ'

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 1)

# STATE: Track active orders so we can delete them validly
# Dict: { order_id: {'side': 'B', 'qty': 100, 'price': 150.00} }
active_orders = {}

def send_add(locate, order_id, side, symbol, qty, price):
    price_int = int(price * 10000)
    pkt = struct.pack(ITCH_ADD_FMT, b'A', locate, 1, time.time_ns(), order_id, side, qty, symbol.encode(), price_int)
    sock.sendto(pkt, (MCAST_GRP, MCAST_PORT))
    
    # Track it
    active_orders[order_id] = {'side': side, 'qty': qty, 'price': price}

def send_delete(order_id):
    pkt = struct.pack(ITCH_DEL_FMT, b'D', 1, 1, time.time_ns(), order_id)
    sock.sendto(pkt, (MCAST_GRP, MCAST_PORT))
    
    if order_id in active_orders:
        del active_orders[order_id]

def main():
    print(f"🔥 Smart Exchange Simulator Active on {MCAST_GRP}:{MCAST_PORT}")
    seq = 1000
    fair_price = 150.00
    
    # Track prices separately
    prices = {1: 150.00, 2: 300.00}
    symbols = {1: 'AAPL', 2: 'MSFT'}
    
    try:
        while True:
            # 1. CLEANUP PHASE: Delete random orders to keep book size manageable
            if len(active_orders) > 10:
                # Pick 3 random orders to kill
                to_delete = random.sample(list(active_orders.keys()), 3)
                for oid in to_delete:
                    send_delete(oid)
                    print(f"   [DEL] Order #{oid} cancelled")

            # 2. RANDOM WALK PRICE
            fair_price += random.uniform(-0.05, 0.05)
            fair_price = round(max(10.00, fair_price), 2)

            # 3. ADD LIQUIDITY
            # Normal Market (No Arb)
            spread = 0.05
            bid_price = round(fair_price - spread, 2)
            ask_price = round(fair_price + spread, 2)

            print(f"   [NORMAL] Fair: {fair_price:.2f} | Bid: {bid_price:.2f} | Ask: {ask_price:.2f}")

            # Send Bid
            send_add(seq, b'B', 'AAPL', 100, bid_price)
            # print(f"   [ADD] Order #{seq} BID {bid_price:.2f} x 100")
            seq += 1
            
            # Send Ask
            send_add(seq, b'S', 'AAPL', 100, ask_price)
            # print(f"   [ADD] Order #{seq} ASK {ask_price:.2f} x 100")
            seq += 1
            
            # 4. OPPORTUNITY PHASE (Rarely)
            if random.random() < 0.05: # 5% chance
                # Create a momentary ARB (Crossed Market)
                arb_bid = ask_price + 0.02 # Bid higher than Ask
                print(f"🚨 [ARB] Creating Opp: Buy {ask_price} vs Sell {arb_bid}")
                send_add(seq, b'B', 'AAPL', 100, arb_bid)
                arb_id = seq
                seq += 1
                
                # ... Wait a tiny bit ...
                time.sleep(0.01)
                
                # ... Then "Market Corrects" (Delete the arb order)
                # This tests if C++ removes the signal!
                send_delete(arb_id)
                print(f"   [CORRECTION] Arb Order #{arb_id} gone")

            time.sleep(2)

    except KeyboardInterrupt:
        print("Shutting down...")

if __name__ == "__main__":
    main()