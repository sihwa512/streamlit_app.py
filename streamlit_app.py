import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
import gspread
from google.oauth2.service_account import Credentials

# --- 頁面設定 ---
st.set_page_config(page_title="綜合退休戰情室 V70.8", layout="wide")

# --- 1. Google Sheets 連接邏輯 ---
GS_FILENAME = "Retirement_Cloud_Data"
GS_SHEETNAME = "Stocks"

def get_gspread_client():
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    # 這裡會讀取您在 Secrets 設定的內容
    creds_dict = st.secrets["gcp_service_account"]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
    return gspread.authorize(creds)

def load_data_from_gs():
    try:
        client = get_gspread_client()
        sh = client.open(GS_FILENAME).worksheet(GS_SHEETNAME)
        df = pd.DataFrame(sh.get_all_records())
        stocks = {}
        if not df.empty:
            for _, row in df.iterrows():
                sid = str(row['id']).upper().strip()
                stocks[sid] = {"sh": float(row['sh']), "co": float(row['co'])}
        else:
            stocks = {"CASH": {"sh": 0.0, "co": 1.0}}
        return stocks
    except Exception as e:
        st.error(f"❌ Google Sheets 連線失敗: {e}")
        return {"CASH": {"sh": 0.0, "co": 1.0}}

def save_data_to_gs(stocks):
    try:
        client = get_gspread_client()
        sh = client.open(GS_FILENAME).worksheet(GS_SHEETNAME)
        data_to_save = [["id", "sh", "co"]]
        for sid, v in stocks.items():
            data_to_save.append([sid, v['sh'], v['co']])
        sh.clear()
        sh.update("A1", data_to_save)
        st.toast("✅ 數據同步成功")
    except Exception as e:
        st.error(f"❌ 雲端存檔失敗: {e}")

# --- 2. 靈魂 CSS ---
st.markdown("""
    <style>
    .stApp { background-color: #0f111a; color: #e0e0e0; }
    [data-testid="stMetric"] { background: linear-gradient(145deg, #1b1e2e, #161926); border: 1px solid #333; border-radius: 15px; padding: 15px !important; }
    h1, h2, h3 { color: #00d4ff !important; font-weight: 700 !important; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. 強化報價抓取 ---
def fetch_price(symbol):
    if symbol == "CASH": return 1.0, "現金部位"
    # 嘗試不同後綴
    for suf in [".TW", ".TWO", ""]:
        try:
            t = yf.Ticker(f"{symbol}{suf}")
            p = t.fast_info.last_price
            if p > 0: return p, t.info.get('shortName', symbol)
            # 歷史收盤備案
            h = t.history(period="1d")
            if not h.empty: return h['Close'].iloc[-1], t.info.get('shortName', symbol)
        except: continue
    return 0.0, symbol

# --- 4. 資料初始化 ---
if 'stocks' not in st.session_state:
    st.session_state.stocks = load_data_from_gs()
if 'principal' not in st.session_state:
    st.session_state.principal = 0.0

# 計算
total_mkt = 0.0
s_val, l_val, b_val, c_val = 0.0, 0.0, 0.0, 0.0
processed_rows = []

for sid, v in st.session_state.stocks.items():
    p, name = fetch_price(sid)
    m = v['sh'] * p
    total_mkt += m
    if sid == "CASH": c_val += m
    elif "B" in sid: b_val += m
    elif "L" in sid: l_val += m
    else: s_val += m
    processed_rows.append({"標的": sid, "名稱": name, "現價": f"{p:,.2f}", "股數": f"{v['sh']:,.0f}", "市值": round(m,0)})

# --- 5. 介面呈現 ---
st.title("📊 綜合退休戰情室 V70.8 Cloud")

col1, col2, col3 = st.columns(3)
with col1: st.metric("資產總市值", f"${total_mkt:,.0f}")
with col2: st.session_state.principal = st.number_input("投入總本金", value=float(st.session_state.principal))
with col3:
    true_pnl = total_mkt - st.session_state.principal
    pnl_pct = (true_pnl / st.session_state.principal * 100) if st.session_state.principal > 0 else 0
    st.metric("真實累積總損益", f"${true_pnl:,.0f}", f"{pnl_pct:.2f}%")

st.divider()

# 現況方塊樣式 (顏色金額大小同步)
def card_html(label, color, pct, val):
    return f"<div style='text-align:center; padding:15px; background:#161926; border:1px solid {color}44; border-radius:12px;'><small style='color:#aaa;'>{label}</small><br><b style='color:{color}; font-size:26px;'>{pct:.1f}%</b><br><b style='color:{color}; font-size:22px;'>${val:,.0f}</b></div>"

c1, c2, c3 = st.columns(3)
with c1: st.markdown(card_html("現況 股票", "#00d4ff", (s_val/total_mkt*100 if total_mkt>0 else 0), s_val), unsafe_allow_html=True)
with c2: st.markdown(card_html("現況 槓桿", "#bd93f9", (l_val/total_mkt*100 if total_mkt>0 else 0), l_val), unsafe_allow_html=True)
with c3: st.markdown(card_html("現況 類現金", "#00ff88", ((b_val+c_val)/total_mkt*100 if total_mkt>0 else 0), (b_val+c_val)), unsafe_allow_html=True)

st.write("")
t1, t2, t3 = st.columns(3)
with t1: ts = st.number_input("目標 股票 %", value=40)
with t2: tl = st.number_input("目標 槓桿 %", value=30)
with t3: 
    t_safe = 100 - ts - tl
    st.markdown(f"<div style='text-align:center;'><small style='color:#aaa;'>目標 類現金</small><br><b style='color:#00ff88; font-size:24px;'>{t_safe}%</b><br><b style='color:#00ff88; font-size:20px;'>目標: ${total_mkt * t_safe/100:,.0f}</b></div>", unsafe_allow_html=True)

st.divider()

# 圓餅圖 (維持細分)
cp, ct = st.columns([1, 1.5])
with cp:
    fig = go.Figure(data=[go.Pie(labels=['股票', '槓桿', '債券', '現金'], values=[s_val, l_val, b_val, c_val], marker=dict(colors=['#00d4ff', '#bd93f9', '#ff9f1c', '#00ff88']), hole=.4)])
    fig.update_layout(template="plotly_dark", margin=dict(t=0,b=0,l=0,r=0))
    st.plotly_chart(fig, use_container_width=True)
with ct:
    st.subheader("📋 目前標的庫存")
    st.dataframe(pd.DataFrame(processed_rows), use_container_width=True, hide_index=True)

with st.sidebar:
    st.header("⚙️ 雲端同步")
    if st.button("🚀 強制刷新數據"):
        st.cache_data.clear()
        st.session_state.stocks = load_data_from_gs()
        st.rerun()
    st.divider()
    add_id = st.text_input("新增代號").upper().strip()
    if st.button("➕ 新增入池"):
        if add_id:
            st.session_state.stocks[add_id] = {"sh": 0.0, "co": 0.0}
            save_data_to_gs(st.session_state.stocks)
            st.rerun()
