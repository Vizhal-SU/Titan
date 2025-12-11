import struct

# Matches the C++ struct alignment
# Q = uint64, I = uint32, c = char
FMT = 'QQIIcc' 
SIZE = struct.calcsize(FMT)

with open('../Titan/trades.bin', 'rb') as f:
    while chunk := f.read(SIZE):
        data = struct.unpack(FMT, chunk)
        # 0=Time, 1=ID, 2=Price, 3=Qty, 4=Side, 5=Action
        print(f"[{data[5].decode()}] Order {data[1]} | {data[4].decode()} {data[3]} @ {data[2]/10000.0}")