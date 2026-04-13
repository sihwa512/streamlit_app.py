import streamlit as st
import pandas as pd
import yfinance as yf
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import plotly.graph_objects as go
import re

# --- 1. 連線設定 ---
st.set_page_config(page_title="專業退休戰情室 V77.0", layout="wide")
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

# --- 2. 數據引擎 ---
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
                sid = str(r['id']).upper().strip()
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

# --- 3. 視覺優化 CSS (1:1 復刻截圖質感) ---
st.markdown("""
<style>
    .rebalance-card { background: #161b22; border: 1px solid #30363d; border-radius: 12px; padding: 25px; color: white; }
    .beta-tag { background: #30363d; padding: 4px 12px; border-radius: 6px; font-family: 'Consolas'; font-size: 0.9rem; }
    .cat-box { text-align: center; padding: 10px; }
    .cat-label { color: #8b949e; font-size: 1rem; margin-bottom: 5px; }
    .cat-pct { font-size: 1.6rem; font-weight: bold; }
    .cat-val { font-family: 'Consolas'; font-size: 1.2rem; }
    .stock-blue { color: #58a6ff; } .leverage-purple { color: #bc8cff; } .cash-green { color: #3fb950; }
    .target-box { background: #1c2128; border: 1px dashed #30363d; border-radius: 8px; padding: 15px; margin-top: 15px; }
    .metric-box { background: #161b22; border: 1px solid #30363d; border-radius: 12px; padding: 20px; text-align: center; }
    .val-text { font-size: 2.2rem; font-weight: 800; font-family: 'Consolas'; }
    table { width: 100%; border-collapse: collapse; font-size: 1.2rem !important; margin-top: 20px;}
    th { background: #1c2128; color: #8b949e; text-align: left; padding: 12px; }
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

for sid, v in cur_stocks.items():
    if v['sh'] <= 0: continue
    curr, prev, ytd = get_price_metrics(sid)
    m = v['sh'] * curr
    total_mkt += m
    today_delta += (curr - prev) * v['sh']
    
    # 分類邏輯 (依據周先生偏好)
    beta = 1.0
    if "L" in sid or "631" in sid: 
        leverage_val += m
        beta = 2.0
    elif sid == "CASH" or "865B" in sid:
        cash_val += m
        beta = 0.0
    else:
        stock_val += m
    
    portfolio_beta_sum += (beta * m)
    
    stock_list.append({
        "標的": sid, "持股": int(v['sh']), "報價": curr, "市值": m, "Beta": beta,
        "報酬": f"{((curr-v['avg'])/v['avg']*100):.1f}%" if v['avg']>0 else "0%"
    })

curr_beta = (portfolio_beta_sum / total_mkt) if total_mkt > 0 else 0.0

# --- 5. 主畫面：儀表板 ---
st.title("🛡️ 專業退休戰情室 V77.0")
h1, h2, h3, h4 = st.columns(4)
with h1: st.markdown(f"<div class='metric-box'><small>💵 USD/TWD</small><br><span class='val-text' style='color:#58a6ff'>{fx:.3f}</span></div>", unsafe_allow_html=True)
with h2: st.markdown(f"<div class='metric-box'><small>💰 總市值</small><br><span class='val-text' style='color:#00d4ff'>${int(total_mkt):,}</span></div>", unsafe_allow_html=True)
with h3: st.markdown(f"<div class='metric-box'><small>📈 今日跳動</small><br><span class='val-text {'up' if today_delta>=0 else 'down'}'>${int(today_delta):,}</span></div>", unsafe_allow_html=True)
with h4: st.markdown(f"<div class='metric-box'><small>📊 累計損益</small><br><span class='val-text {'up' if (total_mkt-total_capital)>=0 else 'down'}'>${int(total_mkt-total_capital):,}</span></div>", unsafe_allow_html=True)

st.divider()

# --- 6. 核心功能：目標再平衡 (復刻 image_cb2ca5.png) ---
st.subheader("⚖️ 目標再平衡管理")
with st.container():
    st.markdown(f"""
    <div class='rebalance-card'>
        <div style='display:flex; justify-content:space-between; align-items:center; margin-bottom:20px;'>
            <span style='font-size:1.3rem; font-weight:bold;'>⚖️ 資產配置目標</span>
            <span class='beta-tag'>當前 Portfolio Beta: {curr_beta:.2f}</span>
        </div>
        <div style='display:flex; justify-content:space-around;'>
            <div class='cat-box'>
                <div class='cat-label'>現況 股票</div>
                <div class='cat-pct stock-blue'>{(stock_val/total_mkt*100) if total_mkt>0 else 0:.1f}%</div>
                <div class='cat-val stock-blue'>${int(stock_val):,}</div>
            </div>
            <div class='cat-box'>
                <div class='cat-label'>現況 槓桿</div>
                <div class='cat-pct leverage-purple'>{(leverage_val/total_mkt*100) if total_mkt>0 else 0:.1f}%</div>
                <div class='cat-val leverage-purple'>${int(leverage_val):,}</div>
            </div>
            <div class='cat-box'>
                <div class='cat-label'>現況 類現金</div>
                <div class='cat-pct cash-green'>{(cash_val/total_mkt*100) if total_mkt>0 else 0:.1f}%</div>
                <div class='cat-val cash-green'>${int(cash_val):,}</div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # 手動調整區
    st.markdown("<div style='height:20px;'></div>", unsafe_allow_html=True)
    st.write("🔧 **手動調整目標佔比：**")
    t_col1, t_col2, t_col3 = st.columns(3)
    with t_col1: t_stock = st.number_input("股票目標 %", 0, 100, 50)
    with t_col2: t_lever = st.number_input("正2目標 %", 0, 100, 0)
    with t_col3: t_cash = 100 - t_stock - t_lever; st.info(f"類現金(自動): {t_cash}%")
    
    target_beta = (t_stock * 1.0 + t_lever * 2.0) / 100
    st.markdown(f"<div style='text-align:right;'><span class='beta-tag' style='color:#ff9f1c'>目標 Beta: {target_beta:.2f}</span></div>", unsafe_allow_html=True)

st.divider()

# --- 7. 再平衡買賣建議清單 (復刻 image_51f48a.png) ---
st.subheader("📋 資產部位與買賣建議")
if stock_list:
    html = "<table><thead><tr><th>標的</th><th>持股</th><th>現價</th><th>市值</th><th>報酬</th><th>再平衡建議</th></tr></thead><tbody>"
    for s in stock_list:
        # 計算建議 (以當前資產總額 * 目標比例)
        # 這裡簡化邏輯：如果該標的是該類別的代表
        advice = "-"
        if s['標的'] == "00662":
            diff_val = (total_mkt * t_stock / 100) - stock_val
            shares = diff_val / s['報價']
            if abs(shares) > 0.5:
                color = "action-buy" if shares > 0 else "action-sell"
                advice = f"<span class='{color}'>{'加碼' if shares>0 else '減碼'} {abs(int(shares)):,} 股</span>"
        elif s['標的'] == "00670L" or s['標的'] == "00631L":
            diff_val = (total_mkt * t_lever / 100) - leverage_val
            shares = diff_val / s['報價']
            if abs(shares) > 0.5:
                color = "action-buy" if shares > 0 else "action-sell"
                advice = f"<span class='{color}'>{'加碼' if shares>0 else '減碼'} {abs(int(shares)):,} 股</span>"
        elif s['標的'] == "CASH" or s['標的'] == "00865B":
            diff_val = (total_mkt * t_cash / 100) - cash_val
            advice = f"<span>調整額 ${int(diff_val):,}</span>"

        html += f"<tr><td><b>{s['標的']}</b></td><td>{s['持股']:,}</td><td>{s['報價']:.2f}</td><td>${int(s['市值']):,}</td><td>{s['報酬']}</td><td>{advice}</td></tr>"
    html += "</tbody></table>"
    st.write(html, unsafe_allow_html=True)

with st.sidebar:
    st.header("🖊️ 快速交易")
    op = st.selectbox("動作", ["買入", "賣出", "入金", "出金"])
    sid_in = st.text_input("代號").upper().strip()
    sh_in = st.number_input("數量", min_value=0.0)
    pr_in = st.number_input("單價", min_value=0.0, value=1.0)
    if st.button("💾 同步至雲端"):
        client = get_client()
        ws = client.open_by_key(GS_ID).worksheet("Transactions")
        ws.append_row([datetime.now().strftime("%Y-%m-%d"), op, sid_in, sh_in, pr_in, ""])
        st.cache_data.clear()
        st.rerun()
