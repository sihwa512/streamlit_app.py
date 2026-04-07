import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
import gspread
from google.oauth2.service_account import Credentials
import re

# --- 1. 頁面設定 ---
st.set_page_config(page_title="綜合退休戰情室 V72.8", layout="wide")

# --- 2. 雲端連線設定 ---
GS_ID = "1jgZhEi-nmaXGUa5fJaYwk79xE9-QG4LwhwV89xriGPs" 

def get_gspread_client():
    try:
        scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds_info = dict(st.secrets["gcp_service_account"])
        if "private_key" in creds_info:
            pk = creds_info["private_key"].replace("\\n", "\n")
            pk = re.sub(r'[^\x20-\x7E\n]', '', pk)
            creds_info["private_key"] = pk
        return gspread.authorize(Credentials.from_service_account_info(creds_info, scopes=scope))
    except: return None

def load_data_from_gs():
    client = get_gspread_client()
    if not client: return {"CASH": {"sh": 0.0, "co": 1.0}}, 0.0
    try:
        doc = client.open_by_key(GS_ID)
        ws_s = doc.worksheet("Stocks")
        # 🌟 讀取修正：確保讀取時不會因為空行報錯
        s_data = ws_s.get_all_values()
        if len(s_data) > 1:
            stocks = {}
            for r in s_data[1:]: # 跳過標題
                if r[0]: stocks[str(r[0]).upper().strip()] = {"sh": float(r[1] or 0), "co": float(r[2] or 0)}
        else:
            stocks = {"CASH": {"sh": 0.0, "co": 1.0}}
            
        ws_v = doc.worksheet("Settings")
        v_data = ws_v.get_all_values()
        principal = float(v_data[1][1]) if len(v_data) > 1 else 0.0
        return stocks, principal
    except:
        return {"CASH": {"sh": 0.0, "co": 1.0}}, 0.0

def save_data_to_gs(stocks, principal):
    client = get_gspread_client()
    if not client: return
    try:
        doc = client.open_by_key(GS_ID)
        
        # 🌟 寫入修正：改用「座標寫入」確保 100% 命中
        ws_s = doc.worksheet("Stocks")
        # 準備資料陣列
        s_list = [["id", "sh", "co"]] + [[sid, float(v['sh']), float(v['co'])] for sid, v in stocks.items()]
        
        # 暴力更新：直接覆蓋 A1 到 C10 的範圍
        ws_s.update(s_list, "A1") 
        
        # 儲存本金
        ws_v = doc.worksheet("Settings")
        ws_v.update([["key", "value"], ["principal", float(principal)]], "A1")
        
        st.success("✅ 數據已強制寫入 Google 試算表！")
        st.cache_data.clear()
    except Exception as e:
        st.error(f"❌ 同步失敗: {e}")

# --- 3. 視覺與報價 ---
st.markdown("<style>.stApp{background-color:#0d1117; color:#c9d1d9;} [data-testid='stMetricValue']>div{color:#00d4ff!important; font-weight:800!important; font-size:2.5rem!important;}</style>", unsafe_allow_html=True)

@st.cache_data(ttl=600)
def fetch_price(symbol):
    if symbol == "CASH": return 1.0, "現金"
    for suf in [".TW", ".TWO", ""]:
        try:
            t = yf.Ticker(f"{symbol}{suf}")
            p = t.fast_info.last_price
            if p > 0: return float(p), symbol
        except: continue
    return 0.0, symbol

# --- 4. 數據核心 ---
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
    unrealized = (p - v['co']) * v['sh'] if v['co'] > 0 else 0
    rows.append({"標的": sid, "現價": f"{p:,.2f}", "股數": f"{v['sh']:,.0f}", "市值": m, "損益": f"{unrealized:,.0f}"})

# --- 5. 主介面 ---
st.title("📊 綜合退休戰情室 V72.8")

m1, m2, m3 = st.columns(3)
with m1: st.metric("總市值", f"${total_mkt:,.0f}")
with m2: 
    new_p = st.number_input("本金", value=float(st.session_state.principal))
    if st.button("💾 同步至雲端"):
        st.session_state.principal = new_p
        save_data_to_gs(st.session_state.stocks, new_p)
        st.rerun()
with m3:
    pnl = total_mkt - st.session_state.principal
    st.metric("總損益", f"${pnl:,.0f}", f"{(pnl/st.session_state.principal*100 if st.session_state.principal>0 else 0):.2f}%")

st.divider()

# 庫存表格
st.subheader("📋 目前庫存清單")
st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

with st.sidebar:
    st.header("⚙️ 修改資料")
    if list(st.session_state.stocks.keys()):
        target = st.selectbox("選取標的", options=list(st.session_state.stocks.keys()))
        new_sh = st.number_input("股數", value=float(st.session_state.stocks[target]["sh"]))
        new_co = st.number_input("成本", value=float(st.session_state.stocks[target]["co"]))
        if st.button("💾 確認修改並寫入雲端"):
            st.session_state.stocks[target] = {"sh": new_sh, "co": new_co}
            save_data_to_gs(st.session_state.stocks, st.session_state.principal)
            st.rerun()
