import streamlit as st
import pandas as pd
import yfinance as yf
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import plotly.graph_objects as go
import re

# --- 1. 連線設定 ---
st.set_page_config(page_title="專業退休戰情室 V77.3", layout="wide")
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

# --- 2. 數據引擎：智能補零 ---
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
                raw_id = str(r['id']).upper().strip()
                # 只有 3 位數以下補齊到 5 位 (ETF)；4 位數保持原樣 (股票)
                sid = raw_id.zfill(5) if raw_id.isdigit() and len(raw_id) <= 3 else raw_id
                
                if r['type'] == "入金": total_in += r['sh']
                elif r['type'] == "出金": total_in -= r['sh']
                elif r['type'] in ["買入", "賣出"]:
                    if sid not in stocks: stocks[sid] = {"sh": 0.0, "cost": 0.0}
                    if r['type'] == "買入":
                        stocks[sid]["sh"] += r['sh']
                        stocks[sid]["cost"] += (r['sh'] * r['pr'])
                    else:
                        if stocks[sid]["sh"] > 0: stocks[sid]["cost"] -= (stocks[sid]["cost"] * (r['sh']/stocks[sid]["sh"]))
                        stocks[sid]["sh"] -= r['sh']
        for s in stocks: stocks[s]["avg"] = stocks[s]["cost"]/stocks[s]["sh"] if stocks[s]["sh"] > 0 else 0
        return df_t, stocks, total_in
    except: return pd.DataFrame(), {}, 0.0

@st.cache_data(ttl=300)
def get_price_metrics(sid):
    if sid == "CASH": return 1.0, 1.0, 1.0
    for tsid in [f"{sid}.TW", f"{sid}.TWO", sid]:
        try:
            t = yf.Ticker(tsid)
            hist = t.history(period="5d")
            if not hist.empty:
                curr = hist['Close'].iloc[-1]
                prev = hist['Close'].iloc[-2] if len(hist) > 1 else curr
                ytd_hist = t.history(start=f"{datetime.now().year}-01-01")
                ytd_open = ytd_hist['Close'].iloc[0] if not ytd_hist.empty else curr
                return float(curr), float(prev), float(ytd_open)
        except: continue
    return 0.0, 0.0, 0.0

