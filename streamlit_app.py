import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
import gspread
from google.oauth2.service_account import Credentials

# --- 頁面設定 ---
st.set_page_config(page_title="綜合退休戰情室 V71.9", layout="wide")

# --- 1. 安全連線邏輯 (防崩潰版) ---
def get_client():
    try:
        scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        # 強制修正 Secrets 讀取邏輯
        creds_info = st.secrets["gcp_service_account"]
        # 這裡會自動處理 private_key 中的換行符號
        return gspread.authorize(Credentials.from_service_account_info(creds_info, scopes=scope))
    except Exception as e:
        st.sidebar.error(f"⚠️ Google 授權失效: 請檢查 Secrets 格式\n({e})")
        return None

def load_data():
    client = get_client()
    if not client: return {"CASH": {"sh": 0.0, "co": 1.0}}, 0.0
    try:
        doc = client.open("Retirement_Cloud_Data")
        ws_s = doc.worksheet("Stocks")
        s_data = ws_s.get_all_records()
        stocks = {str(r['id']).upper().strip(): {"sh": float(r['sh']), "co": float(r['co'])} for r in s_data} if s_data else {"CASH": {"sh": 0.0, "co": 1.0}}
        try:
            ws_v = doc.worksheet("Settings")
            v_data = ws_v.get_all_records()
            principal = float(v_data[0]['value'])
        except: principal = 0.0
        return stocks, principal
    except: return {"CASH": {"sh": 0.0, "co": 1.0}}, 0.0

def save_to_cloud(stocks, principal):
    client = get_client()
    if not client: 
        st.error("❌ 無法連線雲端，數據僅儲存在本地，請修正 Secrets。")
        return
    try:
        doc = client.open("Retirement_Cloud_Data")
        # 寫入 Stocks
        ws_s = doc.worksheet("Stocks")
        s_list = [["id", "sh", "co"]] + [[k, v['sh'], v['co']] for k, v in stocks.items()]
        ws_s.update(values=s_list, range_name="A1")
        # 寫入 Settings
        try:
            ws_v = doc.worksheet("Settings")
            ws_v.update(values=[["key", "value"], ["principal", principal]], range_name="A1")
        except: pass
        st.success("🚀 雲端同步成功！")
    except Exception as e: st.error(f"❌ 寫入失敗: {e}")

# --- 2. 數據處理 ---
if 'stocks' not in st.session_state:
    st.session_state.stocks, st.session_state.principal = load_data()

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

# --- 3. 介面呈現 (還原完整畫面) ---
st.title("📊 綜合退休戰情室 V71.9")

col1, col2, col3 = st.columns(3)
with col1: st.metric("資產總市值", f"${total_mkt:,.0f}")
with col2: 
    st.session_state.principal = st.number_input("設定投入總本金", value=float(st.session_state.principal))
    if st.button("💾 儲存本金"): save_to_cloud(st.session_state.stocks, st.session_state.principal)
with col3:
    pnl = total_mkt - st.session_state.principal
    st.metric("真實累積總損益", f"${pnl:,.0f}", f"{(pnl/st.session_state.principal*100 if st.session_state.principal>0 else 0):.2f}%")

st.divider()

# 現況方塊
c1, c2, c3 = st.columns(3)
with c1: st.info(f"現況 股票: {(s_val/total_mkt*100 if total_mkt>0 else 0):.1f}% \n\n ${s_val:,.0f}")
with c2: st.warning(f"現況 槓桿: {(l_val/total_mkt*100 if total_mkt>0 else 0):.1f}% \n\n ${l_val:,.0f}")
with c3: st.success(f"現況 類現金: {((b_val+c_val)/total_mkt*100 if total_mkt>0 else 0):.1f}% \n\n ${(b_val+c_val):,.0f}")

st.divider()

# 圖表與明細
col_p, col_t = st.columns([1, 2])
with col_p:
    if total_mkt > 0:
        fig = go.Figure(data=[go.Pie(labels=['股票', '槓桿', '類現金'], values=[s_val, l_val, b_val+c_val], hole=.5)])
        fig.update_layout(template="plotly_dark", margin=dict(t=0,b=0,l=0,r=0), paper_bgcolor='rgba(0,0,0,0)')
        st.plotly_chart(fig, use_container_width=True)
with col_t:
    st.subheader("📋 持股明細")
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

with st.sidebar:
    st.header("⚙️ 雲端操作")
    add_id = st.text_input("新增代號").upper().strip()
    if st.button("➕ 加入並同步"):
        if add_id:
            st.session_state.stocks[add_id] = {"sh": 0.0, "co": 0.0}
            save_to_cloud(st.session_state.stocks, st.session_state.principal)
            st.rerun()
