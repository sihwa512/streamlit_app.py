import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
import gspread
from google.oauth2.service_account import Credentials

# --- 1. 頁面基本設定 ---
st.set_page_config(page_title="綜合退休戰情室 V72.0", layout="wide")

# --- 2. 核心雲端連線邏輯 (加入自動修正補丁) ---
def get_gspread_client():
    try:
        scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        # 讀取 Secrets 並轉為字典
        creds_info = dict(st.secrets["gcp_service_account"])
        
        # 🌟 關鍵修復：自動處理私鑰中的換行符號，防止 InvalidByte 錯誤
        if "private_key" in creds_info:
            creds_info["private_key"] = creds_info["private_key"].replace("\\n", "\n")
            
        creds = Credentials.from_service_account_info(creds_info, scopes=scope)
        return gspread.authorize(creds)
    except Exception as e:
        st.sidebar.error(f"❌ Google 授權失效: {e}")
        return None

def load_data_from_gs():
    client = get_gspread_client()
    if not client: return {"CASH": {"sh": 0.0, "co": 1.0}}, 0.0
    try:
        doc = client.open("Retirement_Cloud_Data")
        # 讀取 Stocks 分頁
        ws_stocks = doc.worksheet("Stocks")
        stock_data = ws_stocks.get_all_records()
        stocks = {str(r['id']).upper().strip(): {"sh": float(r['sh']), "co": float(r['co'])} for r in stock_data} if stock_data else {"CASH": {"sh": 0.0, "co": 1.0}}
        
        # 讀取 Settings 分頁中的本金
        try:
            ws_set = doc.worksheet("Settings")
            set_data = ws_set.get_all_records()
            principal = float(next((i['value'] for i in set_data if i['key'] == 'principal'), 0.0))
        except: principal = 0.0
            
        return stocks, principal
    except Exception as e:
        st.sidebar.warning(f"雲端讀取異常: {e}")
        return {"CASH": {"sh": 0.0, "co": 1.0}}, 0.0

def save_data_to_gs(stocks, principal):
    client = get_gspread_client()
    if not client: 
        st.error("無法同步至雲端，請檢查金鑰權限。")
        return
    try:
        doc = client.open("Retirement_Cloud_Data")
        # 寫入持股
        ws_stocks = doc.worksheet("Stocks")
        stock_list = [["id", "sh", "co"]] + [[sid, v['sh'], v['co']] for sid, v in stocks.items()]
        ws_stocks.update(values=stock_list, range_name="A1")
        
        # 寫入本金設定
        try:
            ws_set = doc.worksheet("Settings")
            ws_set.update(values=[["key", "value"], ["principal", principal]], range_name="A1")
        except: pass
        
        st.toast("🚀 雲端同步成功！")
        st.cache_data.clear() # 強制報價重新整理
    except Exception as e:
        st.error(f"同步失敗: {e}")

# --- 3. 視覺樣式 CSS ---
st.markdown("""
    <style>
    .stApp { background-color: #0d1117; color: #c9d1d9; }
    [data-testid="stMetricValue"] > div { 
        color: #00d4ff !important; 
        font-family: 'Consolas', monospace !important; 
        font-size: 2.2rem !important; 
        font-weight: bold !important; 
    }
    .stat-card { 
        text-align: center; padding: 15px; background: #161b22; 
        border-radius: 12px; border: 1px solid #30363d; border-top: 5px solid #58a6ff; 
    }
    </style>
    """, unsafe_allow_html=True)

# --- 4. 報價引擎 ---
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

# --- 5. 數據核心邏輯 ---
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
    roi = ((p - v['co']) / v['co'] * 100) if v['co'] > 0 else 0
    rows.append({
        "標的": sid, "名稱": name, "現價": f"{p:,.2f}", 
        "股數": f"{v['sh']:,.0f}", "市值": m, 
        "損益": f"{unrealized:,.0f}", "報酬率": f"{roi:.2f}%"
    })

# --- 6. 主介面呈現 ---
st.title("📊 綜合退休戰情室 V72.0")

col1, col2, col3 = st.columns(3)
with col1: st.metric("資產總市值", f"${total_mkt:,.0f}")
with col2: 
    new_p = st.number_input("設定投入總本金", value=float(st.session_state.principal), step=1000.0)
    if st.button("💾 儲存本金設定"):
        st.session_state.principal = new_p
        save_data_to_gs(st.session_state.stocks, new_p)
with col3:
    pnl = total_mkt - st.session_state.principal
    pct = (pnl / st.session_state.principal * 100) if st.session_state.principal > 0 else 0
    st.metric("真實累積總損益", f"${pnl:,.0f}", f"{pct:.2f}%")

st.divider()

# 現況方塊
c1, c2, c3 = st.columns(3)
with c1: st.markdown(f"<div class='stat-card'><small>現況 股票</small><br><b style='font-size:24px;'>{(s_val/total_mkt*100 if total_mkt>0 else 0):.1f}%</b><br><b>${s_val:,.0f}</b></div>", unsafe_allow_html=True)
with c2: st.markdown(f"<div class='stat-card' style='border-top-color:#bc8cff;'><small>現況 槓桿</small><br><b style='font-size:24px; color:#bc8cff;'>{(l_val/total_mkt*100 if total_mkt>0 else 0):.1f}%</b><br><b style='color:#bc8cff;'>${l_val:,.0f}</b></div>", unsafe_allow_html=True)
with c3: st.markdown(f"<div class='stat-card' style='border-top-color:#3fb950;'><small>現況 類現金</small><br><b style='font-size:24px; color:#3fb950;'>{((b_val+c_val)/total_mkt*100 if total_mkt>0 else 0):.1f}%</b><br><b style='color:#3fb950;'>${(b_val+c_val):,.0f}</b></div>", unsafe_allow_html=True)

st.divider()

# 圖表與庫存
col_pie, col_table = st.columns([1, 2])
with col_pie:
    if total_mkt > 0:
        fig = go.Figure(data=[go.Pie(labels=['股票', '槓桿', '類現金'], values=[s_val, l_val, b_val+c_val], marker=dict(colors=['#58a6ff', '#bc8cff', '#3fb950']), hole=.5)])
        fig.update_layout(template="plotly_dark", margin=dict(t=0,b=0,l=0,r=0), paper_bgcolor='rgba(0,0,0,0)')
        st.plotly_chart(fig, use_container_width=True)
with col_table:
    st.subheader("📋 目前標的庫存清單")
    df_rows = pd.DataFrame(rows)
    df_rows['市值'] = df_rows['市值'].apply(lambda x: f"${x:,.0f}")
    st.dataframe(df_rows, use_container_width=True, hide_index=True)

# 側邊欄
with st.sidebar:
    st.header("⚙️ 標的管理")
    if st.button("🔄 強制刷新報價"):
        st.cache_data.clear()
        st.rerun()
    st.divider()
    add_id = st.text_input("新增代號 (如 2330)").upper().strip()
    if st.button("➕ 新增入池"):
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
