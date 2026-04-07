import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
import gspread
from google.oauth2.service_account import Credentials

# --- 頁面設定 ---
st.set_page_config(page_title="綜合退休戰情室 V71.0", layout="wide")

# --- 1. Google Sheets 連接邏輯 ---
GS_FILENAME = "Retirement_Cloud_Data"
GS_SHEETNAME = "Stocks"

def get_gspread_client():
    try:
        scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds_dict = st.secrets["gcp_service_account"]
        creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
        return gspread.authorize(creds)
    except: return None

def load_data_from_gs():
    client = get_gspread_client()
    if not client: return {"CASH": {"sh": 0.0, "co": 1.0}}
    try:
        sh = client.open(GS_FILENAME).worksheet(GS_SHEETNAME)
        df = pd.DataFrame(sh.get_all_records())
        stocks = {}
        if not df.empty:
            for _, row in df.iterrows():
                sid = str(row['id']).upper().strip()
                stocks[sid] = {"sh": float(row['sh']), "co": float(row['co'])}
        return stocks
    except: return {"CASH": {"sh": 0.0, "co": 1.0}}

def save_data_to_gs(stocks):
    client = get_gspread_client()
    if not client: return
    try:
        sh = client.open(GS_FILENAME).worksheet(GS_SHEETNAME)
        data = [["id", "sh", "co"]]
        for sid, v in stocks.items(): data.append([sid, v['sh'], v['co']])
        sh.clear(); sh.update("A1", data)
        st.toast("✅ 數據同步完成")
    except: st.error("❌ 雲端存檔失敗")

