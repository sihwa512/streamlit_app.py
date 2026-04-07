import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
import gspread
from google.oauth2.service_account import Credentials
import re

# --- 1. 頁面設定 ---
st.set_page_config(page_title="綜合退休戰情室 V73.6", layout="wide")

# --- 2. 雲端連線設定 (ID 已固定) ---
GS_ID = "1jgZhEi-nmaXGUa5fJaYwk79xE9-QG4LwhwV89xriGPs" 

def get_client():
    try:
        scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        s = st.secrets["gcp_service_account"]
        
        # 🌟 關鍵修正邏輯：自動將 \n 轉為真正的換行符號
        pk = s["private_key"]
        # 處理 JSON 格式複製過來的反斜線
        if "\\n" in pk:
            pk = pk.replace("\\n", "\n")
        
        # 移除可能存在的特殊引號或空格
        pk = pk.strip()
        
        creds_dict = {
            "type": s["type"],
            "project_id": s["project_id"],
            "private_key_id": s["private_key_id"],
            "private_key": pk,
            "client_email": s["client_email"],
            "client_id": s["client_id"],
            "auth_uri": s["auth_uri"],
            "token_uri": s["token_uri"],
            "auth_provider_x509_cert_url": s["auth_provider_x509_cert_url"],
            "client_x509_cert_url": s["client_x509_cert_url"]
        }
        return gspread.authorize(Credentials.from_service_account_info(creds_dict, scopes=scope))
    except Exception as e:
        st.sidebar.error("❌ 金鑰授權失敗，請重新確認 Secrets")
        st.sidebar.code(str(e))
        return None

def load_data():
    client = get_client()
    # 預設數據，保證 Google 連線失敗時畫面不全黑
    def_s = {"CASH": {"sh": 200000.0, "co": 1.0}}
    def_p = 50000.0
    if not client: return def_s, def_p
    try:
        doc = client.open_by_key(GS_ID)
        # 讀取 Stocks 分頁
        ws_s = doc.worksheet("Stocks")
        all_v = ws_s.get_all_values()
        stocks = {}
        if len(all_v) > 1:
            for r in all_v[1:]:
                if r[0]: stocks[str(r[0]).upper().strip()] = {"sh": float(r[1] or 0), "co": float(r[2] or 0)}
        else: stocks = def_s
        # 讀取本金設定
        try:
            ws_v = doc.worksheet("Settings")
            v_v = ws_v.get_all_values()
            p = float(v_v[1][1]) if len(v_v) > 1 else def_p
        except: p = def_p
        return stocks, p
    except: return def_s, def_p

def save_data(stocks, principal):
    client = get_client()
    if not client: 
        st.error("❌ 無法連線雲端，請檢查 Secrets。")
        return
    try:
        doc = client.open_by_key(GS_ID)
        # 1. 寫入持股
        ws_s = doc.worksheet("Stocks")
        ws_s.clear()
        data_s = [["id", "sh", "co"]] + [[k, float(v['sh']), float(v['co'])] for k, v in stocks.items()]
        ws_s.update(values=data_s, range_name='A1')
        # 2. 寫入本金
        ws_v = doc.worksheet("Settings")
        ws_v.clear()
        ws_v.update(values=[["key", "value"], ["principal", float(principal)]], range_name='A1')
        st.success("✅ 雲端同步完成！")
        st.cache_data.clear()
    except Exception as e: st.error(f"❌ 同步失敗: {e}")

# --- 3. 視覺樣式與 CSS ---
st.markdown("<style>.stApp{background-color:#0d1117; color:#c9d1d9;} [data-testid='stMetricValue']>div{color:#00d4ff!important; font-weight:800; font-size:2.6rem!important;} .stat-card{text-align:center; padding:20px; background:#161b22; border-radius:12px; border-top:6px solid #58a6ff; margin-bottom:15px;}</style>", unsafe_allow_html=True)

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

# --- 4. 計算數據 ---
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

# --- 5. 主介面 ---
st.title("📊 綜合退休戰情室 V73.6")

col1, col2, col3 = st.columns(3)
with col1: st.metric("總市值", f"${total_mkt:,.0f}")
with col2: 
    st.session_state.principal = st.number_input("本金設定", value=float(st.session_state.principal))
    if st.button("💾 同步本金設定"): save_data(st.session_state.stocks, st.session_state.principal)
with col3:
    pnl_val = total_mkt - st.session_state.principal
    pct = (pnl_val / st.session_state.principal * 100) if st.session_state.principal > 0 else 0
    st.metric("總損益", f"${pnl_val:,.0f}", f"{pct:.2f}%")

st.divider()

# 現況方塊
c1, c2, c3 = st.columns(3)
def draw_card(title, color, val):
    p = (val / total_mkt * 100) if total_mkt > 0 else 0
    st.markdown(f"<div class='stat-card' style='border-top-color:{color};'><small style='color:#8b949e;'>{title}</small><br><b style='color:{color}; font-size:26px;'>{p:.1f}%</b><br><b style='color:{color}; font-size:24px;'>${val:,.0f}</b></div>", unsafe_allow_html=True)

with c1: draw_card("現況 股票", "#58a6ff", s_val)
with c2: draw_card("現況 槓桿", "#bc8cff", l_val)
with c3: draw_card("現況 類現金", "#3fb950", b_val + c_val)

st.divider()
st.subheader("📋 目前持股明細")
df_d = pd.DataFrame(rows)
df_d['市值'] = df_d['市值'].apply(lambda x: f"${x:,.0f}")
st.dataframe(df_d, use_container_width=True, hide_index=True)

with st.sidebar:
    st.header("⚙️ 雲端操作")
    new_id = st.text_input("➕ 新增代號").upper().strip()
    if st.button("確認加入"):
        if new_id:
            st.session_state.stocks[new_id] = {"sh": 0.0, "co": 0.0}
            save_data(st.session_state.stocks, st.session_state.principal)
            st.rerun()
    st.divider()
    target = st.selectbox("修改標的", options=list(st.session_state.stocks.keys()))
    n_sh = st.number_input("股數", value=float(st.session_state.stocks[target]["sh"]))
    n_co = st.number_input("成本", value=float(st.session_state.stocks[target]["co"]))
    if st.button("💾 儲存修改"):
        st.session_state.stocks[target] = {"sh": n_sh, "co": n_co}
        save_data(st.session_state.stocks, st.session_state.principal)
        st.rerun()
