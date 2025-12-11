import socket
import struct

HOST = '127.0.0.1'
PORT = 60000
# OUCH 'Enter Order' is 49 bytes
MSG_SIZE = 49 
# Struct format: Type(c), Token(14s), Side(c), Shares(I), Symbol(8s), Price(I), ...
FMT = '>c14scI8sI' 

def start_server():
    print(f"🎯 OUCH Gateway Listening on {HOST}:{PORT}")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((HOST, PORT))
        s.listen()
        conn, addr = s.accept()
        with conn:
            print(f"✅ Titan Engine Connected: {addr}")
            while True:
                data = conn.recv(1024)
                if not data: break
                
                # Parse orders
                # Note: In TCP, packets can stick together. 
                # For this simple demo, we assume 1 packet = 1 order.
                if len(data) >= MSG_SIZE:
                    try:
                        # Unpack first few fields
                        header = struct.unpack(FMT, data[:32]) 
                        msg_type = header[0]
                        if msg_type == b'O':
                            token_raw = header[1]
                            token = token_raw.split(b'\x00', 1)[0].decode()
                            
                            side  = header[2].decode()
                            shares= header[3]
                            symbol= header[4].decode().strip()
                            price = header[5] / 10000.0
                            
                            print(f"⚡ [FILLED] {side} {shares} {symbol} @ {price:.2f} (Ref: {token})")
                    except Exception as e:
                        print(f"Parse Error: {e}")

if __name__ == "__main__":
    start_server()