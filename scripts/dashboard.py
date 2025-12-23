import streamlit as st
import pykx as kx
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from streamlit_lightweight_charts import renderLightweightCharts
import plotly.graph_objects as go

# --- 1. PAGE CONFIGURATION ---
st.set_page_config(
    page_title="Titan HFT Analytics",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- 2. TITAN DARK THEME ---
st.markdown("""
<style>
    /* Main App Background */
    .stApp { background-color: #0b0c0e; color: #e0e0e0; font-family: 'Consolas', monospace; }
    
    /* Metrics Styling (Neon Green) */
    div[data-testid="stMetricValue"] {
        font-family: 'Consolas', monospace;
        font-size: 28px !important;
        color: #00ff00;
        text-shadow: 0 0 8px rgba(0, 255, 0, 0.3);
    }
    div[data-testid="stMetricLabel"] { color: #888; font-size: 14px; }
    
    /* Sidebar Styling */
    section[data-testid="stSidebar"] { background-color: #050505; border-right: 1px solid #222; }
    
    /* Hide Streamlit Header/Footer */
    header {visibility: hidden;}
    .block-container {padding-top: 1rem;}
</style>
""", unsafe_allow_html=True)

# --- 3. KDB+ UTILITIES ---
@st.cache_resource
def get_connection(host, port):
    try: return kx.SyncQConnection(host, port)
    except: return None

def decode_kdb_char(val):
    if isinstance(val, int): return chr(val)
    if isinstance(val, bytes): return val.decode("utf-8")
    return str(val)

def process_data(df):
    if df.empty: return df
    
    # 1. Handle Keyed Tables (reset index if needed)
    if isinstance(df.index, pd.DatetimeIndex):
        df = df.reset_index()

    # 2. Decode Strings
    for col in ['msgType', 'side', 'sym']:
        if col in df.columns: df[col] = df[col].apply(decode_kdb_char)
    
    # 3. Convert Time to Unix Seconds (Required for TradingView)
    if 'time' in df.columns:
        if not pd.api.types.is_datetime64_any_dtype(df['time']):
            df['time'] = pd.to_datetime(df['time'])
        
        # Nanoseconds -> Seconds
        df['unix'] = df['time'].astype(np.int64) // 10**9
        df = df.sort_values('unix')
        
    return df


def get_analytics(conn, sym, history_mins):
    if not conn: return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    try:
        # --- 1. DYNAMIC AGGREGATION LOGIC ---
        # Target ~300 candles on screen for optimal readability
        total_seconds = history_mins * 60
        
        if total_seconds <= 180:      # < 5 mins
            bin_size = "0D00:00:01.000000000" # 1s bars
        elif total_seconds <= 300:   # 5-30 mins
            bin_size = "0D00:00:03.000000000" # 5s bars
        elif total_seconds <= 900:   # 30-60 mins
            bin_size = "0D00:00:10.000000000" # 15s bars
        elif total_seconds <= 1800:  # 1-4 hours
            bin_size = "0D00:00:30.000000000" # 1m bars
        else:
            bin_size = "0D00:01:00.000000000" # 5m bars

        # --- 2. DEFINE QUERY VARIABLES ---
        # We calculate the cutoff time safely in Python to avoid KDB syntax errors
        # But we inject the bin_size directly into the xbar function
        
        # 3. TAPE (Last 100 rows)
        df_raw = process_data(conn(f"0!select [-100] from market where sym=`{sym}").pd())
        
        # 4. VWAP LINE (Dynamic Binning)
        # Note the f-string injection of {bin_size}
        q_vwap = f"""
            limit: {history_mins} * 0D00:01:00.000000000;
            cutoff: .z.p - limit;
            0!select last price, vwap:last (sums price*size)%sums size 
            by time:{bin_size} xbar time from market 
            where sym=`{sym}, time > cutoff
        """
        df_vwap = process_data(conn(q_vwap).pd())
        
        # 5. OHLC BARS (Dynamic Binning)
        q_ohlc = f"""
            limit: {history_mins} * 0D00:01:00.000000000;
            cutoff: .z.p - limit;
            0!select open:first price, high:max price, low:min price, close:last price, volume:sum size 
            by time:{bin_size} xbar time from market 
            where sym=`{sym}, time > cutoff
        """
        df_ohlc = process_data(conn(q_ohlc).pd())
        
        return df_raw, df_ohlc, df_vwap
    except Exception as e:
        print(f"KDB Query Error: {e}")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()




def get_system_health(conn):
    if not conn: return pd.DataFrame({"Component": ["Feed"], "Status": ["OFFLINE"], "Lag": ["-"]})
    try:
        q = """
            now: .z.p;
            m_time: $[count market; exec last time from market; now];
            o_time: $[count orders; exec last time from orders; now];
            m_lag: now - m_time; o_lag: now - o_time;
            m_stat: $[m_lag > 00:00:05.000; `STALE; `OK];
            o_stat: $[o_lag > 00:00:05.000; `STALE; `OK];
            ([] Component:`MarketFeed`OrderGateway; Status:(m_stat; o_stat); Lag:(m_lag; o_lag))
        """
        df = conn(q).pd()
        df['Component'] = df['Component'].apply(decode_kdb_char)
        df['Status'] = df['Status'].apply(decode_kdb_char)
        df['Lag'] = df['Lag'].apply(lambda x: f"{x.total_seconds()*1000:.1f} ms" if x.total_seconds() < 1 else f"{x.total_seconds():.1f} s")
        return df
    except: return pd.DataFrame()

# --- 4. THE LIVE DASHBOARD FRAGMENT ---
@st.fragment(run_every=1)
def render_dashboard(conn, sym, history_mins):
    
    # A. FETCH DATA
    df_raw, df_ohlc, df_vwap = pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    if conn:
        df_raw, df_ohlc, df_vwap = get_analytics(conn, sym, history_mins)
    else:
        # Mock Data Fallback
        times = [datetime.now() - timedelta(seconds=x) for x in range(200)][::-1]
        unix = [int(t.timestamp()) for t in times]
        df_ohlc = pd.DataFrame({'unix': unix, 'open': np.random.normal(150, 0.5, 200).cumsum(), 'volume': np.random.randint(1000, 10000, 200)})
        df_ohlc['close'] = df_ohlc['open'] + np.random.normal(0, 0.2, 200)
        df_ohlc['high'] = df_ohlc[['open', 'close']].max(axis=1) + 0.1
        df_ohlc['low'] = df_ohlc[['open', 'close']].min(axis=1) - 0.1
        df_vwap = pd.DataFrame({'unix': unix, 'vwap': df_ohlc['close'].rolling(20).mean().fillna(method='bfill')})

    # B. KEY METRICS
    last_px = df_ohlc['close'].iloc[-1] if not df_ohlc.empty else 0
    vwap_val = df_vwap['vwap'].iloc[-1] if not df_vwap.empty else 0
    vol_total = df_ohlc['volume'].sum() if not df_ohlc.empty else 0
    
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("LAST PRICE", f"{last_px:.2f}")
    c2.metric("SESSION VWAP", f"{vwap_val:.2f}")
    c3.metric("VOLUME", f"{vol_total:,}")
    c4.metric("STATUS", "LIVE 🟢" if conn else "MOCK 🟠")

    st.markdown("---")

    # C. MAIN CHART (TradingView Engine)
    col_chart, col_depth = st.columns([3, 1])
    
    with col_chart:
        if not df_ohlc.empty:
            # 1. Candle Series
            candle_data = df_ohlc[['unix', 'open', 'high', 'low', 'close']].rename(columns={'unix': 'time'}).to_dict('records')
            
            # 2. Volume Series (Color Coded & Visual Fixes)
            vol_data = []
            for i, row in df_ohlc.iterrows():
                # Green if Up, Red if Down
                color = '#26a69a' if row['close'] >= row['open'] else '#ef5350'
                vol_data.append({'time': row['unix'], 'value': row['volume'], 'color': color})
            
            # 3. VWAP Series
            vwap_data = []
            if not df_vwap.empty and 'unix' in df_vwap.columns:
                vwap_data = df_vwap[['unix', 'vwap']].rename(columns={'unix': 'time', 'vwap': 'value'}).to_dict('records')

            # 4. Chart Configuration
            chartOptions = {
                "layout": {
                    "background": {"type": "Solid", "color": "#0b0c0e"},
                    "textColor": "#d1d4dc",
                },
                "grid": {
                    "vertLines": {"color": "rgba(42, 46, 57, 0.1)"},
                    "horzLines": {"color": "rgba(42, 46, 57, 0.1)"},
                },
                "crosshair": {"mode": 1}, # Magnet Mode
                "timeScale": {
                    "borderColor": "rgba(197, 203, 206, 0.8)",
                    "timeVisible": True,
                    "secondsVisible": True # Show seconds in X-Axis
                },
                "rightPriceScale": {
                    "borderColor": "rgba(197, 203, 206, 0.8)",
                    "scaleMargins": {"top": 0.1, "bottom": 0.25} # Push price up to avoid volume overlap
                },
                "overlayPriceScales": {
                    "vol_scale": {
                         "scaleMargins": {"top": 0.9, "bottom": 0} # Push volume down to bottom 15%
                    }
                },
                "height": 500,
            }

            series = [
                {
                    "type": "Candlestick",
                    "data": candle_data,
                    "options": {
                        "upColor": "#00ff00", "downColor": "#ff0000",
                        "borderVisible": False, "wickUpColor": "#00ff00", "wickDownColor": "#ff0000"
                    }
                },
                {
                    "type": "Line",
                    "data": vwap_data,
                    "options": {
                        "color": "#ff9f1c", "lineWidth": 2, "priceLineVisible": False
                    }
                },
                {
                    "type": "Histogram",
                    "data": vol_data,
                    "options": {
                        "priceFormat": {"type": "volume"},
                        "priceScaleId": "vol_scale" # Bind to separate scale
                    }
                }
            ]
            renderLightweightCharts([{"chart": chartOptions, "series": series}], "main_chart")
        else:
            st.info("Waiting for market data stream...")

    # D. DEPTH & HEALTH PANELS
    with col_depth:
        st.markdown("###### 📊 DEPTH PROFILE")
        if last_px > 0:
            # Simulated Depth (Can be connected to quote table later)
            depth_price = np.linspace(last_px*0.999, last_px*1.001, 15)
            depth_vol = np.random.randint(1000, 8000, 15)
            colors = ['#ef5350' if p > last_px else '#26a69a' for p in depth_price]
            
            fig = go.Figure(go.Bar(x=depth_vol, y=depth_price, orientation='h', marker_color=colors))
            fig.update_layout(
                template="plotly_dark", height=250, margin=dict(l=0, r=0, t=0, b=0),
                xaxis=dict(showticklabels=False), yaxis=dict(side='right', showgrid=False),
                paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                uirevision='constant', # Prevents flicker
                bargap=0.1
            )
            st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

        st.markdown("###### 📡 SYSTEM HEALTH")
        df_health = get_system_health(conn)
        if not df_health.empty:
            def color_status(val): return f'color: {"#00ff00" if val == "OK" else "#ff4b4b"}'
            st.dataframe(df_health.style.map(color_status, subset=['Status']), hide_index=True, use_container_width=True)

    # E. LIVE TAPE
    st.markdown("---")
    t1, t2 = st.tabs(["📜 LIVE TAPE", "💻 KDB+ SOURCE"])
    with t1:
        if not df_raw.empty:
            st.dataframe(df_raw[['time', 'price', 'size', 'side', 'msgType']].sort_values('time', ascending=False).head(20), use_container_width=True, hide_index=True)
    with t2:
        st.code(f"select from market where sym=`{sym}", language="q")

# --- 5. MAIN ENTRY POINT ---
def main():
    # SIDEBAR (Static)
    with st.sidebar:
        st.header("🔧 CONFIGURATION")
        host = st.text_input("KDB Host", "localhost")
        port = st.number_input("KDB Port", 5001)
        st.divider()
        sym = st.text_input("Ticker Symbol", "AAPL").upper()
        # CHANGED: Slider controls Time (Minutes) instead of Rows
        history_mins = st.slider("Chart History (Mins)", 1, 60, 15)
        st.caption("Mode: Zero-Flicker (Fragment)")

    # Connect
    conn = get_connection(host, port)
    # st.write(f"DEBUG: Showing last {history_mins} minutes")
    # Static Header
    st.markdown(f"### TITAN <span style='color:#ff4b4b'>ANALYTICS</span>", unsafe_allow_html=True)
    
    # Render Live Fragment
    render_dashboard(conn, sym, history_mins)

if __name__ == "__main__":
    main()