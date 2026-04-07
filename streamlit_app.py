import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
import gspread
from google.oauth2.service_account import Credentials

# --- 頁面設定 ---
st.set_page_config(page_title="綜合退休戰情室 V71.8", layout="wide")

# --- 1. Google Sheets 核心連線 (極簡化版) ---
GS_FILENAME = "Retirement_Cloud_Data"

def get_client():
    try:
        scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        return gspread.authorize(Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope))
    except Exception as e:
        st.error(f"❌ Google 授權失敗: {e}")
        return None

def load_data():
    client = get_client()
    if not client: return {"CASH": {"sh": 0.0, "co": 1.0}}, 0.0
    try:
        doc = client.open(GS_FILENAME)
        # 讀取 Stocks
        ws_s = doc.worksheet("Stocks")
        s_data = ws_s.get_all_records()
        stocks = {str(r['id']).upper().strip(): {"sh": float(r['sh']), "co": float(r['co'])} for r in s_data} if s_data else {"CASH": {"sh": 0.0, "co": 1.0}}
        # 讀取本金
        try:
            ws_v = doc.worksheet("Settings")
            v_data = ws_v.get_all_records()
            principal = float(v_data[0]['value']) # 假設第一列就是本金
        except: principal = 0.0
        return stocks, principal
    except Exception as e:
        st.error(f"❌ 雲端讀取報錯: {e}")
        return {"CASH": {"sh": 0.0, "co": 1.0}}, 0.0

def save_to_cloud(stocks, principal):
    client = get_client()
    if not client: return
    try:
        doc = client.open(GS_FILENAME)
        # 寫入持股
        ws_s = doc.worksheet("Stocks")
        s_list = [["id", "sh", "co"]] + [[k, v['sh'], v['co']] for k, v in stocks.items()]
        ws_s.update("A1", s_list) # 移除 clear()，直接覆蓋
        
        # 寫入本金
        try:
            ws_v = doc.worksheet("Settings")
            ws_v.update("A1", [["key", "value"], ["principal", principal]])
        except: pass
        
        st.success("🚀 雲端同步成功！") # 改用較顯眼的綠色通知
    except Exception as e:
        st.error(f"❌ 寫入雲端失敗: {e}")

# --- 2. 報價引擎 ---
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
        except: continue
    return 0.0, d_name

# --- 3. 數據核心 ---
if 'stocks' not in st.session_state or 'principal' not in st.session_state:
    st.session_state.stocks, st.session_state.principal = load_data()

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

# --- 4. 畫面排版 ---
st.title("📊 綜合退休戰情室 V71.8")
st.markdown("<style>[data-testid='stMetricValue'] > div { color: #00d4ff !important; font-family: 'Consolas'; font-weight: bold; font-size: 2.2rem !important; }</style>", unsafe_allow_html=True)

col1, col2, col3 = st.columns(3)
with col1: st.metric("資產總市值", f"${total_mkt:,.0f}")
with col2:
    new_p = st.number_input("設定投入總本金", value=float(st.session_state.principal))
    if st.button("💾 儲存本金"): # 增加一個實體按鈕
        st.session_state.principal = new_p
        save_to_cloud(st.session_state.stocks, new_p)
with col3:
    pnl = total_mkt - st.session_state.principal
    st.metric("真實累積總損益", f"${pnl:,.0f}", f"{(pnl/st.session_state.principal*100 if st.session_state.principal>0 else 0):.2f}%")

st.divider()

# 現況方塊
c1, c2, c3 = st.columns(3)
with c1: st.info(f"現況 股票: {(s_val/total_mkt*100 if total_mkt>0 else 0):.1f}% \n\n ${s_val:,.0f}")
with c2: st.warning(f"現況 槓桿: {(l_val/total_mkt*100 if total_mkt>0 else 0):.1f}% \n\n ${l_val:,.0f}")
with c3: st.success(f"現況 類現金: {((b_val+c_val)/total_mkt*100 if total_mkt>0 else 0):.1f}% \n\n ${(b_val+c_val):,.0f}")

# 表格與管理
st.subheader("📋 持股明細")
st.table(pd.DataFrame(rows))

with st.sidebar:
    st.header("⚙️ 雲端操作")
    add_id = st.text_input("新增標的代號").upper().strip()
    if st.button("➕ 加入清單並同步"):
        if add_id:
            st.session_state.stocks[add_id] = {"sh": 0.0, "co": 0.0}
            save_to_cloud(st.session_state.stocks, st.session_state.principal)
            st.rerun()
    st.divider()
    if list(st.session_state.stocks.keys()):
        target = st.selectbox("修改標的", options=list(st.session_state.stocks.keys()))
        new_sh = st.number_input("股數", value=float(st.session_state.stocks[target]["sh"]))
        new_co = st.number_input("成本", value=float(st.session_state.stocks[target]["co"]))
        if st.button("💾 儲存修改"):
            st.session_state.stocks[target] = {"sh": new_sh, "co": new_co}
            save_to_cloud(st.session_state.stocks, st.session_state.principal)
            st.rerun()
