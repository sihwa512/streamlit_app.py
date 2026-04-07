import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
import gspread
from google.oauth2.service_account import Credentials
import re

# --- 1. 頁面設定 ---
st.set_page_config(page_title="綜合退休戰情室 V73.1", layout="wide")

# --- 2. 雲端連線核心 (您的專屬 ID) ---
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
    # 預設數據，防止讀取失敗時畫面消失
    def_s = {"CASH": {"sh": 200000.0, "co": 1.0}}
    def_p = 50000.0
    if not client: return def_s, def_p
    try:
        doc = client.open_by_key(GS_ID)
        # 讀取 Stocks
        ws_s = doc.worksheet("Stocks")
        all_v = ws_s.get_all_values()
        stocks = {}
        if len(all_v) > 1:
            for r in all_v[1:]:
                if r[0]: stocks[str(r[0]).upper().strip()] = {"sh": float(r[1] or 0), "co": float(r[2] or 0)}
        else: stocks = def_s
        # 讀取 Settings
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
        # 1. 寫入持股
        ws_s = doc.worksheet("Stocks")
        data = [["id", "sh", "co"]] + [[k, float(v['sh']), float(v['co'])] for k, v in stocks.items()]
        ws_s.update(data, "A1")
        # 2. 寫入本金
        ws_v = doc.worksheet("Settings")
        ws_v.update([["key", "value"], ["principal", float(principal)]], "A1")
        st.success("✅ 雲端同步完成！")
        st.cache_data.clear()
    except Exception as e: st.error(f"❌ 同步出錯: {e}")

# --- 3. 視覺與數據引擎 ---
st.markdown("<style>.stApp{background-color:#0d1117; color:#c9d1d9;} [data-testid='stMetricValue']>div{color:#00d4ff!important; font-family:'Consolas'; font-weight:800; font-size:2.6rem!important;}</style>", unsafe_allow_html=True)

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

# --- 4. 計算資產數據 ---
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

# --- 5. 畫面呈現 ---
st.title("📊 綜合退休戰情室 V73.1")

m1, m2, m3 = st.columns(3)
with m1: st.metric("總市值", f"${total_mkt:,.0f}")
with m2: 
    new_p = st.number_input("本金設定", value=float(st.session_state.principal))
    if st.button("💾 儲存本金並同步"):
        st.session_state.principal = new_p
        save_data(st.session_state.stocks, new_p)
        st.rerun()
with m3:
    true_p = total_mkt - st.session_state.principal
    pct = (true_p / st.session_state.principal * 100) if st.session_state.principal > 0 else 0
    st.metric("總損益", f"${true_p:,.0f}", f"{pct:.2f}%")

st.divider()

# 方塊對照與再平衡
st.subheader("⚖️ 再平衡對照區")
c1, c2, c3 = st.columns(3)
def stat_box(label, color, val):
    pct = (val / total_mkt * 100) if total_mkt > 0 else 0
    return f"<div style='text-align:center; padding:20px; background:#161b22; border-radius:12px; border-top:6px solid {color};'><small style='color:#8b949e;'>{label}</small><br><b style='color:{color}; font-size:26px;'>{pct:.1f}%</b><br><b style='color:{color}; font-size:24px;'>${val:,.0f}</b></div>"
with c1: st.markdown(stat_box("現況 股票", "#58a6ff", s_val), unsafe_allow_html=True)
with c2: st.markdown(stat_box("現況 槓桿", "#bc8cff", l_val), unsafe_allow_html=True)
with c3: st.markdown(stat_box("現況 類現金", "#3fb950", b_val + c_val), unsafe_allow_html=True)

st.write("")
t1, t2, t3 = st.columns(3)
with t1: ts = st.number_input("目標 股票 %", value=40)
with t2: tl = st.number_input("目標 槓桿 %", value=30)
with t3:
    tsafe = 100 - ts - tl
    st.markdown(f"<div style='text-align:center; padding:5px;'><small style='color:#aaa;'>目標 類現金</small><br><b style='color:#3fb950; font-size:24px;'>{tsafe}%</b></div>", unsafe_allow_html=True)

st.markdown(f"<div style='display:flex; justify-content:space-around; background:rgba(255,159,28,0.1); padding:10px; border-radius:8px; border:1px solid #ff9f1c;'><div style='color:#58a6ff;'>股票目標: ${total_mkt*ts/100:,.0f}</div><div style='color:#bc8cff;'>槓桿目標: ${total_mkt*tl/100:,.0f}</div><div style='color:#3fb950;'>類現金目標: ${total_mkt*tsafe/100:,.0f}</div></div>", unsafe_allow_html=True)

st.divider()

# 表格與圓餅圖
col_pie, col_table = st.columns([1, 2])
with col_pie:
    if total_mkt > 0:
        fig = go.Figure(data=[go.Pie(labels=['股票', '槓桿', '類現金'], values=[s_val, l_val, b_val+c_val], marker=dict(colors=['#58a6ff', '#bc8cff', '#3fb950']), hole=.5)])
        fig.update_layout(template="plotly_dark", margin=dict(t=0,b=0,l=0,r=0), paper_bgcolor='rgba(0,0,0,0)')
        st.plotly_chart(fig, use_container_width=True)
with col_table:
    st.subheader("📋 目前庫存清單")
    df_rows = pd.DataFrame(rows)
    df_rows['市值'] = df_rows['市值'].apply(lambda x: f"${x:,.0f}")
    st.dataframe(df_rows, use_container_width=True, hide_index=True)

with st.sidebar:
    st.header("⚙️ 雲端操作")
    add_id = st.text_input("➕ 新增代號").upper().strip()
    if st.button("加入並同步"):
        if add_id: st.session_state.stocks[add_id] = {"sh": 0.0, "co": 0.0}; save_data(st.session_state.stocks, st.session_state.principal); st.rerun()
    st.divider()
    target = st.selectbox("修改標的", options=list(st.session_state.stocks.keys()))
    new_sh = st.number_input("持有股數", value=float(st.session_state.stocks[target]["sh"]))
    new_co = st.number_input("平均成本", value=float(st.session_state.stocks[target]["co"]))
    if st.button("💾 儲存修改內容"):
        st.session_state.stocks[target] = {"sh": new_sh, "co": new_co}
        save_data(st.session_state.stocks, st.session_state.principal); st.rerun()
