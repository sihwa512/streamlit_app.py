import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
import gspread
from google.oauth2.service_account import Credentials
import re

# --- 1. 頁面基本設定 ---
st.set_page_config(page_title="綜合退休戰情室 V72.2", layout="wide")

# --- 2. 核心雲端連線邏輯 (穩定版) ---
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
        doc = client.open("Retirement_Cloud_Data")
        ws_s = doc.worksheet("Stocks")
        s_data = ws_s.get_all_records()
        stocks = {str(r['id']).upper().strip(): {"sh": float(r['sh']), "co": float(r['co'])} for r in s_data} if s_data else {"CASH": {"sh": 0.0, "co": 1.0}}
        try:
            ws_v = doc.worksheet("Settings")
            v_data = ws_v.get_all_records()
            principal = float(next((i['value'] for i in v_data if i['key'] == 'principal'), 0.0))
        except: principal = 0.0
        return stocks, principal
    except: return {"CASH": {"sh": 0.0, "co": 1.0}}, 0.0

def save_data_to_gs(stocks, principal):
    client = get_gspread_client()
    if not client: return
    try:
        doc = client.open("Retirement_Cloud_Data")
        ws_s = doc.worksheet("Stocks")
        s_list = [["id", "sh", "co"]] + [[sid, v['sh'], v['co']] for sid, v in stocks.items()]
        ws_s.clear(); ws_s.update(values=s_list, range_name="A1")
        try:
            ws_v = doc.worksheet("Settings")
            ws_v.clear(); ws_v.update(values=[["key", "value"], ["principal", principal]], range_name="A1")
        except: pass
        st.toast("🚀 雲端同步成功！")
    except: st.error("❌ 同步失敗")

# --- 3. 樣式 CSS ---
st.markdown("""
    <style>
    .stApp { background-color: #0d1117; color: #c9d1d9; }
    [data-testid="stMetricValue"] > div { color: #00d4ff !important; font-family: 'Consolas', monospace !important; font-size: 2.2rem !important; font-weight: 800 !important; }
    .stat-card { text-align: center; padding: 15px; background: #161b22; border-radius: 12px; border: 1px solid #30363d; margin-bottom: 10px; }
    h1, h2, h3 { color: #58a6ff !important; }
    </style>
    """, unsafe_allow_html=True)

# --- 4. 報價與數據 ---
STOCK_NAMES = {"00662":"富邦NASDAQ", "00670L":"NASDAQ正2", "00865B":"美債1-3Y", "00631L":"50正2", "0050":"元大50", "2330":"台積電", "CASH":"閒置現金"}

@st.cache_data(ttl=600)
def fetch_price(symbol):
    if symbol == "CASH": return 1.0, STOCK_NAMES["CASH"]
    d_name = STOCK_NAMES.get(symbol, symbol)
    for suf in [".TW", ".TWO", ""]:
        try:
            t = yf.Ticker(f"{symbol}{suf}")
            p = t.fast_info.last_price
            if p > 0: return float(p), d_name
            h = t.history(period="1d"); 
            if not h.empty: return float(h['Close'].iloc[-1]), d_name
        except: continue
    return 0.0, d_name

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
    rows.append({"標的": sid, "名稱": name, "現價": f"{p:,.2f}", "股數": f"{v['sh']:,.0f}", "市值": m, "損益": f"{unrealized:,.0f}"})

safe_val = b_val + c_val

# --- 5. 主介面 ---
st.title("📊 綜合退休戰情室 V72.2")

m1, m2, m3 = st.columns(3)
with m1: st.metric("資產總市值", f"${total_mkt:,.0f}")
with m2: 
    new_p = st.number_input("設定投入總本金", value=float(st.session_state.principal))
    if st.button("💾 儲存本金"): st.session_state.principal = new_p; save_data_to_gs(st.session_state.stocks, new_p); st.rerun()
with m3:
    pnl = total_mkt - st.session_state.principal
    pct = (pnl / st.session_state.principal * 100) if st.session_state.principal > 0 else 0
    st.metric("真實累積總損益", f"${pnl:,.0f}", f"{pct:.2f}%")

st.divider()