# --- 3. 視覺樣式 (復刻專業戰情室) ---
st.markdown("""
<style>
    .cat-container { display: flex; justify-content: space-around; gap: 15px; margin-bottom: 25px; }
    .cat-card { background: #161b22; border: 1px solid #30363d; border-radius: 12px; padding: 15px; flex: 1; text-align: center; box-shadow: 0 4px 6px rgba(0,0,0,0.3); }
    .cat-label { color: #8b949e; font-size: 0.95rem; margin-bottom: 8px; }
    .cat-pct { font-size: 1.8rem; font-weight: 800; margin-bottom: 4px; }
    .cat-val { font-family: 'Consolas', monospace; font-size: 1.1rem; opacity: 0.9; }
    
    .stock-blue { color: #58a6ff; border-top: 4px solid #58a6ff; }
    .leverage-purple { color: #bc8cff; border-top: 4px solid #bc8cff; }
    .cash-green { color: #3fb950; border-top: 4px solid #3fb950; }
    
    .metric-box { background: #161b22; border: 1px solid #30363d; border-radius: 12px; padding: 20px; text-align: center; }
    .val-text { font-size: 2.2rem; font-weight: 800; font-family: 'Consolas'; }
    .beta-tag { background: #30363d; color: #ff9f1c; padding: 4px 12px; border-radius: 6px; font-size: 0.9rem; font-family: 'Consolas'; }
    
    table { width: 100%; border-collapse: collapse; font-size: 1.2rem !important; }
    th { background: #1c2128; color: #8b949e; text-align: left; padding: 12px; border-bottom: 2px solid #30363d; }
    td { padding: 12px; border-bottom: 1px solid #30363d; }
    .action-buy { color: #ff3e3e; font-weight: bold; } .action-sell { color: #3fb950; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# --- 4. 數據整合 ---
df_hist, cur_stocks, total_capital = fetch_cloud_data()
fx = yf.Ticker("TWD=X").fast_info.last_price or 32.2

total_mkt, today_delta = 0.0, 0.0
stock_val, leverage_val, cash_val = 0.0, 0.0, 0.0
portfolio_beta_sum = 0.0
stock_list = []

active_stocks = {}
for sid, v in cur_stocks.items():
    if v['sh'] <= 0: continue
    curr, prev, ytd = get_price_metrics(sid)
    m = v['sh'] * curr
    total_mkt += m
    today_delta += (curr - prev) * v['sh']
    
    beta = 1.0
    if "L" in sid or "631" in sid: 
        leverage_val += m; beta = 2.0
    elif sid == "CASH" or "865B" in sid:
        cash_val += m; beta = 0.0
    else:
        stock_val += m
    
    portfolio_beta_sum += (beta * m)
    active_stocks[sid] = {"sh": v['sh'], "curr": curr, "m": m, "avg": v['avg']}

curr_beta = (portfolio_beta_sum / total_mkt) if total_mkt > 0 else 0.0

for sid, data in active_stocks.items():
    pct = (data['m'] / total_mkt * 100) if total_mkt > 0 else 0
    stock_list.append({
        "標的": sid, "持股": int(data['sh']), "報價": data['curr'], "市值": data['m'], 
        "佔比": pct, "報酬": f"{((data['curr']-data['avg'])/data['avg']*100):.1f}%" if data['avg']>0 else "0%"
    })

# --- 5. 畫面呈現 ---
st.title("🛡️ 專業退休戰情室 V77.3")

h1, h2, h3, h4 = st.columns(4)
with h1: st.markdown(f"<div class='metric-box'><small>💵 USD/TWD</small><br><span class='val-text' style='color:#58a6ff'>{fx:.3f}</span></div>", unsafe_allow_html=True)
with h2: st.markdown(f"<div class='metric-box'><small>💰 總市值</small><br><span class='val-text' style='color:#00d4ff'>${int(total_mkt):,}</span></div>", unsafe_allow_html=True)
with h3: st.markdown(f"<div class='metric-box'><small>📈 今日跳動</small><br><span class='val-text {'up' if today_delta>=0 else 'down'}'>${int(today_delta):,}</span></div>", unsafe_allow_html=True)
with h4: st.markdown(f"<div class='metric-box'><small>📊 累計損益</small><br><span class='val-text {'up' if (total_mkt-total_capital)>=0 else 'down'}'>${int(total_mkt-total_capital):,}</span></div>", unsafe_allow_html=True)

st.divider()

# --- 6. 目標再平衡：美化方塊 (加入金額) ---
st.subheader("⚖️ 目標再平衡管理")
s_pct = (stock_val/total_mkt*100) if total_mkt > 0 else 0
l_pct = (leverage_val/total_mkt*100) if total_mkt > 0 else 0
c_pct = (cash_val/total_mkt*100) if total_mkt > 0 else 0

st.markdown(f"""
<div class="cat-container">
    <div class="cat-card stock-blue">
        <div class="cat-label">現況 股票</div>
        <div class="cat-pct">{s_pct:.1f}%</div>
        <div class="cat-val">${int(stock_val):,}</div>
    </div>
    <div class="cat-card leverage-purple">
        <div class="cat-label">現況 槓桿</div>
        <div class="cat-pct">{l_pct:.1f}%</div>
        <div class="cat-val">${int(leverage_val):,}</div>
    </div>
    <div class="cat-card cash-green">
        <div class="cat-label">現況 類現金</div>
        <div class="cat-pct">{c_pct:.1f}%</div>
        <div class="cat-val">${int(cash_val):,}</div>
    </div>
</div>
<div style="text-align:right; margin-top:-10px; margin-bottom:10px;">
    <span class="beta-tag">當前組合 Beta: {curr_beta:.2f}</span>
</div>
""", unsafe_allow_html=True)

t_col1, t_col2, t_col3 = st.columns(3)
with t_col1: t_stock = st.number_input("股票目標 %", 0, 100, 50)
with t_col2: t_lever = st.number_input("正2目標 %", 0, 100, 10)
with t_col3: t_cash = 100 - t_stock - t_lever; st.info(f"類現金目標: {t_cash}%")

st.divider()

# --- 7. 資產明細：佔比置於報酬後 ---
st.subheader("📋 目前資產部位與買賣建議")
if stock_list:
    html = "<table><thead><tr><th>標的</th><th>持股數</th><th>報價</th><th>市值</th><th>報酬</th><th>佔比</th><th>再平衡建議</th></tr></thead><tbody>"
    for s in stock_list:
        advice = "-"
        if s['標的'] == "00662":
            diff = (total_mkt * t_stock / 100) - stock_val
            shares = int(diff / s['報價'])
            if abs(shares) > 0: advice = f"<span class='{'action-buy' if shares>0 else 'action-sell'}'>{'加碼' if shares>0 else '減碼'} {abs(shares):,} 股</span>"
        elif "L" in s['標的']:
            diff = (total_mkt * t_lever / 100) - leverage_val
            shares = int(diff / s['報價'])
            if abs(shares) > 0: advice = f"<span class='{'action-buy' if shares>0 else 'action-sell'}'>{'加碼' if shares>0 else '減碼'} {abs(shares):,} 股</span>"

        html += f"<tr><td><b>{s['標的']}</b></td><td>{s['持股']:,}</td><td>{s['報價']:.2f}</td><td>${int(s['市值']):,}</td><td>{s['報酬']}</td><td>{s['佔比']:.1f}%</td><td>{advice}</td></tr>"
    html += "</tbody></table>"
    st.write(html, unsafe_allow_html=True)

with st.sidebar:
    st.header("🖊️ 交易錄入 / 出入金")
    op = st.selectbox("動作", ["買入", "賣出", "入金", "出金"])
    raw_sid = st.text_input("代號", value="CASH").upper().strip()
    sid_in = raw_sid.zfill(5) if raw_sid.isdigit() and len(raw_sid) <= 3 else raw_sid
    sh_in = st.number_input("數量", min_value=0.0, step=100.0)
    pr_in = st.number_input("單價", min_value=0.0, value=1.0)
    if st.button("💾 同步資料"):
        client = get_client()
        ws = client.open_by_key(GS_ID).worksheet("Transactions")
        ws.append_row([datetime.now().strftime("%Y-%m-%d"), op, sid_in, sh_in, pr_in, ""])
        st.cache_data.clear(); st.rerun()
