import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
import gspread
from google.oauth2.service_account import Credentials
import re

# --- 1. 頁面設定 ---
st.set_page_config(page_title="綜合退休戰情室 V73.4", layout="wide")

# --- 2. 雲端連線設定 ---
GS_ID = "1jgZhEi-nmaXGUa5fJaYwk79xE9-QG4LwhwV89xriGPs"

def get_client():
    try:
        scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        # 🌟 核心修正：手動構造權限字典，強制轉換 \n
        s = st.secrets["gcp_service_account"]
        creds_dict = {
            "type": s["type"],
            "project_id": s["project_id"],
            "private_key_id": s["private_key_id"],
            "private_key": s["private_key"].replace("\\n", "\n"), # 關鍵：將字串中的反斜線n轉為換行
            "client_email": s["client_email"],
            "client_id": s["client_id"],
            "auth_uri": s["auth_uri"],
            "token_uri": s["token_uri"],
            "auth_provider_x509_cert_url": s["auth_provider_x509_cert_url"],
            "client_x509_cert_url": s["client_x509_cert_url"]
        }
        return gspread.authorize(Credentials.from_service_account_info(creds_dict, scopes=scope))
    except Exception as e:
        st.sidebar.error(f"連線失敗: {e}")
        return None

def load_data():
    client = get_client()
    # 安全預設值
    def_s = {"CASH": {"sh": 200000.0, "co": 1.0}}
    def_p = 50000.0
    if not client: return def_s, def_p
    try:
        doc = client.open_by_key(GS_ID)
        ws_s = doc.worksheet("Stocks")
        all_v = ws_s.get_all_values()
        stocks = {}
        if len(all_v) > 1:
            for r in all_v[1:]:
                if r[0]: stocks[str(r[0]).upper().strip()] = {"sh": float(r[1] or 0), "co": float(r[2] or 0)}
        else: stocks = def_s
        
        ws_v = doc.worksheet("Settings")
        v_v = ws_v.get_all_values()
        p = float(v_v[1][1]) if len(v_v) > 1 else def_p
        return stocks, p
    except: return def_s, def_p

def save_data(stocks, principal):
    client = get_client()
    if not client: return
    try:
        doc = client.open_by_key(GS_ID)
        # 更新持股
        ws_s = doc.worksheet("Stocks")
        ws_s.clear()
        data_s = [["id", "sh", "co"]] + [[k, float(v['sh']), float(v['co'])] for k, v in stocks.items()]
        ws_s.update('A1', data_s)
        # 更新本金
        ws_v = doc.worksheet("Settings")
        ws_v.clear()
        ws_v.update('A1', [["key", "value"], ["principal", float(principal)]])
        st.success("✅ 雲端同步成功！")
        st.cache_data.clear()
    except Exception as e: st.error(f"❌ 存檔失敗: {e}")

# --- 3. 視覺設定 ---
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

# --- 4. 計算 ---
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

# --- 5. 介面 ---
st.title("📊 綜合退休戰情室 V73.4")

col1, col2, col3 = st.columns(3)
with col1: st.metric("總市值", f"${total_mkt:,.0f}")
with col2: 
    st.session_state.principal = st.number_input("本金", value=float(st.session_state.principal))
    if st.button("💾 同步本金"): save_data(st.session_state.stocks, st.session_state.principal)
with col3:
    pnl_val = total_mkt - st.session_state.principal
    pct = (pnl_val / st.session_state.principal * 100) if st.session_state.principal > 0 else 0
    st.metric("總損益", f"${pnl_val:,.0f}", f"{pct:.2f}%")

st.divider()

# 現況方塊
c1, c2, c3 = st.columns(3)
def stat_box(label, color, val):
    p = (val / total_mkt * 100) if total_mkt > 0 else 0
    st.markdown(f"<div style='text-align:center; padding:20px; background:#161b22; border-radius:12px; border-top:6px solid {color};'><small style='color:#8b949e;'>{label}</small><br><b style='color:{color}; font-size:26px;'>{p:.1f}%</b><br><b style='color:{color}; font-size:24px;'>${val:,.0f}</b></div>", unsafe_allow_html=True)

with c1: stat_box("現況 股票", "#58a6ff", s_val)
with c2: stat_box("現況 槓桿", "#bc8cff", l_val)
with c3: stat_box("現況 類現金", "#3fb950", b_val + c_val)

st.divider()

# 表格
st.subheader("📋 目前持股明細")
df_display = pd.DataFrame(rows)
df_display['市值'] = df_display['市值'].apply(lambda x: f"${x:,.0f}")
st.dataframe(df_display, use_container_width=True, hide_index=True)

with st.sidebar:
    st.header("⚙️ 修改資料")
    target = st.selectbox("標的", options=list(st.session_state.stocks.keys()))
    new_sh = st.number_input("股數", value=float(st.session_state.stocks[target]["sh"]))
    new_co = st.number_input("成本", value=float(st.session_state.stocks[target]["co"]))
    if st.button("💾 儲存並強制同步"):
        st.session_state.stocks[target] = {"sh": new_sh, "co": new_co}
        save_data(st.session_state.stocks, st.session_state.principal)
        st.rerun()