# 再平衡區
st.subheader("⚖️ 目標再平衡對照")
curr_beta = (s_val/total_mkt * 1.0 + l_val/total_mkt * 2.0) if total_mkt > 0 else 0
st.markdown(f"當前組合 Beta: <b style='color:#bc8cff; font-size:1.2rem;'>{curr_beta:.2f}</b>", unsafe_allow_html=True)

c1, c2, c3 = st.columns(3)
def stat_box(label, color, val, pct):
    return f"<div class='stat-card' style='border-top:5px solid {color};'><small style='color:#8b949e;'>{label}</small><br><b style='color:{color}; font-size:26px;'>{pct:.1f}%</b><br><b style='color:{color}; font-size:24px;'>${val:,.0f}</b></div>"
with c1: st.markdown(stat_box("現況 股票", "#58a6ff", s_val, (s_val/total_mkt*100 if total_mkt>0 else 0)), unsafe_allow_html=True)
with c2: st.markdown(stat_box("現況 槓桿", "#bc8cff", l_val, (l_val/total_mkt*100 if total_mkt>0 else 0)), unsafe_allow_html=True)
with c3: st.markdown(stat_box("現況 類現金", "#3fb950", safe_val, (safe_val/total_mkt*100 if total_mkt>0 else 0)), unsafe_allow_html=True)

st.write("")
t1, t2, t3 = st.columns(3)
with t1: ts = st.number_input("目標 股票 %", value=40)
with t2: tl = st.number_input("目標 槓桿 %", value=30)
with t3:
    t_s_pct = 100 - ts - tl
    st.markdown(f"<div style='text-align:center;'><small style='color:#8b949e;'>目標 類現金</small><br><b style='color:#3fb950; font-size:24px;'>{t_s_pct}%</b></div>", unsafe_allow_html=True)

st.markdown(f"<div style='display:flex; justify-content:space-around; background:rgba(255,159,28,0.1); padding:10px; border-radius:8px; border:1px solid #ff9f1c;'><div style='color:#58a6ff;'>股票目標: ${total_mkt*ts/100:,.0f}</div><div style='color:#bc8cff;'>槓桿目標: ${total_mkt*tl/100:,.0f}</div><div style='color:#3fb950;'>類現金目標: ${total_mkt*t_s_pct/100:,.0f}</div></div>", unsafe_allow_html=True)

st.divider()

# 圖表與明細
col_p, col_t = st.columns([1, 2])
with col_p:
    if total_mkt > 0:
        fig = go.Figure(data=[go.Pie(labels=['股票', '槓桿', '類現金'], values=[s_val, l_val, safe_val], marker=dict(colors=['#58a6ff', '#bc8cff', '#3fb950']), hole=.5)])
        fig.update_layout(template="plotly_dark", margin=dict(t=0,b=0,l=0,r=0), paper_bgcolor='rgba(0,0,0,0)')
        st.plotly_chart(fig, use_container_width=True)
with col_t:
    st.subheader("📋 目前庫存清單")
    df_rows = pd.DataFrame(rows)
    df_rows['市值'] = df_rows['市值'].apply(lambda x: f"${x:,.0f}")
    st.dataframe(df_rows, use_container_width=True, hide_index=True)

with st.sidebar:
    st.header("⚙️ 標的管理")
    if st.button("🔄 強制刷新報價"): st.cache_data.clear(); st.rerun()
    add_id = st.text_input("新增代號").upper().strip()
    if st.button("➕ 新增標的"):
        if add_id: st.session_state.stocks[add_id] = {"sh": 0.0, "co": 0.0}; save_data_to_gs(st.session_state.stocks, st.session_state.principal); st.rerun()
    st.divider()
    if list(st.session_state.stocks.keys()):
        target = st.selectbox("修改標的", options=list(st.session_state.stocks.keys()))
        new_sh = st.number_input("持有股數", value=float(st.session_state.stocks[target]["sh"]))
        new_co = st.number_input("平均成本", value=float(st.session_state.stocks[target]["co"]))
        if st.button("💾 儲存修改"):
            st.session_state.stocks[target] = {"sh": new_sh, "co": new_co}
            save_data_to_gs(st.session_state.stocks, st.session_state.principal); st.rerun()
