import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
import gspread
from google.oauth2.service_account import Credentials
import re

# --- 1. 頁面設定 ---
st.set_page_config(page_title="綜合退休戰情室 V72.9", layout="wide")

# --- 2. 雲端連線設定 (ID 已確認) ---
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
        s_data = ws_s.get_all_values()
        stocks = {}
        if len(s_data) > 1:
            for r in s_data[1:]:
                if r[0]: 
                    # 讀取時也進行清理
                    sid = str(r[0]).upper().strip()
                    stocks[sid] = {"sh": round(float(r[1] or 0), 2), "co": round(float(r[2] or 0), 2)}
        else: stocks = {"CASH": {"sh": 0.0, "co": 1.0}}
            
        ws_v = doc.worksheet("Settings")
        v_data = ws_v.get_all_values()
        principal = round(float(v_data[1][1]), 0) if len(v_data) > 1 else 0.0
        return stocks, principal
    except: return {"CASH": {"sh": 0.0, "co": 1.0}}, 0.0

def save_data_to_gs(stocks, principal):
    client = get_gspread_client()
    if not client: return
    try:
        doc = client.open_by_key(GS_ID)
        
        # 🌟 核心修正：將數據強制格式化為乾淨的數字
        ws_s = doc.worksheet("Stocks")
        # 標題行
        clean_list = [["id", "sh", "co"]]
        for sid, v in stocks.items():
            # 這裡強制四捨五入到小數點第二位，解決 98849.9985 這種碎碎的數字問題
            clean_list.append([sid, round(float(v['sh']), 2), round(float(v['co']), 2)])
        
        ws_s.update(clean_list, "A1") 
        
        # 儲存本金
        ws_v = doc.worksheet("Settings")
        ws_v.update([["key", "value"], ["principal", round(float(principal), 0)]], "A1")
        
        st.success("✅ 雲端同步完成！請重新整理試算表頁面確認。")
        st.cache_data.clear()
    except Exception as e:
        st.error(f"❌ 同步失敗: {e}")

# --- 3. 視覺樣式與報價 ---
st.markdown("<style>.stApp{background-color:#0d1117; color:#c9d1d9;} [data-testid='stMetricValue']>div{color:#00d4ff!important; font-weight:800!important; opacity:1!important;}</style>", unsafe_allow_html=True)

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

# --- 4. 初始化 ---
if 'stocks' not in st.session_state:
    st.session_state.stocks, st.session_state.principal = load_data_from_gs()

total_mkt, s_val, l_val, b_val, c_val = 0.0, 0.0, 0.0, 0.0, 0.0
rows = []
for sid, v in st.session_state.stocks.items():
    p, name = fetch_price(sid)
    m = round(v['sh'] * p, 0) # 市值取整數
    total_mkt += m
    if sid == "CASH": c_val += m
    elif "B" in sid: b_val += m
    elif "L" in sid: l_val += m
    else: s_val += m
    
    unrealized = round((p - v['co']) * v['sh'], 0)
    rows.append({"標的": sid, "現價": f"{p:,.2f}", "股數": f"{v['sh']:,.0f}", "市值": f"${m:,.0f}", "損益": f"${unrealized:,.0f}"})

# --- 5. 畫面 ---
st.title("📊 綜合退休戰情室 V72.9")

m1, m2, m3 = st.columns(3)
with m1: st.metric("總市值", f"${total_mkt:,.0f}")
with m2: 
    new_p = st.number_input("本金設定", value=float(st.session_state.principal))
    if st.button("💾 儲存並同步至雲端"):
        st.session_state.principal = new_p
        save_data_to_gs(st.session_state.stocks, new_p)
        st.rerun()
with m3:
    pnl = total_mkt - st.session_state.principal
    st.metric("總損益", f"${pnl:,.0f}", f"{(pnl/st.session_state.principal*100 if st.session_state.principal>0 else 0):.2f}%")

st.divider()
st.table(pd.DataFrame(rows)) # 使用靜態表格更清楚

with st.sidebar:
    st.header("⚙️ 修改資料")
    target = st.selectbox("標的", options=list(st.session_state.stocks.keys()))
    new_sh = st.number_input("股數", value=float(st.session_state.stocks[target]["sh"]))
    new_co = st.number_input("成本", value=float(st.session_state.stocks[target]["co"]))
    if st.button("💾 確認修改並存檔"):
        st.session_state.stocks[target] = {"sh": new_sh, "co": new_co}
        save_data_to_gs(st.session_state.stocks, st.session_state.principal)
        st.rerun()
