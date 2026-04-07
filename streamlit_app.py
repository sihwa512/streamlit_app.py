import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
import gspread
from google.oauth2.service_account import Credentials

# --- 頁面設定 ---
st.set_page_config(page_title="綜合退休戰情室 V70.5", layout="wide")

# --- 1. Google Sheets 連接邏輯 ---
# 這裡已經幫您設定好試算表名稱
GS_FILENAME = "Retirement_Cloud_Data"
GS_SHEETNAME = "Stocks"

def get_gspread_client():
    # 從 Streamlit Secrets 讀取 GCP 金鑰 (請確保 Secrets 已填寫)
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds_dict = st.secrets["gcp_service_account"]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
    return gspread.authorize(creds)

def load_data_from_gs():
    try:
        client = get_gspread_client()
        sh = client.open(GS_FILENAME).worksheet(GS_SHEETNAME)
        df = pd.DataFrame(sh.get_all_records())
        # 將資料轉為 session_state 格式
        stocks = {}
        if not df.empty:
            for _, row in df.iterrows():
                stocks[str(row['id']).upper()] = {"sh": float(row['sh']), "co": float(row['co'])}
        else:
            stocks = {"CASH": {"sh": 0.0, "co": 1.0}}
        return stocks
    except Exception as e:
        st.error(f"連線 Google Sheets 失敗: {e}。請確認試算表名稱為 '{GS_FILENAME}' 且已分享權限給服務帳號 Email。")
        return {"CASH": {"sh": 0.0, "co": 1.0}}

def save_data_to_gs(stocks):
    try:
        client = get_gspread_client()
        sh = client.open(GS_FILENAME).worksheet(GS_SHEETNAME)
        # 轉換為列表寫入
        data_to_save = [["id", "sh", "co"]]
        for sid, v in stocks.items():
            data_to_save.append([sid, v['sh'], v['co']])
        sh.clear()
        sh.update("A1", data_to_save)
        st.toast("✅ 數據已成功存入雲端表格")
    except Exception as e:
        st.error(f"存檔失敗: {e}")

