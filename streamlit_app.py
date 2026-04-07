import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
import gspread
from google.oauth2.service_account import Credentials
import re

# --- 1. 頁面基本設定 ---
st.set_page_config(page_title="綜合退休戰情室 V72.1", layout="wide")

# --- 2. 核心雲端連線邏輯 (加入強效清潔補丁) ---
def get_gspread_client():
    try:
        scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds_info = dict(st.secrets["gcp_service_account"])
        
        if "private_key" in creds_info:
            pk = creds_info["private_key"]
            # 🌟 強效清潔：移除所有隱形字元，並標準化換行符號
            pk = pk.replace("\\n", "\n")
            pk = re.sub(r'[^\x20-\x7E\n]', '', pk) # 移除所有非標準 ASCII 字元
            if "-----BEGIN PRIVATE KEY-----" not in pk:
                pk = "-----BEGIN PRIVATE KEY-----\n" + pk + "\n-----END PRIVATE KEY-----"
            creds_info["private_key"] = pk
            
        creds = Credentials.from_service_account_info(creds_info, scopes=scope)
        return gspread.authorize(creds)
    except Exception as e:
        st.sidebar.error(f"❌ 授權失敗: {str(e)[:50]}...") # 縮短錯誤訊息
        return None

def load_data_from_gs():
    client = get_gspread_client()
    if not client: return {"CASH": {"sh": 0.0, "co": 1.0}}, 0.0
    try:
        doc = client.open("Retirement_Cloud_Data")
        ws_stocks = doc.worksheet("Stocks")
        stock_data = ws_stocks.get_all_records()
        stocks = {str(r['id']).upper().strip(): {"sh": float(r['sh']), "co": float(r['co'])} for r in stock_data} if stock_data else {"CASH": {"sh": 0.0, "co": 1.0}}
        try:
            ws_set = doc.worksheet("Settings")
            set_data = ws_set.get_all_records()
            principal = float(next((i['value'] for i in set_data if i['key'] == 'principal'), 0.0))
        except: principal = 0.0
        return stocks, principal
    except: return {"CASH": {"sh": 0.0, "co": 1.0}}, 0.0

def save_data_to_gs(stocks, principal):
    client = get_gspread_client()
    if not client: return
    try:
        doc = client.open("Retirement_Cloud_Data")
        ws_stocks = doc.worksheet("Stocks")
        stock_list = [["id", "sh", "co"]] + [[sid, v['sh'], v['co']] for sid, v in stocks.items()]
        ws_stocks.clear()
        ws_stocks.update(values=stock_list, range_name="A1")
        try:
            ws_set = doc.worksheet("Settings")
            ws_set.clear()
            ws_set.update(values=[["key", "value"], ["principal", principal]], range_name="A1")
        except: pass
        st.toast("🚀 雲端同步成功！")
    except Exception as e: st.error(f"同步失敗: {e}")

# --- 3. 樣式與報價 (省略重複部分，保持完整性) ---
st.markdown("<style>.stApp { background-color: #0d1117; color: #c9d1d9; }[data-testid='stMetricValue'] > div { color: #00d4ff !important; font-size: 2.2rem !important; font-weight: bold !important; }</style>", unsafe_allow_html=True)

@st.cache_data(ttl=600)
def fetch_price(symbol):
    if symbol == "CASH": return 1.0, "閒置現金"
    for suf in [".TW", ".TWO", ""]:
        try:
            t = yf.Ticker(f"{symbol}{suf}")
            p = t.fast_info.last_price
            if p > 0: return float(p), symbol
            h = t.history(period="1d")
            if not h.empty: return float(h['Close'].iloc[-1]), symbol
        except: continue
    return 0.0, symbol

# --- 4. 數據與介面 ---
if 'stocks' not in st.session_state:
    st.session_state.stocks, st.session_state.principal = load_data_from_gs()

total_mkt, s_val, l_val, b_val, c_val = 0.0, 0.0, 0.0, 0.0, 0.0
rows = []
for sid, v in st.session_state.stocks.items():
    p, name = fetch_price(sid)
    m = v['sh'] * p
    total_mkt += m
    if sid == "CASH": c_val += m
    elif "B" in sid: b_val += m
    elif "L" in sid: l_val += m
    else: s_val += m
    rows.append({"標的": sid, "現價": f"{p:,.2f}", "股數": f"{v['sh']:,.0f}", "市值": m})

st.title("📊 綜合退休戰情室 V72.1")
col1, col2, col3 = st.columns(3)
with col1: st.metric("資產總市值", f"${total_mkt:,.0f}")
with col2: 
    st.session_state.principal = st.number_input("設定投入總本金", value=float(st.session_state.principal))
    if st.button("💾 儲存本金"): save_data_to_gs(st.session_state.stocks, st.session_state.principal)
with col3:
    pnl = total_mkt - st.session_state.principal
    st.metric("累積總損益", f"${pnl:,.0f}", f"{(pnl/st.session_state.principal*100 if st.session_state.principal>0 else 0):.2f}%")

st.divider()
# (以下省略部分介面程式碼，與上一版相同)
st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

with st.sidebar:
    if st.button("🔄 強制刷新報價"): st.cache_data.clear(); st.rerun()
    add_id = st.text_input("新增代號").upper().strip()
    if st.button("➕ 新增入池"):
        if add_id: st.session_state.stocks[add_id] = {"sh": 0.0, "co": 0.0}; save_data_to_gs(st.session_state.stocks, st.session_state.principal); st.rerun()