# --- 2. 靈魂 CSS：解決字體太淡問題 ---
st.markdown("""
    <style>
    .stApp { background-color: #0d1117; color: #c9d1d9; }
    
    /* 核心指標字體強化：解決太淡的問題 */
    [data-testid="stMetricValue"] > div {
        color: #00d4ff !important; 
        font-family: 'Consolas', monospace !important;
        font-size: 2.2rem !important;
        font-weight: 800 !important;
        opacity: 1 !important; /* 強制不透明 */
    }
    [data-testid="stMetricLabel"] > div {
        color: #ffffff !important;
        font-weight: bold !important;
        opacity: 0.9 !important;
    }
    
    /* 方塊容器美化 */
    [data-testid="stMetric"] {
        background: #161b22;
        border: 1px solid #30363d;
        border-radius: 12px;
        padding: 20px !important;
    }

    .stat-card {
        text-align: center; 
        padding: 15px; 
        background: #161b22; 
        border-radius: 12px; 
        border: 1px solid #30363d;
    }
    
    h1, h2, h3 { color: #58a6ff !important; }
    
    /* 隱藏標題後面的連結符號 */
    .stMarkdown a { text-decoration: none; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. 股票中文簡稱對照表 ---
STOCK_NAMES = {
    "00662": "富邦NASDAQ",
    "00670L": "富邦NASDAQ正2",
    "00865B": "國泰美債1-3Y",
    "00631L": "元大台灣50正2",
    "0050": "元大台灣50",
    "2330": "台積電",
    "CASH": "閒置現金"
}

def fetch_price(symbol):
    if symbol == "CASH": return 1.0, STOCK_NAMES.get("CASH")
    
    display_name = STOCK_NAMES.get(symbol, symbol) # 優先使用自訂簡稱
    
    for suf in [".TW", ".TWO", ""]:
        try:
            t = yf.Ticker(f"{symbol}{suf}")
            p = t.fast_info.last_price
            if p > 0: return p, display_name
            h = t.history(period="1d")
            if not h.empty: return h['Close'].iloc[-1], display_name
        except: continue
    return 0.0, display_name

# --- 4. 初始化 ---
if 'stocks' not in st.session_state: st.session_state.stocks = load_data_from_gs()
if 'principal' not in st.session_state: st.session_state.principal = 0.0

total_mkt = 0.0
s_val, l_val, b_val, c_val = 0.0, 0.0, 0.0, 0.0
rows = []

for sid, v in st.session_state.stocks.items():
    p, name = fetch_price(sid)
    m = v['sh'] * p
    total_mkt += m
    if sid == "CASH": c_val += m
    elif "B" in sid: b_val += m
    elif "L" in sid: l_val += m
    else: s_val += m
    rows.append({"標的": sid, "名稱": name, "現價": f"{p:,.2f}", "股數": f"{v['sh']:,.0f}", "市值": m})

safe_val = b_val + c_val

# --- 🚀 主介面佈局 ---
st.title("📊 綜合退休戰情室 V71.0")

# 第一列：核心指標 (現在字體會非常清晰)
m1, m2, m3 = st.columns(3)
with m1: st.metric("資產總市值", f"${total_mkt:,.0f}")
with m2: 
    # 本金輸入框美化
    st.markdown("<small style='color:#aaa;'>設定投入總本金</small>", unsafe_allow_html=True)
    st.session_state.principal = st.number_input("Principal_Input", value=float(st.session_state.principal), label_visibility="collapsed")
with m3:
    true_pnl = total_mkt - st.session_state.principal
    pnl_pct = (true_pnl / st.session_state.principal * 100) if st.session_state.principal > 0 else 0
    # 損益顏色強化
    pnl_label = "累積淨獲利"
    st.metric(pnl_label, f"${true_pnl:,.0f}", f"{pnl_pct:.2f}%")

st.divider()

# 第二列：再平衡對照區
st.subheader("⚖️ 目標再平衡對照")
curr_beta = (s_val/total_mkt * 1.0 + l_val/total_mkt * 2.0) if total_mkt > 0 else 0
st.markdown(f"當前組合 Beta: <b style='color:#bc8cff; font-size:1.2rem;'>{curr_beta:.2f}</b>", unsafe_allow_html=True)

c1, c2, c3 = st.columns(3)
def stat_box(label, color, val, pct):
    return f"""<div class='stat-card' style='border-top: 5px solid {color};'>
        <small style='color:#8b949e; font-weight:bold;'>{label}</small><br>
        <b style='color:{color}; font-size:28px;'>{pct:.1f}%</b><br>
        <b style='color:{color}; font-size:24px;'>${val:,.0f}</b>
    </div>"""

with c1: st.markdown(stat_box("現況 股票", "#58a6ff", s_val, (s_val/total_mkt*100 if total_mkt>0 else 0)), unsafe_allow_html=True)
with c2: st.markdown(stat_box("現況 槓桿", "#bc8cff", l_val, (l_val/total_mkt*100 if total_mkt>0 else 0)), unsafe_allow_html=True)
with c3: st.markdown(stat_box("現況 類現金", "#3fb950", safe_val, (safe_val/total_mkt*100 if total_mkt>0 else 0)), unsafe_allow_html=True)

st.write("")
t1, t2, t3 = st.columns(3)
with t1: ts = st.number_input("目標 股票 %", value=40)
with t2: tl = st.number_input("目標 槓桿 %", value=30)
with t3:
    t_safe = 100 - ts - tl
    st.markdown(f"""<div style='text-align:center; padding:5px; background:rgba(63,185,80,0.1); border-radius:10px;'>
        <small style='color:#8b949e;'>目標 類現金</small><br>
        <b style='color:#3fb950; font-size:24px;'>{t_safe}%</b>
    </div>""", unsafe_allow_html=True)

st.markdown(f"""<div style='display:flex; justify-content:space-around; background:rgba(255,159,28,0.1); padding:12px; border-radius:8px; border: 1px solid #ff9f1c;'>
    <div style='color:#58a6ff; font-weight:bold;'>股票目標: ${total_mkt*ts/100:,.0f}</div>
    <div style='color:#bc8cff; font-weight:bold;'>槓桿目標: ${total_mkt*tl/100:,.0f}</div>
    <div style='color:#3fb950; font-weight:bold;'>類現金目標: ${total_mkt*t_safe/100:,.0f}</div>
</div>""", unsafe_allow_html=True)

st.divider()

# 第三列：圖表與表格
col_pie, col_table = st.columns([1, 1.5])
with col_pie:
    st.subheader("🍩 資產配置佔比")
    if total_mkt > 0:
        fig = go.Figure(data=[go.Pie(labels=['股票', '槓桿', '債券', '現金'], values=[s_val, l_val, b_val, c_val], 
                                     marker=dict(colors=['#58a6ff', '#bc8cff', '#ff9f1c', '#3fb950']), hole=.5)])
        fig.update_layout(template="plotly_dark", margin=dict(t=0,b=0,l=0,r=0), showlegend=True, paper_bgcolor='rgba(0,0,0,0)')
        st.plotly_chart(fig, use_container_width=True)

with col_table:
    st.subheader("📋 目前庫存清單")
    if rows:
        df = pd.DataFrame(rows)
        df['市值'] = df['市值'].apply(lambda x: f"${x:,.0f}")
        st.dataframe(df, use_container_width=True, hide_index=True)

# 側邊欄
with st.sidebar:
    st.header("⚙️ 標的管理")
    add_id = st.text_input("新增代號").upper().strip()
    if st.button("➕ 新增入池"):
        if add_id: st.session_state.stocks[add_id] = {"sh": 0.0, "co": 0.0}; save_data_to_gs(st.session_state.stocks); st.rerun()
    st.divider()
    if list(st.session_state.stocks.keys()):
        target_stk = st.selectbox("修改標的", options=list(st.session_state.stocks.keys()))
        new_sh = st.number_input("持有股數", value=float(st.session_state.stocks[target_stk]["sh"]))
        if st.button("💾 儲存修改"): st.session_state.stocks[target_stk]["sh"] = new_sh; save_data_to_gs(st.session_state.stocks); st.rerun()
    st.divider()
    if st.button("🔄 強制重整報價"): st.cache_data.clear(); st.rerun()
