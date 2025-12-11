import mmap
import struct
import time
import curses

def draw_book(stdscr, mm):
    # Hide cursor
    curses.curs_set(0)
    stdscr.nodelay(True)
    
    # Struct format matches C++ BookSnapshot:
    # 5 uint32 bids_p, 5 uint32 bids_q, 5 uint32 asks_p, 5 uint32 asks_q, 1 uint64 seq
    # 5*4 + 5*4 + 5*4 + 5*4 + 8 = 88 bytes
    FMT = '5I5I5I5IQ'
    
    while True:
        # 1. Read Shared Memory
        mm.seek(0)
        buf = mm.read(88)
        data = struct.unpack(FMT, buf)
        
        bid_prices = data[0:5]
        bid_qtys   = data[5:10]
        ask_prices = data[10:15]
        ask_qtys   = data[15:20]
        seq_id     = data[20]

        # 2. Draw UI
        stdscr.clear()
        stdscr.addstr(0, 0, f"TITAN ENGINE LIVE MONITOR | Seq: {seq_id}", curses.A_BOLD)
        stdscr.addstr(2, 0, "   QTY   |   BID   ||   ASK   |   QTY   ")
        stdscr.addstr(3, 0, "---------+---------++---------+---------")

        for i in range(5):
            # Asks (Reverse order for ladder feel? Or standard list)
            # Let's do Standard: Best Ask at top, Best Bid at top
            
            bp = bid_prices[i] / 10000.0
            bq = bid_qtys[i]
            ap = ask_prices[i] / 10000.0
            aq = ask_qtys[i]

            b_str = f"{bp:7.2f}" if bq > 0 else "       "
            a_str = f"{ap:7.2f}" if aq > 0 else "       "
            
            # Color coding
            stdscr.addstr(4+i, 2, f"{bq:5}")
            stdscr.addstr(4+i, 10, b_str, curses.color_pair(1)) # Green
            stdscr.addstr(4+i, 19, "||")
            stdscr.addstr(4+i, 23, a_str, curses.color_pair(2)) # Red
            stdscr.addstr(4+i, 33, f"{aq:5}")

        stdscr.refresh()
        
        # 60 FPS
        time.sleep(0.016)
        
        if stdscr.getch() == ord('q'):
            break

def main():
    # Open Shared Memory
    try:
        f = open("/dev/shm/titan_book", "r+b")
        mm = mmap.mmap(f.fileno(), 88)
    except FileNotFoundError:
        print("Titan Engine not running! (Start C++ first)")
        return

    # Init Curses
    curses.wrapper(draw_book, mm)

if __name__ == "__main__":
    main()