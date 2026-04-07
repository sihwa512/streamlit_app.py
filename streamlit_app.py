import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
import gspread
from google.oauth2.service_account import Credentials

# --- 頁面設定 ---
st.set_page_config(page_title="綜合退休戰情室 V71.6", layout="wide")

# --- 1. Google Sheets 連接邏輯 (優化寫入穩定性) ---
GS_FILENAME = "Retirement_Cloud_Data"

def get_gspread_client():
    try:
        scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds_dict = st.secrets["gcp_service_account"]
        creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
        return gspread.authorize(creds)
    except: return None

def load_data_from_gs():
    client = get_gspread_client()
    if not client: return {"CASH": {"sh": 0.0, "co": 1.0}}, 0.0
    try:
        doc = client.open(GS_FILENAME)
        # 讀取持股 Stocks
        try:
            ws_stocks = doc.worksheet("Stocks")
            data = ws_stocks.get_all_records()
            stocks = {str(r['id']).upper().strip(): {"sh": float(r['sh']), "co": float(r['co'])} for r in data} if data else {"CASH": {"sh": 0.0, "co": 1.0}}
        except: stocks = {"CASH": {"sh": 0.0, "co": 1.0}}
        
        # 讀取本金 Settings
        try:
            ws_set = doc.worksheet("Settings")
            set_data = ws_set.get_all_records()
            principal = float(next((i['value'] for i in set_data if i['key'] == 'principal'), 0.0))
        except: principal = 0.0
            
        return stocks, principal
    except Exception as e:
        st.error(f"讀取失敗: {e}")
        return {"CASH": {"sh": 0.0, "co": 1.0}}, 0.0

def save_data_to_gs(stocks, principal):
    client = get_gspread_client()
    if not client: return
    try:
        doc = client.open(GS_FILENAME)
        # 🌟 強化寫入邏輯：改用一次性全覆蓋更新
        ws_stocks = doc.worksheet("Stocks")
        stock_list = [["id", "sh", "co"]] + [[sid, v['sh'], v['co']] for sid, v in stocks.items()]
        ws_stocks.clear() # 先清空，確保舊標的不殘留
        ws_stocks.update("A1", stock_list)
        
        # 寫入本金
        try:
            ws_set = doc.worksheet("Settings")
            ws_set.clear()
            ws_set.update("A1", [["key", "value"], ["principal", principal]])
        except: pass
        
        st.toast("🚀 雲端同步成功！")
    except Exception as e:
        st.error(f"同步失敗，原因: {e}")

# --- 2. 樣式與報價 ---
st.markdown("<style>.stApp { background-color: #0d1117; color: #c9d1d9; }[data-testid='stMetricValue'] > div { color: #00d4ff !important; font-family: 'Consolas'; font-weight: bold; font-size: 2.2rem !important; }</style>", unsafe_allow_html=True)

@st.cache_data(ttl=600)
def fetch_price(symbol):
    if symbol == "CASH": return 1.0, "閒置現金"
    names = {"00662":"富邦NASDAQ", "00670L":"NASDAQ正2", "00865B":"美債1-3Y", "00631L":"50正2", "0050":"元大50", "2330":"台積電"}
    d_name = names.get(symbol, symbol)
    for suf in [".TW", ".TWO", ""]:
        try:
            t = yf.Ticker(f"{symbol}{suf}")
            p = t.fast_info.last_price
            if p > 0: return float(p), d_name
            h = t.history(period="1d")
            if not h.empty: return float(h['Close'].iloc[-1]), d_name
        except: continue
    return 0.0, d_name

# --- 3. 數據核心流程 ---
if 'stocks' not in st.session_state or 'principal' not in st.session_state:
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
    roi = ((p - v['co']) / v['co'] * 100) if v['co'] > 0 else 0
    rows.append({"標的": sid, "名稱": name, "現價": f"{p:,.2f}", "股數": f"{v['sh']:,.0f}", "市值": m, "損益": f"{unrealized:,.0f}", "報酬率": f"{roi:.2f}%"})

# --- 4. 畫面呈現 ---
st.title("📊 綜合退休戰情室 V71.6 Cloud")

m1, m2, m3 = st.columns(3)
with m1: st.metric("資產總市值", f"${total_mkt:,.0f}")
with m2: 
    new_p = st.number_input("投入總本金", value=float(st.session_state.principal), step=1000.0)
    if new_p != st.session_state.principal:
        st.session_state.principal = new_p
        save_data_to_gs(st.session_state.stocks, new_p)
