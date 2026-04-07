import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
import gspread
from google.oauth2.service_account import Credentials
import re

# --- 1. 頁面設定 ---
st.set_page_config(page_title="綜合退休戰情室 V73.0", layout="wide")

# --- 2. 雲端連線 ---
GS_ID = "1jgZhEi-nmaXGUa5fJaYwk79xE9-QG4LwhwV89xriGPs"

def get_client():
    try:
        scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = dict(st.secrets["gcp_service_account"])
        if "private_key" in creds:
            creds["private_key"] = creds["private_key"].replace("\\n", "\n")
            creds["private_key"] = re.sub(r'[^\x20-\x7E\n]', '', creds["private_key"])
        return gspread.authorize(Credentials.from_service_account_info(creds, scopes=scope))
    except: return None

def load_data():
    client = get_client()
    # 預設值，防崩潰
    default_stocks = {"CASH": {"sh": 200000.0, "co": 1.0}}
    default_p = 50000.0
    if not client: return default_stocks, default_p
    try:
        doc = client.open_by_key(GS_ID)
        # 讀取 Stocks
        ws_s = doc.worksheet("Stocks")
        all_v = ws_s.get_all_values()
        stocks = {}
        if len(all_v) > 1:
            for r in all_v[1:]:
                if r[0]: stocks[str(r[0]).upper().strip()] = {"sh": float(r[1] or 0), "co": float(r[2] or 0)}
        else: stocks = default_stocks
        # 讀取本金
        try:
            ws_v = doc.worksheet("Settings")
            v_v = ws_v.get_all_values()
            principal = float(v_v[1][1]) if len(v_v) > 1 else default_p
        except: principal = default_p
        return stocks, principal
    except: return default_stocks, default_p

def save_data(stocks, principal):
    client = get_client()
    if not client: return
    try:
        doc = client.open_by_key(GS_ID)
        # 寫入 Stocks
        ws_s = doc.worksheet("Stocks")
        data = [["id", "sh", "co"]] + [[k, float(v['sh']), float(v['co'])] for k, v in stocks.items()]
        ws_s.update(data, "A1")
        # 寫入 Settings
        ws_v = doc.worksheet("Settings")
        ws_v.update([["key", "value"], ["principal", float(principal)]], "A1")
        st.success("✅ 雲端同步成功！")
        st.cache_data.clear()
    except Exception as e: st.error(f"同步出錯: {e}")

# --- 3. 視覺樣式 ---
st.markdown("""
    <style>
    .stApp { background-color: #0d1117; color: #c9d1d9; }
    [data-testid="stMetricValue"] > div { color: #00d4ff !important; font-family: 'Consolas'; font-size: 2.6rem !important; font-weight: 800 !important; }
    .stat-card { text-align: center; padding: 20px; background: #161b22; border-radius: 12px; border: 1px solid #30363d; margin-bottom: 15px; }
    </style>
    """, unsafe_allow_html=True)

# --- 4. 數據引擎 ---
if 'stocks' not in st.session_state:
    st.session_state.stocks, st.session_state.principal = load_data()

@st.cache_data(ttl=600)
def fetch_price(sid):
    if sid == "CASH": return 1.0, "閒置現金"
    names = {"00662":"富邦NASDAQ", "00670L":"NASDAQ正2", "00865B":"美債1-3Y", "00631L":"50正2", "0050":"元大50", "2330":"台積電"}
    for suf in [".TW", ".TWO", ""]:
        try:
            t = yf.Ticker(f"{sid}{suf}")
            p = t.fast_info.last_price
            if p > 0: return float(p), names.get(sid, sid)
        except: continue
    return 0.0, names.get(sid, sid)

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
    pnl = (p - v['co']) * v['sh']
    rows.append({"標的": sid, "名稱": name, "現價": f"{p:,.2f}", "股數": f"{v['sh']:,.0f}", "市值": f"${m:,.0f}", "損益": f"${pnl:,.0f}"})

# --- 5. 畫面呈現 ---
st.title("📊 綜合退休戰情室 V73.0")

col1, col2, col3 = st.columns(3)
with col1: st.metric("總市值", f"${total_mkt:,.0f}")
with col2: 
    new_p = st.number_input("本金設定", value=float(st.session_state.principal))
    if st.button("💾 儲存並同步"):
        st.session_state.principal = new_p
        save_data(st.session_state.stocks, new_p)
        st.rerun()
with col3:
    true_pnl = total_mkt - st.session_state.principal
    pct = (true_pnl / st.session_state.principal * 100) if st.session_state.principal > 0 else 0
    st.metric("總損益", f"${true_pnl:,.0f}", f"{pct:.2f}%")

st.divider()

# 方塊對應
c1, c2, c3 = st.columns(3)
def stat_box(label, color, val):
    pct = (val / total_mkt * 100) if total_mkt > 0 else 0
    return f"<div class='stat-card' style='border-top:6px solid {color};'><small style='color:#8b949e;'>{label}</small><br><b style='color:{color}; font-size:26px;'>{pct:.1f}%</b><br><b style='color:{color}; font-size:24px;'>${val:,.0f}</b></div>"
with c1: st.markdown(stat_box("現況 股票", "#58a6ff", s_val), unsafe_allow_html=True)
with c2: st.markdown(stat_box("現況 槓桿", "#bc8cff", l_val), unsafe_allow_html=True)
with c3: st.markdown(stat_box("現況 類現金", "#3fb950", b_val + c_val), unsafe_allow_html=True)

st.divider()

# 表格
st.subheader("📋 持股明細清單")
st.table(pd.DataFrame(rows))

with st.sidebar:
    st.header("⚙️ 雲端操作")
    if st.button("🔄 強制重新整理"): st.cache_data.clear(); st.rerun()
    st.divider()
    target = st.selectbox("修改標的", options=list(st.session_state.stocks.keys()))
    new_sh = st.number_input("股數", value=float(st.session_state.stocks[target]["sh"]))
    new_co = st.number_input("成本", value=float(st.session_state.stocks[target]["co"]))
    if st.button("💾 確認修改內容"):
        st.session_state.stocks[target] = {"sh": new_sh, "co": new_co}
        save_data(st.session_state.stocks, st.session_state.principal)
        st.rerun()
