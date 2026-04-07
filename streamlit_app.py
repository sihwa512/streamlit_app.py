import streamlit as st
import pandas as pd
import yfinance as yf
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import plotly.graph_objects as go
import re

# --- 1. 連線與核心設定 ---
st.set_page_config(page_title="退休戰情室 V76.1", layout="wide")
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

# --- 2. 數據處理 ---
@st.cache_data(ttl=60)
def fetch_cloud_data():
    client = get_client()
    if not client: return pd.DataFrame(), {}, 0.0
    try:
        doc = client.open_by_key(GS_ID)
        df_t = pd.DataFrame(doc.worksheet("Transactions").get_all_records())
        stocks, total_in = {}, 0.0
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
    # 強化台灣代碼格式 
    tsid = f"{sid}.TW" if sid.isdigit() else sid
    try:
        t = yf.Ticker(tsid)
        # 優先抓取即時價，失敗則抓歷史最後一筆
        curr = t.fast_info.last_price
        hist = t.history(period="5d")
        if curr is None or curr == 0: curr = hist['Close'].iloc[-1]
        prev = hist['Close'].iloc[-2] if len(hist) > 1 else curr
        # 年初價
        ytd_hist = t.history(start=f"{datetime.now().year}-01-01")
        ytd_open = ytd_hist['Close'].iloc[0] if not ytd_hist.empty else curr
        return float(curr), float(prev), float(ytd_open)
    except: return 0.0, 0.0, 0.0

# --- 3. 視覺優化 CSS ---
st.markdown("""
<style>
    /* 強化文字對比與字體大小 */
    .metric-box { background: #161b22; border: 1px solid #30363d; border-radius: 12px; padding: 20px; text-align: center; }
    .label-text { color: #8b949e; font-size: 1.1rem; margin-bottom: 8px; }
    .val-text { font-size: 2.4rem; font-weight: 800; font-family: 'Consolas'; }
    .up { color: #ff3e3e; } .down { color: #3fb950; }
    /* 隱藏表格小數點樣式 */
    [data-testid="stDataFrame"] { font-size: 1.1rem; }
</style>
""", unsafe_allow_html=True)

# --- 4. 數據整合 ---
df_hist, cur_stocks, total_capital = fetch_cloud_data()
fx = yf.Ticker("TWD=X").fast_info.last_price or 32.3

total_mkt, today_delta = 0.0, 0.0
stock_list = []
for sid, v in cur_stocks.items():
    if v['sh'] <= 0: continue
    curr, prev, ytd = get_price_metrics(sid)
    mkt = v['sh'] * curr
    total_mkt += mkt
    today_delta += (curr - prev) * v['sh']
    
    stock_list.append({
        "標的": sid,
        "持股數": int(v['sh']), # 強制轉整數
        "平均成本": round(v['avg'], 2),
        "現報價": round(curr, 2),
        "目前市值": int(mkt), # 強制轉整數
        "報酬率": f"{((curr-v['avg'])/v['avg']*100):.2f}%" if v['avg']>0 else "0.00%",
        "YTD": f"{((curr-ytd)/ytd*100):.2f}%" if ytd>0 else "0.00%"
    })

# --- 5. 頂部儀表板 ---
st.title("🛡️ 退休戰情室 V76.1")
c1, c2, c3, c4 = st.columns(4)
with c1: st.markdown(f"<div class='metric-box'><div class='label-text'>💵 USD/TWD 匯率</div><div class='val-text' style='color:#58a6ff'>{fx:.3f}</div></div>", unsafe_allow_html=True)
with c2: st.markdown(f"<div class='metric-box'><div class='label-text'>💰 資產總市值</div><div class='val-text' style='color:#00d4ff'>${int(total_mkt):,}</div></div>", unsafe_allow_html=True)
with c3:
    color = "up" if today_delta >= 0 else "down"
    st.markdown(f"<div class='metric-box'><div class='label-text'>📈 今日損益變動</div><div class='val-text {color}'>${int(today_delta):,}</div></div>", unsafe_allow_html=True)
with c4:
    net = total_mkt - total_capital
    color = "up" if net >= 0 else "down"
    st.markdown(f"<div class='metric-box'><div class='label-text'>📊 累計總損益</div><div class='val-text {color}'>${int(net):,}</div><div style='color:#8b949e'>本金: ${int(total_capital):,}</div></div>", unsafe_allow_html=True)

st.divider()

# --- 6. 專業圖表與分析 ---
l_col, r_col = st.columns([2, 1])
with l_col:
    st.subheader("📈 淨值成長與資產分佈")
    if not df_hist.empty:
        fig = go.Figure(go.Scatter(x=df_hist['date'], y=df_hist['sh'].cumsum(), fill='tozeroy', line=dict(color='#bc8cff')))
        fig.update_layout(template="plotly_dark", height=320, margin=dict(l=10,r=10,t=10,b=10), paper_bgcolor='rgba(0,0,0,0)')
        st.plotly_chart(fig, use_container_width=True)

with r_col:
    st.subheader("🎯 再平衡與提領")
    target_pct = st.number_input("股票目標 %", value=50, step=5)
    withdraw_rate = st.slider("預估提領 %", 1, 8, 4)
    
    annual_w = total_mkt * (withdraw_rate / 100)
    st.info(f"月領額預估：NT$ {int(annual_w/12):,}")
    
    diff = (total_mkt * (target_pct/100)) - total_mkt
    st.warning(f"再平衡：{'加碼' if diff > 0 else '減碼'} ${int(abs(diff)):,}")

# --- 7. 清晰資產列表 ---
st.subheader("📋 當前資產明細")
if stock_list:
    df_show = pd.DataFrame(stock_list)
    # 使用 DataFrame 顯示，並移除索引
    st.table(df_show) 

with st.sidebar:
    st.header("🖊️ 快速錄入")
    op = st.selectbox("動作", ["買入", "賣出", "入金", "出金"])
    sid_in = st.text_input("代號").upper()
    sh_in = st.number_input("數量", min_value=0.0)
    pr_in = st.number_input("單價", min_value=0.0, value=1.0)
    if st.button("同步雲端資料"):
        client = get_client()
        ws = client.open_by_key(GS_ID).worksheet("Transactions")
        ws.append_row([datetime.now().strftime("%m-%d"), op, sid_in, sh_in, pr_in, "系統紀錄"])
        st.cache_data.clear()
        st.rerun()