with m3:
    pnl = total_mkt - st.session_state.principal
    pct = (pnl / st.session_state.principal * 100) if st.session_state.principal > 0 else 0
    st.metric("真實累積總損益", f"${pnl:,.0f}", f"{pct:.2f}%")

st.divider()

# Beta 再平衡區
curr_beta = (s_val/total_mkt * 1.0 + l_val/total_mkt * 2.0) if total_mkt > 0 else 0
st.markdown(f"當前組合 Beta: <b style='color:#bc8cff; font-size:1.2rem;'>{curr_beta:.2f}</b>", unsafe_allow_html=True)
c1, c2, c3 = st.columns(3)
def stat_box(label, color, val, pct):
    return f"<div style='text-align:center; padding:12px; background:#161b22; border-radius:12px; border-top:5px solid {color};'><small style='color:#8b949e;'>{label}</small><br><b style='color:{color}; font-size:24px;'>{pct:.1f}%</b><br><b style='color:{color}; font-size:22px;'>${val:,.0f}</b></div>"
with c1: st.markdown(stat_box("現況 股票", "#58a6ff", s_val, (s_val/total_mkt*100 if total_mkt>0 else 0)), unsafe_allow_html=True)
with c2: st.markdown(stat_box("現況 槓桿", "#bc8cff", l_val, (l_val/total_mkt*100 if total_mkt>0 else 0)), unsafe_allow_html=True)
with c3: st.markdown(stat_box("現況 類現金", "#3fb950", (b_val+c_val), ((b_val+c_val)/total_mkt*100 if total_mkt>0 else 0)), unsafe_allow_html=True)

st.write("")
t1, t2, t3 = st.columns(3)
with t1: ts = st.number_input("目標 股票 %", value=40)
with t2: tl = st.number_input("目標 槓桿 %", value=30)
with t3:
    t_safe_pct = 100 - ts - tl
    st.markdown(f"<div style='text-align:center; padding:5px;'><small style='color:#8b949e;'>目標 類現金</small><br><b style='color:#3fb950; font-size:24px;'>{t_safe_pct}%</b></div>", unsafe_allow_html=True)

st.markdown(f"<div style='display:flex; justify-content:space-around; background:rgba(255,159,28,0.1); padding:10px; border-radius:8px; border:1px solid #ff9f1c;'><div style='color:#58a6ff;'>股票目標: ${total_mkt*ts/100:,.0f}</div><div style='color:#bc8cff;'>槓桿目標: ${total_mkt*tl/100:,.0f}</div><div style='color:#3fb950;'>類現金目標: ${total_mkt*t_safe_pct/100:,.0f}</div></div>", unsafe_allow_html=True)

st.divider()

# 表格與圖表
col_pie, col_table = st.columns([1, 2])
with col_pie:
    fig = go.Figure(data=[go.Pie(labels=['股票', '槓桿', '債券', '現金'], values=[s_val, l_val, b_val, c_val], marker=dict(colors=['#58a6ff', '#bc8cff', '#ff9f1c', '#3fb950']), hole=.5)])
    fig.update_layout(template="plotly_dark", margin=dict(t=0,b=0,l=0,r=0), paper_bgcolor='rgba(0,0,0,0)')
    st.plotly_chart(fig, use_container_width=True)
with col_table:
    st.subheader("📋 目前標的庫存")
    df_rows = pd.DataFrame(rows)
    df_rows['市值'] = df_rows['市值'].apply(lambda x: f"${x:,.0f}")
    st.dataframe(df_rows, use_container_width=True, hide_index=True)

# 側邊欄
with st.sidebar:
    st.header("⚙️ 雲端中心")
    if st.button("🚀 強制刷新 (同步雲端)"):
        st.cache_data.clear()
        st.session_state.stocks, st.session_state.principal = load_data_from_gs()
        st.rerun()
    st.divider()
    add_id = st.text_input("新增代號").upper().strip()
    if st.button("➕ 新增標的"):
        if add_id: 
            st.session_state.stocks[add_id] = {"sh": 0.0, "co": 0.0}
            save_data_to_gs(st.session_state.stocks, st.session_state.principal)
            st.rerun()
    st.divider()
    if list(st.session_state.stocks.keys()):
        target = st.selectbox("修改標的", options=list(st.session_state.stocks.keys()))
        new_sh = st.number_input("持有股數", value=float(st.session_state.stocks[target]["sh"]))
        new_co = st.number_input("平均成本", value=float(st.session_state.stocks[target]["co"]))
        if st.button("💾 儲存修改"):
            st.session_state.stocks[target] = {"sh": new_sh, "co": new_co}
            save_data_to_gs(st.session_state.stocks, st.session_state.principal)
            st.rerun()
