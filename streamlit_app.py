import streamlit as st
import pandas as pd
import yfinance as yf
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta
import plotly.graph_objects as go
import re

# --- 1. 基本設定 ---
st.set_page_config(page_title="專業退休戰情室 V75.0", layout="wide")
GS_ID = "1jgZhEi-nmaXGUa5fJaYwk79xE9-QG4LwhwV89xriGPs"

def get_client():
    try:
        scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        s = st.secrets["gcp_service_account"]
        pk = s["private_key"].replace("\\n", "\n")
        pk = re.sub(r'[^\x20-\x7E\n]', '', pk)
        return gspread.authorize(Credentials.from_service_account_info({
            "type": s["type"], "project_id": s["project_id"], "private_key_id": s["private_key_id"],
            "private_key": pk, "client_email": s["client_email"], "client_id": s["client_id"],
            "auth_uri": s["auth_uri"], "token_uri": s["token_uri"],
            "auth_provider_x509_cert_url": s["auth_provider_x509_cert_url"],
            "client_x509_cert_url": s["client_x509_cert_url"]
        }, scopes=scope))
    except: return None

# --- 2. 數據加載 ---
@st.cache_data(ttl=30)
def load_all_data():
    client = get_client()
    if not client: return pd.DataFrame(), {}, 0.0
    try:
        doc = client.open_by_key(GS_ID)
        ws_t = doc.worksheet("Transactions")
        df_t = pd.DataFrame(ws_t.get_all_records())
        stocks = {}
        total_cap = 0.0
        if not df_t.empty:
            df_t['sh'] = pd.to_numeric(df_t['sh'], errors='coerce').fillna(0)
            df_t['pr'] = pd.to_numeric(df_t['pr'], errors='coerce').fillna(0)
            for _, r in df_t.iterrows():
                sid = str(r['id']).upper().zfill(5) if str(r['id']).isdigit() else str(r['id']).upper()
                if r['type'] == "入金": total_cap += r['sh']
                elif r['type'] == "出金": total_cap -= r['sh']
                elif r['type'] in ["買入", "賣出"]:
                    if sid not in stocks: stocks[sid] = {"sh": 0.0, "cost": 0.0}
                    if r['type'] == "買入":
                        stocks[sid]["sh"] += r['sh']
                        stocks[sid]["cost"] += (r['sh'] * r['pr'])
                    else:
                        if stocks[sid]["sh"] > 0:
                            stocks[sid]["cost"] -= (stocks[sid]["cost"] * (r['sh']/stocks[sid]["sh"]))
                        stocks[sid]["sh"] -= r['sh']
        for s in stocks: stocks[s]["avg"] = stocks[s]["cost"]/stocks[s]["sh"] if stocks[s]["sh"] > 0 else 0
        return df_t, stocks, total_cap
    except: return pd.DataFrame(), {}, 0.0

@st.cache_data(ttl=3600)
def get_market_metrics():
    try:
        usdtwd = yf.Ticker("TWD=X").fast_info.last_price
        return round(usdtwd, 3)
    except: return 32.1

@st.cache_data(ttl=600)
def get_advanced_info(sid):
    if sid == "CASH": return 1.0, 0.0, 0.0 # 現價, 昨收, 年初價
    ticker_sid = f"{sid}.TW" if sid.isdigit() else sid
    try:
        t = yf.Ticker(ticker_sid)
        curr = t.fast_info.last_price
        # 抓取年初與昨收
        hist = t.history(start=f"{datetime.now().year}-01-01")
        y_close = hist['Close'].iloc[-2] if len(hist) > 1 else curr
        ytd_open = hist['Close'].iloc[0] if not hist.empty else curr
        return float(curr), float(y_close), float(ytd_open)
    except: return 0.0, 0.0, 0.0

# --- 3. 計算資產 ---
df_hist, cur_stocks, total_capital = load_data()
fx = get_market_metrics()

# --- 4. CSS 樣式 (模仿截圖深色質感) ---
st.markdown("""
<style>
    .metric-card { background: #161b22; border-radius: 10px; padding: 15px; border: 1px solid #30363d; text-align: center; }
    .metric-label { color: #8b949e; font-size: 0.9rem; }
    .metric-value { color: #58a6ff; font-size: 1.8rem; font-weight: bold; font-family: 'Consolas'; }
    .profit-pos { color: #ff3e3e; } .profit-neg { color: #3fb950; } /* 台灣紅漲綠跌習慣 */
</style>
""", unsafe_allow_html=True)

