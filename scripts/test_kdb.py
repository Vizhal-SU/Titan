import pykx as kx
import pandas as pd
import time
from datetime import datetime

# --- CONFIGURATION ---
HOST = 'localhost'
PORT = 5001
TABLE_NAME = 'orders'  # Change this to a table that exists in your DB (e.g., 'quote', 'order')
POLL_INTERVAL = 2     # Seconds between pulls

def test_live_feed():
    print(f"⚡ Starting KDB+ Live Printer...")
    print(f"   Target: {HOST}:{PORT} | Table: {TABLE_NAME}")
    print("-" * 60)

    conn = None

    while True:
        try:
            # 1. CONNECT (Auto-reconnect logic)
            if conn is None:
                try:
                    conn = kx.SyncQConnection(HOST, PORT)
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ Connected to KDB+")
                except Exception as e:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] ⏳ Waiting for KDB+ server... ({e})")
                    time.sleep(POLL_INTERVAL)
                    continue

            # 2. QUERY (Get last 3 rows for testing)
            # We use '0!' to unkey the table ensuring it converts to a flat DataFrame easily
            query = f"0!select [-3] from {TABLE_NAME}"
            
            # 3. EXECUTE
            # This is where your previous code failed. 
            # PyKX safely wraps this, and .pd() handles the conversion.
            res = conn(query)
            
            # 4. CONVERT & PRINT
            # If the table is empty or doesn't exist, PyKX might return a different type.
            # We check if it's a table before converting.
            if isinstance(res, kx.Table):
                df = res.pd()
                
                if not df.empty:
                    # Clear line/formatting for cleaner output
                    print(f"\n--- 📥 Received {len(df)} rows at {datetime.now().strftime('%H:%M:%S')} ---")
                    print(df.to_string(index=False)) 
                else:
                    print(".", end="", flush=True) # Heartbeat for empty table
            else:
                # This catches if 'res' is not a table (e.g. an atom or list error)
                print(f"\n⚠️ Unexpected response type: {type(res)}")

        except kx.QError as e:
            print(f"\n❌ KDB Query Error: {e}")
            # Often means table doesn't exist. Don't crash, just wait.
            
        except OSError:
            print("\n❌ Connection Lost. Reconnecting...")
            conn = None # Trigger reconnection in next loop
            
        except Exception as e:
            print(f"\n🚨 Python Error: {e}")
            # This catches the 'bool has no attribute...' if it ever happened again (unlikely with PyKX)

        # 5. WAIT
        time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    try:
        test_live_feed()
    except KeyboardInterrupt:
        print("\n\n🛑 User stopped script.")