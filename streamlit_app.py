import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
import gspread
from google.oauth2.service_account import Credentials

# --- 頁面設定 ---
st.set_page_config(page_title="綜合退休戰情室 V70.6", layout="wide")

# --- 1. Google Sheets 連接邏輯 ---
GS_FILENAME = "Retirement_Cloud_Data"
GS_SHEETNAME = "Stocks"

def get_gspread_client():
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds_dict = st.secrets["gcp_service_account"]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
    return gspread.authorize(creds)

def load_data_from_gs():
    try:
        client = get_gspread_client()
        sh = client.open(GS_FILENAME).worksheet(GS_SHEETNAME)
        df = pd.DataFrame(sh.get_all_records())
        stocks = {}
        if not df.empty:
            for _, row in df.iterrows():
                sid = str(row['id']).upper().strip()
                stocks[sid] = {"sh": float(row['sh']), "co": float(row['co'])}
        else:
            stocks = {"CASH": {"sh": 0.0, "co": 1.0}}
        return stocks
    except Exception as e:
        st.error(f"連線 Google Sheets 失敗: {e}")
        return {"CASH": {"sh": 0.0, "co": 1.0}}

def save_data_to_gs(stocks):
    try:
        client = get_gspread_client()
        sh = client.open(GS_FILENAME).worksheet(GS_SHEETNAME)
        data_to_save = [["id", "sh", "co"]]
        for sid, v in stocks.items():
            data_to_save.append([sid, v['sh'], v['co']])
        sh.clear()
        sh.update("A1", data_to_save)
        st.toast("✅ 數據已成功同步至雲端")
    except Exception as e:
        st.error(f"存檔失敗: {e}")

