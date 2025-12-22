import mmap
import struct
import time
import curses
import os

def draw_portfolio(stdscr, mm):
    curses.curs_set(0)
    stdscr.nodelay(True)
    curses.start_color()
    curses.use_default_colors()

    # Colors
    curses.init_pair(1, curses.COLOR_GREEN, -1)   # Profit
    curses.init_pair(2, curses.COLOR_RED, -1)     # Loss
    curses.init_pair(3, curses.COLOR_CYAN, -1)    # Header
    curses.init_pair(4, curses.COLOR_YELLOW, -1)  # Label

    # --- PROTOCOL ---
    # Header: Q (Seq), d (GlobalPnL), I (GlobalTrades), I (Count) = 8+8+4+4 = 24 bytes.
    # Entry:  8s (Sym), i (Qty), 4x (Pad), d (PnL), d (AvgPx), I (Trades), 4x (Pad) 
    #         = 8+4+4+8+8+4+4 = 40 bytes per stock.
    
    HEADER_FMT = 'QdII' 
    ENTRY_FMT  = '8si4xddI4x'
    
    HEADER_SIZE = struct.calcsize(HEADER_FMT) # 24
    ENTRY_SIZE  = struct.calcsize(ENTRY_FMT)  # 40

    last_seq = 0
    
    while True:
        mm.seek(0)
        
        # 1. READ HEADER
        try:
            buf = mm.read(HEADER_SIZE)
            header = struct.unpack(HEADER_FMT, buf)
            
            seq_id = header[0]
            global_pnl = header[1]
            global_trades = header[2]
            count = header[3]
        except:
            continue

        # 2. READ ENTRIES
        positions = []
        mm.seek(HEADER_SIZE) # Jump past header
        
        for _ in range(min(count, 64)): # Read up to 64 items
            buf = mm.read(ENTRY_SIZE)
            e = struct.unpack(ENTRY_FMT, buf)
            
            sym = e[0].decode().strip()
            qty = e[1]
            pnl = e[2]
            trades = e[4]
            positions.append( {'sym': sym, 'qty': qty, 'pnl': pnl, 'trades': trades} )

        # 3. DRAW UI
        stdscr.erase()
        
        # Global Header
        status = " LIVE " if seq_id != last_seq else " IDLE "
        last_seq = seq_id
        
        stdscr.addstr(0, 0, " TITAN PORTFOLIO MONITOR ", curses.A_BOLD)
        stdscr.addstr(0, 30, status, curses.color_pair(3))
        
        stdscr.addstr(2, 2, f"TOTAL P&L: ${global_pnl:,.2f}", curses.color_pair(1) if global_pnl >=0 else curses.color_pair(2))
        stdscr.addstr(2, 30, f"TOTAL TRADES: {global_trades}")

        # Table Header
        stdscr.addstr(4, 2, "SYMBOL     POS       P&L       TRADES", curses.color_pair(4))
        stdscr.hline(5, 2, curses.ACS_HLINE, 40)

        # Table Rows
        row = 6
        positions.sort(key=lambda x: x['pnl'], reverse=True) 
        
        # 1. GET SCREEN DIMENSIONS
        height, width = stdscr.getmaxyx()

        for p in positions:
            if p['trades'] == 0 and p['qty'] == 0: continue 
            
            # 2. SAFETY CHECK: STOP DRAWING IF WE HIT THE BOTTOM
            if row >= height - 1:
                stdscr.addstr(row, 2, "... (Resize window for more)", curses.color_pair(4))
                break

            sym_str = f"{p['sym']:<8}"
            qty_str = f"{p['qty']:<8}"
            pnl_str = f"${p['pnl']:<8.2f}"
            trd_str = f"{p['trades']:<6}"
            
            col = curses.color_pair(1) if p['pnl'] >= 0 else curses.color_pair(2)
            
            stdscr.addstr(row, 2, sym_str, curses.A_BOLD)
            stdscr.addstr(row, 13, qty_str)
            stdscr.addstr(row, 23, pnl_str, col)
            stdscr.addstr(row, 34, trd_str)
            
            row += 1

        stdscr.refresh()
        time.sleep(0.1)


def main():
    SHM_PATH = "/dev/shm/titan_book"
    if not os.path.exists(SHM_PATH): return
    
    file_size = os.path.getsize(SHM_PATH)
    with open(SHM_PATH, "r+b") as f:
        mm = mmap.mmap(f.fileno(), file_size)
        curses.wrapper(draw_portfolio, mm)

if __name__ == "__main__":
    main()