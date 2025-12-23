import streamlit as st
import pykx as kx
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import numpy as np
from datetime import datetime, timedelta

# --- 1. PAGE CONFIGURATION ---
st.set_page_config(
    page_title="Titan HFT Analytics",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- 2. CUSTOM CSS (Dark Terminal Theme) ---
st.markdown("""
<style>
    /* Main Background & Fonts */
    .stApp { background-color: #000000; color: #e0e0e0; font-family: 'Consolas', monospace; }
    
    /* Metrics Styling */
    div[data-testid="stMetricValue"] {
        font-family: 'Consolas', monospace;
        font-size: 26px !important;
        color: #00ff00; /* HFT Green */
        text-shadow: 0 0 5px rgba(0, 255, 0, 0.4);
    }
    div[data-testid="stMetricLabel"] {
        color: #888;
        font-size: 14px;
    }
    
    /* Sidebar */
    section[data-testid="stSidebar"] {
        background-color: #111;
        border-right: 1px solid #333;
    }
    
    /* Tables */
    .dataframe { 
        font-family: 'Consolas', monospace; 
        font-size: 12px; 
    }
</style>
""", unsafe_allow_html=True)

# --- 3. BACKEND CONNECTION & UTILS ---

@st.cache_resource
def get_connection(host, port):
    """Establishes cached connection to KDB+."""
    try:
        conn = kx.SyncQConnection(host, port)
        return conn
    except Exception:
        return None

def decode_kdb_char(val):
    """Robustly decodes KDB char/byte types to string."""
    if isinstance(val, int): return chr(val)
    if isinstance(val, bytes): return val.decode("utf-8")
    return str(val)

def process_data(df):
    """Clean raw KDB data for Python usage."""
    if df.empty: return df
    
    # Decode char columns if they exist
    for col in ['msgType', 'side', 'sym']:
        if col in df.columns:
            df[col] = df[col].apply(decode_kdb_char)
            
    # Ensure time is datetime64
    if 'time' in df.columns and not pd.api.types.is_datetime64_any_dtype(df['time']):
        df['time'] = pd.to_datetime(df['time'])
        
    return df

def get_system_health(conn):
    """
    Calculates REAL latency by comparing server time (.z.p) 
    vs the last received timestamp in the tables.
    """
    if conn is None:
        return pd.DataFrame({
            "Component": ["Feed Handler", "KDB+ TP", "RDB"],
            "Status": ["OFFLINE", "OFFLINE", "OFFLINE"],
            "Lag": ["-", "-", "-"]
        })

    try:
        # Q Query: Get last timestamp from both tables and compare to .z.p
        # We use 'exec' to get raw values, not tables
        q_health = """
            / 1. Capture current time
            now: .z.p;
            
            / 2. Get last time from tables (handle empty tables safely)
            m_time: $[count market; exec last time from market; now - 1D];
            o_time: $[count orders; exec last time from orders; now - 1D];
            
            / 3. Calculate Lag
            m_lag: now - m_time;
            o_lag: now - o_time;
            
            / 4. Determine Status (Threshold: 5 seconds)
            m_stat: $[m_lag > 00:00:05.000; `STALE; `OK];
            o_stat: $[o_lag > 00:00:05.000; `STALE; `OK];
            
            / 5. Return Table
            ([] 
                Component:`MarketFeed`OrderGateway; 
                Status:(m_stat; o_stat); 
                Lag:(m_lag; o_lag)
            )
        """
        df = conn(q_health).pd()
        
        # Formatting
        df['Component'] = df['Component'].apply(lambda x: str(x).replace("b'", "").replace("'", ""))
        df['Status'] = df['Status'].apply(lambda x: str(x).replace("b'", "").replace("'", ""))
        
        # Pretty print Latency
        def fmt_lag(td):
            # If lag is massive (e.g. > 1 day because table is empty), show N/A
            if td.days > 0: return "N/A"
            
            total_micros = td.microseconds + (td.seconds * 1000000)
            if total_micros < 1000: 
                return f"{total_micros} µs"
            elif total_micros < 1000000:
                return f"{total_micros / 1000:.1f} ms"
            else:
                return f"{total_micros / 1000000:.1f} s"
            
        df['Lag'] = df['Lag'].apply(fmt_lag)
        
        return df

    except Exception as e:
        return pd.DataFrame({"Component": ["System Error"], "Status": ["FAIL"], "Lag": [str(e)]})

def get_analytics(conn, sym, lookback_rows=1000):
    """
    PERFORMS SERVER-SIDE ANALYTICS IN KDB+
    1. Raw Ticks: Last N trades.
    2. OHLC: 1-Minute aggregated bars (using xbar).
    3. VWAP: Running Volume Weighted Avg Price (vectorized).
    """
    if conn is None: return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    try:
        # 1. RAW TICKS (For Tape)
        q_raw = f"0!select [-{lookback_rows}] from market where sym=`{sym}"
        df_raw = process_data(conn(q_raw).pd())

        # 2. OHLC BARS (Server-side Aggregation)
        # Uses 'xbar' to bucket time by 1 minute (0D00:01:00)
        q_ohlc = f"""
            0!select 
                open:first price, 
                high:max price, 
                low:min price, 
                close:last price, 
                volume:sum size 
            by time:0D00:01:00 xbar time 
            from market 
            where sym=`{sym}
        """
        df_ohlc = process_data(conn(q_ohlc).pd())

        # 3. RUNNING VWAP (Vectorized Calculation)
        # Calculates (Cumulative Price * Size) / (Cumulative Size)
        q_vwap = f"""
            select time, price, 
            vwap:(sums price*size) % sums size 
            from market 
            where sym=`{sym}, price > 0.001
        """
        df_vwap = process_data(conn(q_vwap).pd())
        
        return df_raw, df_ohlc, df_vwap

    except Exception as e:
        st.toast(f"KDB Query Error: {e}", icon="⚠️")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

# --- 4. MAIN APPLICATION ---

def main():
    # --- SIDEBAR CONFIGURATION ---
    with st.sidebar:
        st.header("🔧 CONFIGURATION")
        
        # Connection Params
        kdb_host = st.text_input("KDB Host", "localhost")
        kdb_port = st.number_input("KDB Port", 5001, step=1)
        
        st.divider()
        
        # User Inputs
        selected_sym = st.text_input("Ticker Symbol", "AAPL").upper()
        lookback = st.slider("Tape Lookback (Rows)", 100, 5000, 500)
        
        st.divider()
        
        if st.button("CONNECT & REFRESH", type="primary"):
            st.rerun()

    # --- CONNECTION HANDLING ---
    conn = get_connection(kdb_host, kdb_port)
    
    # Header Status
    c1, c2 = st.columns([3, 1])
    with c1:
        st.markdown(f"<h1 style='margin:0;'>TITAN <span style='color:#ff4b4b'>ANALYTICS</span></h1>", unsafe_allow_html=True)
        st.caption(f"Real-time microstructure analysis for {selected_sym}")
    with c2:
        if conn:
            st.success(f"🟢 CONNECTED: {kdb_host}:{kdb_port}")
        else:
            st.error("🔴 DISCONNECTED (Using Mock Data)")

    # --- DATA FETCHING ---
    if conn:
        df_raw, df_ohlc, df_vwap = get_analytics(conn, selected_sym, lookback)
    else:
        # Mock Data Generator for Offline Testing
        times = [datetime.now() - timedelta(minutes=x) for x in range(100)][::-1]
        df_vwap = pd.DataFrame({
            'time': times,
            'price': np.random.normal(150, 1, 100).cumsum(),
            'vwap': np.random.normal(150, 1, 100).cumsum()
        })
        df_ohlc = pd.DataFrame({
            'time': times,
            'volume': np.random.randint(100, 5000, 100)
        })
        df_raw = pd.DataFrame({
            'time': times, 'sym': [selected_sym]*100, 
            'price': df_vwap['price'], 'size': df_ohlc['volume'], 
            'side': ['B']*50 + ['S']*50, 'msgType': ['T']*100
        })

    # --- METRICS ROW ---
    last_price = 0.0

    if not df_vwap.empty:
        last_price = df_vwap['price'].iloc[-1]
        start_price = df_vwap['price'].iloc[0]
        pct_change = ((last_price - start_price) / start_price) * 100
        vwap_val = df_vwap['vwap'].iloc[-1]
        total_vol = df_ohlc['volume'].sum() if not df_ohlc.empty else 0
        
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("LAST PRICE", f"{last_price:.2f}", f"{pct_change:.2f}%")
        m2.metric("SESSION VWAP", f"{vwap_val:.2f}", delta_color="off")
        m3.metric("TOTAL VOLUME", f"{total_vol:,}")
        m4.metric("ALGO LATENCY", "14 µs") # Placeholder for now
    
    st.markdown("---")

    # --- MAIN CHART (Price vs VWAP + Volume) ---
    col_chart, col_depth = st.columns([3, 1])

    with col_chart:
        if not df_vwap.empty:
            fig = make_subplots(specs=[[{"secondary_y": True}]])

            # 1. Raw Price (Thin Grey)
            fig.add_trace(go.Scatter(
                x=df_vwap['time'], y=df_vwap['price'],
                name='Market Px', line=dict(color='#666', width=1),
                opacity=0.6
            ), secondary_y=False)

            # 2. VWAP (Thick Orange - The Benchmark)
            fig.add_trace(go.Scatter(
                x=df_vwap['time'], y=df_vwap['vwap'],
                name='VWAP', line=dict(color='#ff9f1c', width=2)
            ), secondary_y=False)

            # 3. Volume (Green Bars)
            if not df_ohlc.empty:
                fig.add_trace(go.Bar(
                    x=df_ohlc['time'], y=df_ohlc['volume'],
                    name='Volume', marker_color='rgba(46, 204, 113, 0.2)'
                ), secondary_y=True)

            fig.update_layout(
                title=f"<b>{selected_sym}</b> Market Microstructure",
                template="plotly_dark",
                height=500,
                hovermode="x unified",
                legend=dict(orientation="h", y=1.02, x=0),
                margin=dict(l=0, r=0, t=30, b=0),
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(15,15,15,1)'
            )

            t_min = df_vwap['time'].min()
            t_max = df_vwap['time'].max()
            # Add 5% buffer so points aren't cut off
            buffer = (t_max - t_min) * 0.05

            # Hiding gridlines for cleaner look
            fig.update_xaxes(range = [t_min, t_max + buffer], showgrid=False)
            fig.update_yaxes(showgrid=True, gridcolor='#222')
            
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Waiting for data stream...")

    # --- SIDE PANEL (Depth & Info) ---
    with col_depth:
        st.markdown("###### 📊 DEPTH PROFILE")
        
        if last_price > 0:
            # Simulated Depth (Since 'market' table is usually L1/Trades)
            # In a real setup, you'd query a 'quote' table here
            depth_price = np.linspace(last_price*0.995, last_price*1.005, 15)
            depth_vol = np.random.randint(500, 5000, 15)
            colors = ['#ff4b4b' if p > last_price else '#00ff00' for p in depth_price]
            
            fig_depth = go.Figure(go.Bar(
                x=depth_vol, y=depth_price,
                orientation='h', marker_color=colors
            ))
            fig_depth.update_layout(
                template="plotly_dark",
                height=300,
                margin=dict(l=0, r=0, t=0, b=0),
                xaxis=dict(showticklabels=False),
                yaxis=dict(side='right', showgrid=False),
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)'
            )
            st.plotly_chart(fig_depth, use_container_width=True)
        
        else:
            st.write("No price data for depth chart")
        
        st.markdown("###### 📡 SYSTEM HEALTH")

        # 1. CALL THE FUNCTION (Pass your connection object)
        df_health = get_system_health(conn)

        # 2. DEFINE STYLING (Green for OK, Red for STALE/OFFLINE)
        def color_status(val):
            color = '#00ff00' if val == 'OK' else '#ff4b4b'
            return f'color: {color}'

        # 3. DISPLAY THE DATAFRAME WITH STYLES
        st.dataframe(
            df_health.style.map(color_status, subset=['Status']), 
            hide_index=True,
            use_container_width=True
        )

    # --- BOTTOM: RAW DATA & CODE ---
    st.markdown("---")
    t1, t2 = st.tabs(["📜 LIVE TAPE", "💻 KDB+ SOURCE CODE"])
    
    with t1:
        if not df_raw.empty:
            st.dataframe(
                df_raw.sort_values(by='time', ascending=False).head(50),
                use_container_width=True, hide_index=True
            )
        else:
            st.write("No trade data available.")

    with t2:
        st.markdown("#### Server-Side Q Analytics Used:")
        st.code(f"""
/ 1. OHLC Aggregation (xbar)
select open:first price, high:max price, close:last price, volume:sum size 
by time:0D00:01:00 xbar time from market where sym=`{selected_sym}

/ 2. Vectorized VWAP Calculation
select time, price, vwap:(sums price*size)%sums size 
from market where sym=`{selected_sym}
        """, language="q")

if __name__ == "__main__":
    main()