# --- 5. 頂部儀表板 ---
st.title("🛡️ 綜合退休戰情室 V75.0")
h1, h2, h3, h4 = st.columns(4)

total_mkt = 0.0
today_change = 0.0
stock_rows = []

for sid, v in cur_stocks.items():
    if v['sh'] <= 0: continue
    curr, prev, ytd = get_advanced_info(sid)
    mkt = v['sh'] * curr
    total_mkt += mkt
    today_change += (curr - prev) * v['sh']
    
    # 計算報酬與回撤
    roi = ((curr - v['avg']) / v['avg'] * 100) if v['avg'] > 0 else 0
    ytd_p = ((curr - ytd) / ytd * 100) if ytd > 0 else 0
    
    stock_rows.append({
        "標的": sid, "持股": v['sh'], "成本": v['avg'], "市值": mkt, 
        "現價": curr, "報酬": roi, "YTD": ytd_p
    })

with h1: st.markdown(f"<div class='metric-card'><div class='metric-label'>💵 USD/TWD 匯率</div><div class='metric-value'>{fx}</div></div>", unsafe_allow_html=True)
with h2: st.markdown(f"<div class='metric-card'><div class='metric-label'>💰 資產總市值</div><div class='metric-value'>${total_mkt:,.0f}</div></div>", unsafe_allow_html=True)
with h3: 
    color = "profit-pos" if today_change >= 0 else "profit-neg"
    st.markdown(f"<div class='metric-card'><div class='metric-label'>📈 今日損益跳動</div><div class='metric-value {color}'>${today_change:,.0f}</div></div>", unsafe_allow_html=True)
with h4:
    net_pnl = total_mkt - total_capital
    pnl_color = "profit-pos" if net_pnl >= 0 else "profit-neg"
    st.markdown(f"<div class='metric-card'><div class='metric-label'>📊 真實累積總損益</div><div class='metric-value {pnl_color}'>${net_pnl:,.0f}</div><div style='color:#8b949e; font-size:0.8rem;'>投入本金: ${total_capital:,.0f}</div></div>", unsafe_allow_html=True)

st.divider()

# --- 6. 再平衡建議 ---
st.subheader("🎯 目標再平衡管理")
b1, b2, b3 = st.columns([1, 1, 1])
with b1:
    target_stock_pct = st.slider("股票目標 %", 0, 100, 50)
with b2:
    st.info(f"當前股票佔比: {(total_mkt-total_capital)/total_mkt*100 if total_mkt>0 else 0:.1f}%")
    target_val = total_mkt * (target_stock_pct / 100)
    diff = target_val - (total_mkt - total_capital)
    action = "加碼" if diff > 0 else "提領"
    st.warning(f"再平衡建議: {action} ${abs(diff):,.0f}")

st.divider()

# --- 7. 資產部位明細 (專業列表) ---
st.subheader("📝 當前資產部位")
if stock_rows:
    df_s = pd.DataFrame(stock_rows)
    # 格式化顯示
    st.dataframe(df_s.style.format({
        "現價": "{:,.2f}", "成本": "{:,.2f}", "持股": "{:,.0f}",
        "市值": "${:,.0f}", "報酬": "{:.2f}%", "YTD": "{:.2f}%"
    }), use_container_width=True, hide_index=True)

# --- 8. 側邊欄 ---
with st.sidebar:
    st.header("🖊️ 快速錄入")
    op = st.selectbox("動作類型", ["買入", "賣出", "入金", "出金"])
    sid_in = st.text_input("標的代號").upper()
    sh_in = st.number_input("數量/金額", min_value=0.0)
    pr_in = st.number_input("單價", min_value=0.0, value=1.0)
    if st.button("送出紀錄"):
        client = get_client()
        ws = client.open_by_key(GS_ID).worksheet("Transactions")
        ws.append_row([datetime.now().strftime("%Y-%m-%d"), op, sid_in, sh_in, pr_in, ""])
        st.cache_data.clear()
        st.rerun()
