import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
import gspread
from google.oauth2.service_account import Credentials
import re

# --- 1. 頁面設定 ---
st.set_page_config(page_title="綜合退休戰情室 V72.5", layout="wide")

# --- 2. 雲端連線設定 (已填入您的專屬 ID) ---
GS_ID = "1jgZhEi-nmaXGUa5fJaYwk79xE9-QG4LwhwV89xriGPs" 

def get_gspread_client():
    try:
        scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds_info = dict(st.secrets["gcp_service_account"])
        # 自動清潔私鑰格式
        if "private_key" in creds_info:
            pk = creds_info["private_key"].replace("\\n", "\n")
            pk = re.sub(r'[^\x20-\x7E\n]', '', pk)
            creds_info["private_key"] = pk
        return gspread.authorize(Credentials.from_service_account_info(creds_info, scopes=scope))
    except Exception as e:
        st.error(f"⚠️ 連線初始化失敗: {e}")
        return None

def load_data_from_gs():
    client = get_gspread_client()
    if not client: return {"CASH": {"sh": 0.0, "co": 1.0}}, 0.0
    try:
        doc = client.open_by_key(GS_ID)
        # 讀取 Stocks
        ws_s = doc.worksheet("Stocks")
        s_data = ws_s.get_all_records()
        stocks = {str(r['id']).upper().strip(): {"sh": float(r['sh']), "co": float(r['co'])} for r in s_data} if s_data else {"CASH": {"sh": 0.0, "co": 1.0}}
        # 讀取 Settings
        try:
            ws_v = doc.worksheet("Settings")
            v_data = ws_v.get_all_records()
            principal = float(next((i['value'] for i in v_data if i['key'] == 'principal'), 0.0))
        except: principal = 0.0
        return stocks, principal
    except Exception as e:
        st.error(f"❌ 雲端讀取失敗: {e}")
        return {"CASH": {"sh": 0.0, "co": 1.0}}, 0.0

def save_data_to_gs(stocks, principal):
    client = get_gspread_client()
    if not client: return
    try:
        doc = client.open_by_key(GS_ID)
        # 1. 更新 Stocks
        ws_s = doc.worksheet("Stocks")
        s_list = [["id", "sh", "co"]] + [[sid, v['sh'], v['co']] for sid, v in stocks.items()]
        ws_s.update(s_list, "A1")
        # 2. 更新 Settings
        try:
            ws_v = doc.worksheet("Settings")
            ws_v.update([["key", "value"], ["principal", principal]], "A1")
        except: pass
        st.success("✅ 雲端同步成功！數據已存入試算表。")
    except Exception as e:
        st.error(f"❌ 寫入雲端失敗: {e}")

# --- 3. 視覺與報價 ---
st.markdown("<style>.stApp { background-color: #0d1117; color: #c9d1d9; }[data-testid='stMetricValue'] > div { color: #00d4ff !important; font-weight: bold; font-size: 2.2rem !important; }</style>", unsafe_allow_html=True)

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
            h = t.history(period="1d"); 
            if not h.empty: return float(h['Close'].iloc[-1]), d_name
        except: continue
    return 0.0, d_name

# --- 4. 數據初始化 ---
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

# --- 5. 畫面呈現 ---
st.title("📊 綜合退休戰情室 V72.5")

col1, col2, col3 = st.columns(3)
with col1: st.metric("資產總市值", f"${total_mkt:,.0f}")
with col2: 
    st.session_state.principal = st.number_input("設定投入總本金", value=float(st.session_state.principal))
    if st.button("💾 儲存本金並同步"):
        save_data_to_gs(st.session_state.stocks, st.session_state.principal)
with col3:
    pnl = total_mkt - st.session_state.principal
    st.metric("累積總損益", f"${pnl:,.0f}", f"{(pnl/st.session_state.principal*100 if st.session_state.principal>0 else 0):.2f}%")

st.divider()

# 表格與圓餅圖
col_p, col_t = st.columns([1, 2])
with col_p:
    if total_mkt > 0:
        fig = go.Figure(data=[go.Pie(labels=['股票', '槓桿', '類現金'], values=[s_val, l_val, b_val+c_val], marker=dict(colors=['#58a6ff', '#bc8cff', '#3fb950']), hole=.5)])
        fig.update_layout(template="plotly_dark", margin=dict(t=0,b=0,l=0,r=0), paper_bgcolor='rgba(0,0,0,0)')
        st.plotly_chart(fig, use_container_width=True)
with col_t:
    st.subheader("📋 目前庫存清單")
    df_rows = pd.DataFrame(rows)
    df_rows['市值'] = df_rows['市值'].apply(lambda x: f"${x:,.0f}")
    st.dataframe(df_rows, use_container_width=True, hide_index=True)

with st.sidebar:
    st.header("⚙️ 標的管理")
    add_id = st.text_input("新增代號").upper().strip()
    if st.button("➕ 新增入池並存檔"):
        if add_id: 
            st.session_state.stocks[add_id] = {"sh": 0.0, "co": 0.0}
            save_data_to_gs(st.session_state.stocks, st.session_state.principal)
            st.rerun()
    st.divider()
    if list(st.session_state.stocks.keys()):
        target = st.selectbox("修改標的", options=list(st.session_state.stocks.keys()))
        new_sh = st.number_input("持有股數", value=float(st.session_state.stocks[target]["sh"]))
        new_co = st.number_input("平均成本", value=float(st.session_state.stocks[target]["co"]))
        if st.button("💾 儲存修改內容"):
            st.session_state.stocks[target] = {"sh": new_sh, "co": new_co}
            save_data_to_gs(st.session_state.stocks, st.session_state.principal)
            st.rerun()