# --- 2. 靈魂 CSS：還原單機網頁版質感 ---
st.markdown("""
    <style>
    .stApp { background-color: #0f111a; color: #e0e0e0; }
    [data-testid="stMetric"] {
        background: linear-gradient(145deg, #1b1e2e, #161926);
        border: 1px solid #333; border-radius: 15px; padding: 15px !important;
        box-shadow: 0 4px 15px rgba(0,0,0,0.4);
    }
    [data-testid="stMetricLabel"] > div { color: #aaa !important; font-weight: bold !important; }
    [data-testid="stMetricValue"] > div { font-family: 'Consolas', monospace; color: #00d4ff !important; font-size: 1.8rem !important; }
    .stNumberInput input { background-color: #252836 !important; color: white !important; border: 1px solid #555 !important; border-radius: 8px !important; }
    hr { border: 0; border-top: 1px dashed #444; }
    h1, h2, h3 { color: #00d4ff !important; font-weight: 700 !important; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. 核心運算 ---
@st.cache_data(ttl=3600)
def get_price(symbol):
    if symbol == "CASH": return 1.0, "現金部位"
    try:
        s = symbol if "." in symbol else f"{symbol}.TW"
        t = yf.Ticker(s)
        return t.fast_info.last_price, t.info.get('shortName', symbol)
    except: return 0.0, symbol

# 首次載入 (從雲端讀取)
if 'stocks' not in st.session_state:
    st.session_state.stocks = load_data_from_gs()
if 'principal' not in st.session_state:
    st.session_state.principal = 0.0

total_mkt = 0.0
s_val, l_val, b_val, c_val = 0.0, 0.0, 0.0, 0.0
processed_rows = []

for sid, v in st.session_state.stocks.items():
    price, name = get_price(sid)
    mkt = v['sh'] * price
    total_mkt += mkt
    if sid == "CASH": c_val += mkt
    elif "B" in sid: b_val += mkt
    elif "L" in sid: l_val += mkt
    else: s_val += mkt
    processed_rows.append({"標的": sid, "名稱": name, "現價": round(price,2), "股數": v['sh'], "市值": round(mkt,0)})

safe_val = b_val + c_val

# --- 4. 介面呈現 ---
st.title("📊 綜合退休戰情室 V70.5 Cloud")

col1, col2, col3 = st.columns(3)
with col1: st.metric("資產總市值", f"${total_mkt:,.0f}")
with col2:
    st.markdown("<small style='color:#aaa;'>投入總本金</small>", unsafe_allow_html=True)
    st.session_state.principal = st.number_input("P_Input", value=float(st.session_state.principal), label_visibility="collapsed")
with col3:
    true_pnl = total_mkt - st.session_state.principal
    pnl_pct = (true_pnl / st.session_state.principal * 100) if st.session_state.principal > 0 else 0
    st.metric("真實累積總損益", f"${true_pnl:,.0f}", f"{pnl_pct:.2f}%")

st.divider()

# 現況方塊 (還原配色)
st.subheader("⚖️ 目標再平衡對照")
cur1, cur2, cur3 = st.columns(3)
def card_html(label, color, pct, val):
    return f"<div style='text-align:center; padding:15px; background:rgba(255,255,255,0.03); border-radius:12px; border:1px solid {color}44;'><small style='color:#aaa;'>{label}</small><br><b style='color:{color}; font-size:26px;'>{pct:.1f}%</b><br><b style='color:{color}; font-size:22px;'>${val:,.0f}</b></div>"

with cur1: st.markdown(card_html("現況 股票", "#00d4ff", (s_val/total_mkt*100 if total_mkt>0 else 0), s_val), unsafe_allow_html=True)
with cur2: st.markdown(card_html("現況 槓桿", "#bd93f9", (l_val/total_mkt*100 if total_mkt>0 else 0), l_val), unsafe_allow_html=True)
with cur3: st.markdown(card_html("現況 類現金", "#00ff88", (safe_val/total_mkt*100 if total_mkt>0 else 0), safe_val), unsafe_allow_html=True)

st.write("")
t_col1, t_col2, t_col3 = st.columns(3)
with t_col1: 
    ts = st.number_input("目標 股票 %", value=40)
    st.markdown(f"<div style='text-align:center;'><b style='color:#00d4ff; font-size:18px;'>目標: ${total_mkt * ts/100:,.0f}</b></div>", unsafe_allow_html=True)
with t_col2: 
    tl = st.number_input("目標 槓桿 %", value=30)
    st.markdown(f"<div style='text-align:center;'><b style='color:#bd93f9; font-size:18px;'>目標: ${total_mkt * tl/100:,.0f}</b></div>", unsafe_allow_html=True)
with t_col3: 
    t_safe_pct = 100 - ts - tl
    st.markdown(f"<div style='text-align:center; padding-top:10px;'><small style='color:#aaa;'>目標 類現金</small><br><b style='color:#00ff88; font-size:24px;'>{t_safe_pct}%</b><br><b style='color:#00ff88; font-size:18px;'>目標: ${total_mkt * t_safe_pct/100:,.0f}</b></div>", unsafe_allow_html=True)

st.divider()

# 圖表區
c_pie, c_table = st.columns([1, 1.5])
with c_pie:
    st.subheader("🍩 資產配置佔比")
    fig = go.Figure(data=[go.Pie(labels=['股票', '槓桿', '債券', '現金'], values=[s_val, l_val, b_val, c_val], marker=dict(colors=['#00d4ff', '#bd93f9', '#ff9f1c', '#00ff88']), hole=.4)])
    fig.update_layout(template="plotly_dark", margin=dict(t=0,b=0,l=0,r=0))
    st.plotly_chart(fig, use_container_width=True)

with c_table:
    st.subheader("📋 目前庫存清單")
    st.dataframe(pd.DataFrame(processed_rows), use_container_width=True, hide_index=True)

# --- 5. 側邊欄管理 (雲端同步) ---
with st.sidebar:
    st.header("⚙️ 雲端數據控制")
    if st.button("🔄 從 Google Sheets 重新同步"):
        st.session_state.stocks = load_data_from_gs()
        st.rerun()
    
    st.divider()
    add_id = st.text_input("新增代號 (如 00662 / CASH)").upper()
    if st.button("➕ 新增入池並存檔"):
        if add_id:
            st.session_state.stocks[add_id] = {"sh": 0.0, "co": 0.0}
            save_data_to_gs(st.session_state.stocks)
            st.rerun()

    st.divider()
    st.write("📊 **庫存數據修改**")
    if list(st.session_state.stocks.keys()):
        target_stk = st.selectbox("選取標的", options=list(st.session_state.stocks.keys()))
        new_sh = st.number_input("持有股數/金額", value=float(st.session_state.stocks[target_stk]["sh"]))
        if st.button("💾 儲存修改至雲端"):
            st.session_state.stocks[target_stk]["sh"] = new_sh
            save_data_to_gs(st.session_state.stocks)
            st.rerun()

    st.divider()
    if st.button("🗑️ 系統重置", type="primary"):
        st.session_state.stocks = {"CASH": {"sh": 0.0, "co": 1.0}}
        save_data_to_gs(st.session_state.stocks)
        st.rerun()