# --- 2. 樣式 CSS ---
st.markdown("""
    <style>
    .stApp { background-color: #0f111a; color: #e0e0e0; }
    [data-testid="stMetric"] {
        background: linear-gradient(145deg, #1b1e2e, #161926);
        border: 1px solid #333; border-radius: 15px; padding: 15px !important;
        box-shadow: 0 4px 15px rgba(0,0,0,0.4);
    }
    [data-testid="stMetricValue"] > div { font-family: 'Consolas', monospace; color: #00d4ff !important; font-size: 1.8rem !important; }
    .stNumberInput input { background-color: #252836 !important; color: white !important; border: 1px solid #555 !important; }
    h1, h2, h3 { color: #00d4ff !important; font-weight: 700 !important; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. 強化版報價抓取引擎 ---
@st.cache_data(ttl=600) # 每 10 分鐘更新一次報價
def get_stock_info(symbol):
    if symbol == "CASH":
        return 1.0, "現金部位"
    
    # 針對台灣市場代號優化
    full_symbol = symbol
    if "." not in symbol:
        # 預設先嘗試上市 (.TW)，若無資料再嘗試上櫃 (.TWO)
        full_symbol = f"{symbol}.TW"
    
    try:
        ticker = yf.Ticker(full_symbol)
        # 嘗試從 fast_info 拿價格
        price = ticker.fast_info.last_price
        
        # 如果 fast_info 是 NaN，從 info 拿
        if pd.isna(price) or price == 0:
            price = ticker.info.get('regularMarketPrice')
        
        # 如果還是抓不到，拿最後一個歷史收盤價
        if pd.isna(price) or price == 0 or price is None:
            hist = ticker.history(period="1d")
            if not hist.empty:
                price = hist['Close'].iloc[-1]
            else:
                # 嘗試上櫃格式
                if ".TW" in full_symbol:
                    alt_symbol = symbol.replace(".TW", "") + ".TWO"
                    ticker = yf.Ticker(alt_symbol)
                    hist = ticker.history(period="1d")
                    if not hist.empty:
                        price = hist['Close'].iloc[-1]
        
        name = ticker.info.get('shortName', symbol)
        return float(price), name
    except:
        return 0.0, symbol

# --- 4. 數據處理 ---
if 'stocks' not in st.session_state:
    st.session_state.stocks = load_data_from_gs()
if 'principal' not in st.session_state:
    st.session_state.principal = 0.0

total_mkt = 0.0
s_val, l_val, b_val, c_val = 0.0, 0.0, 0.0, 0.0
processed_rows = []

# 遍歷持股抓取資料
for sid, v in st.session_state.stocks.items():
    price, name = get_stock_info(sid)
    mkt = v['sh'] * price
    total_mkt += mkt
    if sid == "CASH": c_val += mkt
    elif "B" in sid: b_val += mkt
    elif "L" in sid: l_val += mkt
    else: s_val += mkt
    processed_rows.append({
        "標的": sid, 
        "名稱": name, 
        "現價": f"{price:,.2f}", 
        "股數": f"{v['sh']:,.0f}", 
        "市值": round(mkt, 0)
    })

safe_val = b_val + c_val

# --- 5. 主介面呈現 ---
st.title("📊 綜合退休戰情室 V70.6 Cloud")

col1, col2, col3 = st.columns(3)
with col1: st.metric("資產總市值", f"${total_mkt:,.0f}")
with col2: st.session_state.principal = st.number_input("投入總本金", value=float(st.session_state.principal))
with col3:
    true_pnl = total_mkt - st.session_state.principal
    pnl_pct = (true_pnl / st.session_state.principal * 100) if st.session_state.principal > 0 else 0
    st.metric("真實累積總損益", f"${true_pnl:,.0f}", f"{pnl_pct:.2f}%")

st.divider()

# 現況方塊
st.subheader("⚖️ 目標再平衡對照")
cur1, cur2, cur3 = st.columns(3)
def card_html(label, color, pct, val):
    return f"<div style='text-align:center; padding:15px; background:rgba(255,255,255,0.03); border:1px solid {color}44; border-radius:12px;'><small style='color:#aaa;'>{label}</small><br><b style='color:{color}; font-size:26px;'>{pct:.1f}%</b><br><b style='color:{color}; font-size:22px;'>${val:,.0f}</b></div>"

with cur1: st.markdown(card_html("現況 股票", "#00d4ff", (s_val/total_mkt*100 if total_mkt>0 else 0), s_val), unsafe_allow_html=True)
with cur2: st.markdown(card_html("現況 槓桿", "#bd93f9", (l_val/total_mkt*100 if total_mkt>0 else 0), l_val), unsafe_allow_html=True)
with cur3: st.markdown(card_html("現況 類現金", "#00ff88", (safe_val/total_mkt*100 if total_mkt>0 else 0), safe_val), unsafe_allow_html=True)

st.write("")
t_col1, t_col2, t_col3 = st.columns(3)
with t_col1: 
    ts = st.number_input("目標 股票 %", value=40)
    st.markdown(f"<div style='text-align:center; color:#00d4ff; font-weight:bold;'>目標: ${total_mkt * ts/100:,.0f}</div>", unsafe_allow_html=True)
with t_col2: 
    tl = st.number_input("目標 槓桿 %", value=30)
    st.markdown(f"<div style='text-align:center; color:#bd93f9; font-weight:bold;'>目標: ${total_mkt * tl/100:,.0f}</div>", unsafe_allow_html=True)
with t_col3: 
    t_safe_pct = 100 - ts - tl
    st.markdown(f"<div style='text-align:center; padding-top:10px;'><small style='color:#aaa;'>目標 類現金</small><br><b style='color:#00ff88; font-size:24px;'>{t_safe_pct}%</b><br><b style='color:#00ff88; font-weight:bold;'>目標: ${total_mkt * t_safe_pct/100:,.0f}</b></div>", unsafe_allow_html=True)

st.divider()

# 圖表與庫存
c_pie, c_table = st.columns([1, 1.5])
with c_pie:
    fig = go.Figure(data=[go.Pie(labels=['股票', '槓桿', '債券', '現金'], values=[s_val, l_val, b_val, c_val], marker=dict(colors=['#00d4ff', '#bd93f9', '#ff9f1c', '#00ff88']), hole=.4)])
    fig.update_layout(template="plotly_dark", margin=dict(t=0,b=0,l=0,r=0))
    st.plotly_chart(fig, use_container_width=True)

with c_table:
    st.subheader("📋 目前庫存清單")
    if processed_rows:
        st.dataframe(pd.DataFrame(processed_rows), use_container_width=True, hide_index=True)

# 側邊欄
with st.sidebar:
    st.header("⚙️ 雲端數據控制")
    if st.button("🔄 強制重新整理"):
        st.cache_data.clear() # 清除報價快取
        st.session_state.stocks = load_data_from_gs()
        st.rerun()
    
    st.divider()
    add_id = st.text_input("新增代號 (如 00662 / 2330)").upper().strip()
    if st.button("➕ 新增入池並存檔"):
        if add_id and add_id not in st.session_state.stocks:
            st.session_state.stocks[add_id] = {"sh": 0.0, "co": 0.0}
            save_data_to_gs(st.session_state.stocks)
            st.rerun()

    st.divider()
    st.write("📊 **庫存股數修改**")
    if list(st.session_state.stocks.keys()):
        target_stk = st.selectbox("選取標的", options=list(st.session_state.stocks.keys()))
        new_sh = st.number_input("持有總股數", value=float(st.session_state.stocks[target_stk]["sh"]))
        if st.button("💾 儲存並同步至雲端"):
            st.session_state.stocks[target_stk]["sh"] = new_sh
            save_data_to_gs(st.session_state.stocks)
            st.rerun()
