import socket
import struct

MCAST_GRP = '224.0.2.1'
MCAST_PORT = 50000

def run_probe():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    
    # 1. Bind to all interfaces
    sock.bind(('', MCAST_PORT))
    
    # 2. Join Group on ALL interfaces (The "Shotgun" approach)
    mreq = struct.pack("4sl", socket.inet_aton(MCAST_GRP), socket.INADDR_ANY)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)

    print(f"🕵️  PROBE LISTENING on {MCAST_GRP}:{MCAST_PORT}...")
    
    while True:
        try:
            data = sock.recv(1024)
            print(f"✅ DETECTED DATA: {len(data)} bytes")
        except KeyboardInterrupt:
            break

if __name__ == "__main__":
    run_probe()