import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
import gspread
from google.oauth2.service_account import Credentials

# --- 頁面設定 ---
st.set_page_config(page_title="綜合退休戰情室 V71.3", layout="wide")

# --- 1. Google Sheets 核心穩定連接 ---
GS_FILENAME = "Retirement_Cloud_Data"
GS_SHEETNAME = "Stocks"

def get_gspread_client():
    try:
        # 從 Secrets 讀取 (請確保 Secrets 已設定正確)
        scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds_dict = st.secrets["gcp_service_account"]
        creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
        return gspread.authorize(creds)
    except Exception as e:
        st.error(f"連線權限錯誤: {e}")
        return None

def load_data_from_gs():
    client = get_gspread_client()
    if not client: return {"CASH": {"sh": 0.0, "co": 1.0}}
    try:
        sh = client.open(GS_FILENAME).worksheet(GS_SHEETNAME)
        data = sh.get_all_records()
        stocks = {}
        if data:
            for row in data:
                sid = str(row['id']).upper().strip()
                stocks[sid] = {"sh": float(row.get('sh', 0)), "co": float(row.get('co', 0))}
        else:
            stocks = {"CASH": {"sh": 0.0, "co": 1.0}}
        return stocks
    except Exception as e:
        st.warning(f"讀取雲端失敗 ({e})，使用本地暫存數據。")
        return st.session_state.get('stocks', {"CASH": {"sh": 0.0, "co": 1.0}})

def save_data_to_gs(stocks):
    client = get_gspread_client()
    if not client: return
    try:
        sh = client.open(GS_FILENAME).worksheet(GS_SHEETNAME)
        # 轉換資料格式
        data_list = [["id", "sh", "co"]]
        for sid, v in stocks.items():
            data_list.append([sid, float(v['sh']), float(v['co'])])
        
        # 使用極速更新模式
        sh.update("A1", data_list)
        st.toast("✅ 數據已即時同步至雲端")
        st.cache_data.clear() # 強制報價重新整理
    except Exception as e:
        st.error(f"⚠️ 雲端存檔中斷: {e}")

# --- 2. 戰情室視覺 CSS ---
st.markdown("""
    <style>
    .stApp { background-color: #0d1117; color: #c9d1d9; }
    [data-testid="stMetricValue"] > div { color: #00d4ff !important; font-family: 'Consolas', monospace !important; font-size: 2.2rem !important; font-weight: 800 !important; }
    .stMetric { background: #161b22; border: 1px solid #30363d; border-radius: 12px; padding: 20px !important; }
    .stat-card { text-align: center; padding: 15px; background: #161b22; border-radius: 12px; border: 1px solid #30363d; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. 自動報價處理 ---
@st.cache_data(ttl=600)
def fetch_price(symbol):
    if symbol == "CASH": return 1.0, "閒置現金"
    # 台灣標的名對照
    names = {"00662":"富邦NASDAQ", "00670L":"富邦NASDAQ正2", "00865B":"國泰美債1-3Y", "00631L":"50正2", "0050":"元大50", "2330":"台積電"}
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

# --- 4. 數據核心流程 ---
if 'stocks' not in st.session_state:
    st.session_state.stocks = load_data_from_gs()
if 'principal' not in st.session_state:
    st.session_state.principal = 0.0

total_mkt = 0.0
s_val, l_val, b_val, c_val = 0.0, 0.0, 0.0, 0.0
rows = []

# 建立表格數據
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
    rows.append({"標的": sid, "名稱": name, "現價": f"{p:,.2f}", "股數": f"{v['sh']:,.0f}", "市值": f"${m:,.0f}", "損益": f"{unrealized:,.0f}", "報酬率": f"{roi:.2f}%"})

safe_val = b_val + c_val

# --- 5. 畫面呈現 ---
st.title("📊 綜合退休戰情室 V71.3")

col1, col2, col3 = st.columns(3)
with col1: st.metric("資產總市值", f"${total_mkt:,.0f}")
with col2: st.session_state.principal = st.number_input("設定投入總本金", value=float(st.session_state.principal))
with col3:
    pnl = total_mkt - st.session_state.principal
    pct = (pnl / st.session_state.principal * 100) if st.session_state.principal > 0 else 0
    st.metric("真實累積總損益", f"${pnl:,.0f}", f"{pct:.2f}%")

st.divider()

# 現況展示
c1, c2, c3 = st.columns(3)
def stat_box(label, color, val, pct):
    return f"<div class='stat-card' style='border-top:5px solid {color};'><small style='color:#8b949e;'>{label}</small><br><b style='color:{color}; font-size:26px;'>{pct:.1f}%</b><br><b style='color:{color}; font-size:24px;'>${val:,.0f}</b></div>"
with c1: st.markdown(stat_box("現況 股票", "#58a6ff", s_val, (s_val/total_mkt*100 if total_mkt>0 else 0)), unsafe_allow_html=True)
with c2: st.markdown(stat_box("現況 槓桿", "#bc8cff", l_val, (l_val/total_mkt*100 if total_mkt>0 else 0)), unsafe_allow_html=True)
with c3: st.markdown(stat_box("現況 類現金", "#3fb950", safe_val, (safe_val/total_mkt*100 if total_mkt>0 else 0)), unsafe_allow_html=True)

st.divider()

# 圓餅圖與表格
col_p, col_t = st.columns([1, 2])
with col_p:
    fig = go.Figure(data=[go.Pie(labels=['股票', '槓桿', '債券', '現金'], values=[s_val, l_val, b_val, c_val], marker=dict(colors=['#58a6ff', '#bc8cff', '#ff9f1c', '#3fb950']), hole=.5)])
    fig.update_layout(template="plotly_dark", margin=dict(t=0,b=0,l=0,r=0), paper_bgcolor='rgba(0,0,0,0)')
    st.plotly_chart(fig, use_container_width=True)
with col_t:
    st.subheader("📋 目前標的庫存")
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

# 側邊欄控制
with st.sidebar:
    st.header("⚙️ 雲端中心")
    if st.button("🚀 強制刷新 (清除暫存)"):
        st.cache_data.clear()
        st.session_state.stocks = load_data_from_gs()
        st.rerun()
    st.divider()
    add_id = st.text_input("新增代號").upper().strip()
    if st.button("➕ 新增標的"):
        if add_id: st.session_state.stocks[add_id] = {"sh": 0.0, "co": 0.0}; save_data_to_gs(st.session_state.stocks); st.rerun()
    st.divider()
    if list(st.session_state.stocks.keys()):
        target = st.selectbox("修改標的", options=list(st.session_state.stocks.keys()))
        new_sh = st.number_input("持有股數", value=float(st.session_state.stocks[target]["sh"]))
        new_co = st.number_input("平均成本", value=float(st.session_state.stocks[target]["co"]))
        if st.button("💾 儲存修改"):
            st.session_state.stocks[target] = {"sh": new_sh, "co": new_co}
            save_data_to_gs(st.session_state.stocks)
            st.rerun()
