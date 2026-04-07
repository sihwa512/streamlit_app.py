import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
import gspread
from google.oauth2.service_account import Credentials
import re

# --- 1. 頁面設定 ---
st.set_page_config(page_title="綜合退休戰情室 V73.2", layout="wide")

# --- 2. 雲端連線設定 ---
GS_ID = "1jgZhEi-nmaXGUa5fJaYwk79xE9-QG4LwhwV89xriGPs"

def get_client():
    try:
        scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds_info = dict(st.secrets["gcp_service_account"])
        if "private_key" in creds_info:
            creds_info["private_key"] = creds_info["private_key"].replace("\\n", "\n")
            creds_info["private_key"] = re.sub(r'[^\x20-\x7E\n]', '', creds_info["private_key"])
        return gspread.authorize(Credentials.from_service_account_info(creds_info, scopes=scope))
    except Exception as e:
        st.error(f"連線初始化失敗: {e}")
        return None

def load_data():
    client = get_client()
    # 基礎預設值
    def_s = {"CASH": {"sh": 200000.0, "co": 1.0}}
    def_p = 50000.0
    if not client: return def_s, def_p
    try:
        doc = client.open_by_key(GS_ID)
        # 讀取持股
        ws_s = doc.worksheet("Stocks")
        all_v = ws_s.get_all_values()
        stocks = {}
        if len(all_v) > 1:
            for r in all_v[1:]:
                if len(r) >= 3 and r[0]: 
                    stocks[str(r[0]).upper().strip()] = {"sh": float(r[1] or 0), "co": float(r[2] or 0)}
        else: stocks = def_s
        # 讀取本金
        try:
            ws_v = doc.worksheet("Settings")
            v_v = ws_v.get_all_values()
            p = float(v_v[1][1]) if len(v_v) > 1 else def_p
        except: p = def_p
        return stocks, p
    except: return def_s, def_p

def save_data(stocks, principal):
    client = get_client()
    if not client: return
    try:
        doc = client.open_by_key(GS_ID)
        
        # 🌟 寫入方式大改：使用更強制的清空與重寫
        # 1. 處理 Stocks
        ws_s = doc.worksheet("Stocks")
        ws_s.clear() # 先清空整張表，避免殘留資料干擾
        data_s = [["id", "sh", "co"]] + [[k, float(v['sh']), float(v['co'])] for k, v in stocks.items()]
        ws_s.update('A1', data_s)
        
        # 2. 處理 Settings
        ws_v = doc.worksheet("Settings")
        ws_v.clear()
        ws_v.update('A1', [["key", "value"], ["principal", float(principal)]])
        
        st.toast("✅ 雲端同步成功！數據已強制寫入。")
        st.cache_data.clear()
    except Exception as e:
        st.error(f"❌ 同步失敗，請確認分頁名稱是否正確: {e}")

# --- 3. 視覺與數據處理 ---
st.markdown("<style>.stApp{background-color:#0d1117; color:#c9d1d9;} [data-testid='stMetricValue']>div{color:#00d4ff!important; font-weight:800; font-size:2.6rem!important;}</style>", unsafe_allow_html=True)

if 'stocks' not in st.session_state:
    st.session_state.stocks, st.session_state.principal = load_data()

@st.cache_data(ttl=600)
def fetch_price(sid):
    if sid == "CASH": return 1.0, "閒置現金"
    names = {"00662":"富邦NASDAQ", "00670L":"NASDAQ正2", "00865B":"美債1-3Y", "00631L":"50正2", "0050":"元大50", "2330":"台積電"}
    d_name = names.get(sid, sid)
    for suf in [".TW", ".TWO", ""]:
        try:
            t = yf.Ticker(f"{sid}{suf}")
            p = t.fast_info.last_price
            if p > 0: return float(p), d_name
        except: continue
    return 0.0, d_name

# 計算核心
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
    rows.append({"標的": sid, "名稱": name, "現價": f"{p:,.2f}", "股數": f"{v['sh']:,.0f}", "市值": m, "損益": f"{pnl:,.0f}"})

# --- 4. 畫面呈現 ---
st.title("📊 綜合退休戰情室 V73.2")

# 指標列
m1, m2, m3 = st.columns(3)
with m1: st.metric("總市值", f"${total_mkt:,.0f}")
with m2: 
    st.session_state.principal = st.number_input("設定本金", value=float(st.session_state.principal))
    if st.button("💾 同步本金到雲端"):
        save_data(st.session_state.stocks, st.session_state.principal)
with m3:
    true_pnl = total_mkt - st.session_state.principal
    pct = (true_pnl / st.session_state.principal * 100) if st.session_state.principal > 0 else 0
    st.metric("總損益", f"${true_pnl:,.0f}", f"{pct:.2f}%")

st.divider()

# 方塊展示
c1, c2, c3 = st.columns(3)
def draw_card(title, color, val):
    p = (val / total_mkt * 100) if total_mkt > 0 else 0
    st.markdown(f"<div style='text-align:center; padding:20px; background:#161b22; border-radius:12px; border-top:6px solid {color};'><small style='color:#8b949e;'>{title}</small><br><b style='color:{color}; font-size:26px;'>{p:.1f}%</b><br><b style='color:{color}; font-size:24px;'>${val:,.0f}</b></div>", unsafe_allow_html=True)

with c1: draw_card("現況 股票", "#58a6ff", s_val)
with c2: draw_card("現況 槓桿", "#bc8cff", l_val)
with c3: draw_card("現況 類現金", "#3fb950", b_val + c_val)

st.divider()

# 表格管理
col_t, col_s = st.columns([2, 1])
with col_t:
    st.subheader("📋 目前持股清單")
    df = pd.DataFrame(rows)
    df['市值'] = df['市值'].apply(lambda x: f"${x:,.0f}")
    st.dataframe(df, use_container_width=True, hide_index=True)

with col_s:
    st.subheader("⚙️ 快速修改")
    target = st.selectbox("選取標的", options=list(st.session_state.stocks.keys()))
    new_sh = st.number_input("股數", value=float(st.session_state.stocks[target]["sh"]))
    new_co = st.number_input("成本", value=float(st.session_state.stocks[target]["co"]))
    if st.button("💾 儲存修改並強制同步"):
        st.session_state.stocks[target] = {"sh": new_sh, "co": new_co}
        save_data(st.session_state.stocks, st.session_state.principal)
        st.rerun()
    
    st.divider()
    new_id = st.text_input("➕ 新增代號").upper().strip()
    if st.button("新增標的"):
        if new_id:
            st.session_state.stocks[new_id] = {"sh": 0.0, "co": 0.0}
            save_data(st.session_state.stocks, st.session_state.principal)
            st.rerun()
