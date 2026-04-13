import streamlit as st
import pandas as pd
import yfinance as yf
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import plotly.graph_objects as go
import re

# --- 1. 連線與核心設定 ---
st.set_page_config(page_title="退休戰情室 V76.3", layout="wide")
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
                # 🌟 改良代號處理：不管是 2330 還是 00865B，都視為有效 ID
                sid = str(r['id']).upper().strip()
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

@st.cache_data(ttl=300)
def get_price_metrics(sid):
    if sid == "CASH": return 1.0, 1.0, 1.0
    
    # 🌟 報價引擎：嘗試多種可能的台灣代號後綴
    possible_tickers = [f"{sid}.TW", f"{sid}.TWO", sid]
    
    for tsid in possible_tickers:
        try:
            t = yf.Ticker(tsid)
            hist = t.history(period="5d")
            if not hist.empty:
                curr = hist['Close'].iloc[-1]
                prev = hist['Close'].iloc[-2] if len(hist) > 1 else curr
                
                # 年初價
                ytd_hist = t.history(start=f"{datetime.now().year}-01-01")
                ytd_open = ytd_hist['Close'].iloc[0] if not ytd_hist.empty else curr
                return float(curr), float(prev), float(ytd_open)
        except: continue
    return 0.0, 0.0, 0.0

# --- 3. 視覺優化 CSS ---
st.markdown("""
<style>
    .metric-box { background: #161b22; border: 1px solid #30363d; border-radius: 12px; padding: 22px; text-align: center; }
    .label-text { color: #8b949e; font-size: 1.2rem; margin-bottom: 8px; }
    .val-text { font-size: 2.5rem; font-weight: 800; font-family: 'Consolas', monospace; }
    .up { color: #ff3e3e; } .down { color: #3fb950; }
    /* 強化表格清晰度 */
    table { width: 100%; border-collapse: collapse; font-size: 1.3rem !important; }
    th { background-color: #1c2128 !important; color: #8b949e !important; padding: 12px !important; text-align: left !important; }
    td { padding: 12px !important; border-bottom: 1px solid #30363d !important; }
</style>
""", unsafe_allow_html=True)

# --- 4. 數據整合 ---
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
        "標的": sid,
        "持股數": f"{int(v['sh']):,}", 
        "現報價": f"{curr:,.2f}",
        "目前市值": f"{int(mkt):,}", 
        "報酬率": f"{((curr-v['avg'])/v['avg']*100):.2f}%" if v['avg']>0 else "0.00%",
        "YTD": f"{((curr-ytd)/ytd*100):.2f}%" if ytd>0 else "0.00%"
    })

# --- 5. 頂部儀表板 ---
st.title("🛡️ 退休戰情室 V76.3")
c1, c2, c3, c4 = st.columns(4)
with c1: st.markdown(f"<div class='metric-box'><div class='label-text'>💵 USD/TWD 匯率</div><div class='val-text' style='color:#58a6ff'>{fx:.3f}</div></div>", unsafe_allow_html=True)
with c2: st.markdown(f"<div class='metric-box'><div class='label-text'>💰 資產總市值</div><div class='val-text' style='color:#00d4ff'>${int(total_mkt):,}</div></div>", unsafe_allow_html=True)
with c3:
    color = "up" if today_delta >= 0 else "down"
    st.markdown(f"<div class='metric-box'><div class='label-text'>📈 今日損益變動</div><div class='val-text {color}'>${int(today_delta):,}</div></div>", unsafe_allow_html=True)
with c4:
    net = total_mkt - total_capital
    color = "up" if net >= 0 else "down"
    st.markdown(f"<div class='metric-box'><div class='label-text'>📊 累計總損益</div><div class='val-text {color}'>${int(net):,}</div><div style='color:#8b949e; font-size:1rem;'>本本金: ${int(total_capital):,}</div></div>", unsafe_allow_html=True)

st.divider()

# --- 6. 專業圖表與分析 ---
l_col, r_col = st.columns([2, 1])
with l_col:
    st.subheader("📈 淨值成長曲線")
    if not df_hist.empty:
        # 計算歷史累計淨值
        fig = go.Figure(go.Scatter(x=df_hist['date'], y=df_hist['sh'].cumsum(), fill='tozeroy', line=dict(color='#bc8cff', width=3)))
        fig.update_layout(template="plotly_dark", height=350, margin=dict(l=10,r=10,t=10,b=10), paper_bgcolor='rgba(0,0,0,0)')
        st.plotly_chart(fig, use_container_width=True)

with r_col:
    st.subheader("🎯 再平衡與提領")
    target_pct = st.number_input("股票目標 %", value=50, step=5)
    withdraw_rate = st.slider("預估提領 %", 1.0, 8.0, 4.0, 0.5)
    annual_w = total_mkt * (withdraw_rate / 100)
    st.info(f"月領額預估：NT$ {int(annual_w/12):,}")
    diff = (total_mkt * (target_pct/100)) - total_mkt
    st.warning(f"再平衡建議：{'加碼' if diff > 0 else '減碼'} ${int(abs(diff)):,}")

# --- 7. 清晰資產列表 ---
st.subheader("📋 目前資產明細")
if stock_list:
    # 這裡使用自定義 HTML 表格，確保字體最大、最清晰且無小數點
    html = "<table><thead><tr><th>標的</th><th>持股數</th><th>現報價</th><th>目前市值</th><th>報酬率</th><th>YTD</th></tr></thead><tbody>"
    for item in stock_list:
        html += f"<tr><td><b>{item['標的']}</b></td><td>{item['持股數']}</td><td>{item['現報價']}</td><td>{item['目前市值']}</td><td>{item['報酬率']}</td><td>{item['YTD']}</td></tr>"
    html += "</tbody></table>"
    st.write(html, unsafe_allow_html=True)

with st.sidebar:
    st.header("🖊️ 快速錄入")
    op = st.selectbox("動作", ["買入", "賣出", "入金", "出金"])
    sid_in = st.text_input("代號").upper().strip()
    sh_in = st.number_input("數量", min_value=0.0)
    pr_in = st.number_input("單價", min_value=0.0, value=1.0)
    if st.button("💾 確認並同步"):
        client = get_client()
        ws = client.open_by_key(GS_ID).worksheet("Transactions")
        ws.append_row([datetime.now().strftime("%Y-%m-%d"), op, sid_in, sh_in, pr_in, ""])
        st.cache_data.clear()
        st.rerun()
