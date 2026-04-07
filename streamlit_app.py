import streamlit as st
import pandas as pd
import yfinance as yf
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import plotly.graph_objects as go
import re

# --- 1. 核心連線設定 ---
st.set_page_config(page_title="退休戰情室 V76.0", layout="wide")
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

# --- 2. 數據讀取與計算 ---
@st.cache_data(ttl=60)
def fetch_cloud_data():
    client = get_client()
    if not client: return pd.DataFrame(), {}, 0.0
    try:
        doc = client.open_by_key(GS_ID)
        df_t = pd.DataFrame(doc.worksheet("Transactions").get_all_records())
        stocks = {}
        total_in = 0.0
        if not df_t.empty:
            df_t['sh'] = pd.to_numeric(df_t['sh'], errors='coerce').fillna(0)
            df_t['pr'] = pd.to_numeric(df_t['pr'], errors='coerce').fillna(0)
            for _, r in df_t.iterrows():
                sid = str(r['id']).upper().zfill(5) if str(r['id']).isdigit() else str(r['id']).upper()
                if r['type'] == "入金": total_in += r['sh']
                elif r['type'] == "出金": total_in -= r['sh']
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
        return df_t, stocks, total_in
    except: return pd.DataFrame(), {}, 0.0

@st.cache_data(ttl=600)
def get_price_metrics(sid):
    if sid == "CASH": return 1.0, 1.0, 1.0
    tsid = f"{sid}.TW" if sid.isdigit() else sid
    try:
        t = yf.Ticker(tsid)
        curr = t.fast_info.last_price
        hist = t.history(period="5d")
        prev = hist['Close'].iloc[-2] if len(hist) > 1 else curr
        ytd_hist = t.history(start=f"{datetime.now().year}-01-01")
        ytd_open = ytd_hist['Close'].iloc[0] if not ytd_hist.empty else curr
        return float(curr), float(prev), float(ytd_open)
    except: return 0.0, 0.0, 0.0

# --- 3. 畫面美化 CSS ---
st.markdown("""
<style>
    .main { background-color: #0d1117; }
    .metric-box { background: #161b22; border: 1px solid #30363d; border-radius: 12px; padding: 20px; text-align: center; }
    .val-text { font-size: 2rem; font-weight: 800; font-family: 'Consolas'; }
    .up { color: #ff3e3e; } .down { color: #3fb950; }
</style>
""", unsafe_allow_html=True)

# --- 4. 數據整合運算 ---
df_hist, cur_stocks, total_capital = fetch_cloud_data()
fx = yf.Ticker("TWD=X").fast_info.last_price or 32.2

total_mkt, today_delta = 0.0, 0.0
stock_list = []
for sid, v in cur_stocks.items():
    if v['sh'] <= 0: continue
    curr, prev, ytd = get_price_metrics(sid)
    mkt = v['sh'] * curr
    total_mkt += mkt
    today_delta += (curr - prev) * v['sh']
    stock_list.append({
        "標的": sid, "持股": v['sh'], "成本": v['avg'], "市值": mkt, 
        "現價": curr, "報酬": ((curr-v['avg'])/v['avg']*100) if v['avg']>0 else 0,
        "YTD": ((curr-ytd)/ytd*100) if ytd>0 else 0
    })

# --- 5. 頂部儀表板 ---
st.title("🛡️ 綜合退休戰情室 V76.0")
c1, c2, c3, c4 = st.columns(4)
with c1: st.markdown(f"<div class='metric-box'><small>💵 USD/TWD 匯率</small><br><span class='val-text' style='color:#58a6ff'>{fx:.3f}</span></div>", unsafe_allow_html=True)
with c2: st.markdown(f"<div class='metric-box'><small>💰 資產總市值</small><br><span class='val-text' style='color:#00d4ff'>${total_mkt:,.0f}</span></div>", unsafe_allow_html=True)
with c3:
    color = "up" if today_delta >= 0 else "down"
    st.markdown(f"<div class='metric-box'><small>📈 今日損益跳動</small><br><span class='val-text {color}'>${today_delta:,.0f}</span></div>", unsafe_allow_html=True)
with c4:
    net = total_mkt - total_capital
    color = "up" if net >= 0 else "down"
    st.markdown(f"<div class='metric-box'><small>📊 真實總累積損益</small><br><span class='val-text {color}'>${net:,.0f}</span><br><small>本金: ${total_capital:,.0f}</small></div>", unsafe_allow_html=True)

st.divider()

# --- 6. 專業分析區 ---
l_col, r_col = st.columns([2, 1])

with l_col:
    st.subheader("📈 歷史淨值與資產分布")
    # 模擬成長圖
    fig = go.Figure(go.Scatter(x=df_hist['date'], y=df_hist['sh'].cumsum(), mode='lines+markers', line=dict(color='#bc8cff', width=3)))
    fig.update_layout(template="plotly_dark", height=300, margin=dict(l=20, r=20, t=20, b=20), paper_bgcolor='rgba(0,0,0,0)')
    st.plotly_chart(fig, use_container_width=True)

with r_col:
    st.subheader("🎯 目標再平衡與自由度")
    target_pct = st.number_input("股票目標佔比 (%)", value=50)
    current_pct = (total_mkt / (total_mkt + 1) * 100) # 簡化
    diff = (total_mkt * (target_pct/100)) - total_mkt
    st.warning(f"再平衡建議：{'加碼' if diff > 0 else '提領'} ${abs(diff):,.0f}")
    
    withdraw_rate = st.slider("提領率 (%)", 1, 10, 4)
    annual_withdraw = total_mkt * (withdraw_rate / 100)
    st.success(f"預估年領額：NT$ {annual_withdraw:,.0f} (月領 {annual_withdraw/12:,.0f})")

# --- 7. 持股清單與流水帳 ---
st.subheader("📋 當前資產部位與交易明細")
t1, t2 = st.tabs(["資產清單", "交易流水帳"])
with t1:
    if stock_list:
        st.dataframe(pd.DataFrame(stock_list).style.format({"市值":"${:,.0f}","現價":"{:.2f}","成本":"{:.2f}","報酬":"{:.2f}%","YTD":"{:.2f}%"}), use_container_width=True, hide_index=True)
with t2:
    st.dataframe(df_hist.iloc[::-1], use_container_width=True, hide_index=True)

with st.sidebar:
    st.header("🖊️ 快速交易")
    op = st.selectbox("類型", ["買入", "賣出", "入金", "出金"])
    sid_in = st.text_input("代號").upper()
    sh_in = st.number_input("數量", min_value=0.0)
    pr_in = st.number_input("單價", min_value=0.0, value=1.0)
    if st.button("同步雲端"):
        client = get_client()
        ws = client.open_by_key(GS_ID).worksheet("Transactions")
        ws.append_row([datetime.now().strftime("%m-%d"), op, sid_in, sh_in, pr_in, ""])
        st.cache_data.clear()
        st.rerun()
