import streamlit as st
import pandas as pd
import yfinance as yf
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import plotly.graph_objects as go
import re

# --- 1. 核心連線設定 ---
st.set_page_config(page_title="專業退休戰情室 V77.4", layout="wide")
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

# --- 2. 數據引擎：智能代號與流水帳 ---
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
                # 智能補零：ETF(3位內)補至5位，個股(4位)不變
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

# --- 3. 視覺樣式設定 ---
st.markdown("""
<style>
    .section-title { font-size: 1.4rem; font-weight: bold; margin-bottom: 15px; color: #e6edf3; display: flex; align-items: center; gap: 10px; }
    .card-container { display: flex; justify-content: space-around; gap: 12px; margin-bottom: 20px; }
    .info-card { background: #161b22; border: 1px solid #30363d; border-radius: 12px; padding: 18px; flex: 1; text-align: center; }
    .target-card { background: #1c2128; border: 1px dashed #444c56; border-radius: 12px; padding: 18px; flex: 1; text-align: center; }
    
    .label-text { color: #8b949e; font-size: 0.95rem; margin-bottom: 6px; }
    .pct-text { font-size: 1.9rem; font-weight: 800; margin-bottom: 4px; }
    .amt-text { font-family: 'Consolas', monospace; font-size: 1.15rem; opacity: 0.85; }
    
    .stock-color { color: #58a6ff; } .stock-border { border-top: 5px solid #58a6ff; }
    .lever-color { color: #bc8cff; } .lever-border { border-top: 5px solid #bc8cff; }
    .cash-color { color: #3fb950; } .cash-border { border-top: 5px solid #3fb950; }
    
    .metric-box { background: #161b22; border: 1px solid #30363d; border-radius: 10px; padding: 15px; text-align: center; }
    .val-main { font-size: 2.1rem; font-weight: 800; font-family: 'Consolas'; }
    .beta-tag { background: #30363d; color: #ff9f1c; padding: 3px 10px; border-radius: 5px; font-size: 0.85rem; font-family: 'Consolas'; }
    
    table { width: 100%; border-collapse: collapse; font-size: 1.25rem !important; margin-top: 15px; }
    th { background: #1c2128; color: #8b949e; text-align: left; padding: 12px; border-bottom: 2px solid #30363d; }
    td { padding: 12px; border-bottom: 1px solid #30363d; }
    .buy-text { color: #ff3e3e; font-weight: bold; } .sell-text { color: #3fb950; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# --- 4. 數據整合計算 ---
df_hist, cur_stocks, total_capital = fetch_cloud_data()
fx = yf.Ticker("TWD=X").fast_info.last_price or 32.2

total_mkt, today_delta = 0.0, 0.0
s_val, l_val, c_val = 0.0, 0.0, 0.0
beta_sum = 0.0
stock_list = []

# 分類運算
active_data = {}
for sid, v in cur_stocks.items():
    if v['sh'] <= 0: continue
    curr, prev, ytd = get_price_metrics(sid)
    m = v['sh'] * curr
    total_mkt += m
    today_delta += (curr - prev) * v['sh']
    
    b = 1.0
    if "L" in sid or "631" in sid: 
        l_val += m; b = 2.0
    elif sid == "CASH" or "865B" in sid:
        c_val += m; b = 0.0
    else:
        s_val += m
    
    beta_sum += (b * m)
    active_data[sid] = {"sh": v['sh'], "curr": curr, "m": m, "avg": v['avg']}

curr_beta = (beta_sum / total_mkt) if total_mkt > 0 else 0.0

# --- 5. 主畫面呈現 ---
st.title("🛡️ 專業退休戰情室 V77.4")

h1, h2, h3, h4 = st.columns(4)
with h1: st.markdown(f"<div class='metric-box'><small>💵 USD/TWD</small><br><span class='val-main' style='color:#58a6ff'>{fx:.3f}</span></div>", unsafe_allow_html=True)
with h2: st.markdown(f"<div class='metric-box'><small>💰 總市值</small><br><span class='val-main' style='color:#00d4ff'>${int(total_mkt):,}</span></div>", unsafe_allow_html=True)
with h3: st.markdown(f"<div class='metric-box'><small>📈 今日跳動</small><br><span class='val-main {'up' if today_delta>=0 else 'down'}'>${int(today_delta):,}</span></div>", unsafe_allow_html=True)
with h4: st.markdown(f"<div class='metric-box'><small>📊 累計損益</small><br><span class='val-main {'up' if (total_mkt-total_capital)>=0 else 'down'}'>${int(total_mkt-total_capital):,}</span></div>", unsafe_allow_html=True)

st.divider()

# --- 6. 智能再平衡模組 (現況 vs 目標) ---
st.markdown("<div class='section-title'>⚖️ 投資組合再平衡管理</div>", unsafe_allow_html=True)

# 現況排
st.markdown(f"""
<div class='card-container'>
    <div class='info-card stock-border'><div class='label-text'>現況 股票</div><div class='pct-text stock-color'>{(s_val/total_mkt*100) if total_mkt>0 else 0:.1f}%</div><div class='amt-text stock-color'>${int(s_val):,}</div></div>
    <div class='info-card lever-border'><div class='label-text'>現況 槓桿</div><div class='pct-text lever-color'>{(l_val/total_mkt*100) if total_mkt>0 else 0:.1f}%</div><div class='amt-text lever-color'>${int(l_val):,}</div></div>
    <div class='info-card cash-border'><div class='label-text'>現況 類現金</div><div class='pct-text cash-color'>{(c_val/total_mkt*100) if total_mkt>0 else 0:.1f}%</div><div class='amt-text cash-color'>${int(c_val):,}</div></div>
</div>
<div style='text-align:right; margin-top:-10px; margin-bottom:15px;'><span class='beta-tag'>當前組合 Beta: {curr_beta:.2f}</span></div>
""", unsafe_allow_html=True)

# 目標調整區
t_c1, t_c2, t_c3 = st.columns(3)
with t_c1: t_s_pct = st.number_input("股票目標 %", 0, 100, 50, step=5)
with t_c2: t_l_pct = st.number_input("正2目標 %", 0, 100, 10, step=5)
with t_c3: t_c_pct = 100 - t_s_pct - t_l_pct; st.info(f"類現金目標(自動): {t_c_pct}%")

# 目標排 (換算金額)
t_s_amt = total_mkt * (t_s_pct / 100)
t_l_amt = total_mkt * (t_l_pct / 100)
t_c_amt = total_mkt * (t_c_pct / 100)
t_beta = (t_s_pct * 1.0 + t_l_pct * 2.0) / 100

st.markdown(f"""
<div class='card-container'>
    <div class='target-card'><div class='label-text'>🎯 目標 股票</div><div class='pct-text stock-color' style='opacity:0.7'>{t_s_pct}%</div><div class='amt-text stock-color'>${int(t_s_amt):,}</div></div>
    <div class='target-card'><div class='label-text'>🎯 目標 槓桿</div><div class='pct-text lever-color' style='opacity:0.7'>{t_l_pct}%</div><div class='amt-text lever-color'>${int(t_l_amt):,}</div></div>
    <div class='target-card'><div class='label-text'>🎯 目標 類現金</div><div class='pct-text cash-color' style='opacity:0.7'>{t_c_pct}%</div><div class='amt-text cash-color'>${int(t_c_amt):,}</div></div>
</div>
<div style='text-align:right; margin-top:-10px; margin-bottom:15px;'><span class='beta-tag' style='border:1px solid #ff9f1c'>預期配置 Beta: {t_beta:.2f}</span></div>
""", unsafe_allow_html=True)

st.divider()

# --- 7. 資產部位與建議表 ---
st.subheader("📋 目前資產明細與建議")
if active_data:
    html = "<table><thead><tr><th>標的</th><th>持股數</th><th>報價</th><th>市值</th><th>報酬</th><th>佔比</th><th>再平衡建議</th></tr></thead><tbody>"
    for sid, d in active_data.items():
        pct = (d['m'] / total_mkt * 100) if total_mkt > 0 else 0
        roi = f"{((d['curr']-d['avg'])/d['avg']*100):.1f}%" if d['avg']>0 else "0%"
        
        advice = "-"
        if sid == "00662":
            diff = t_s_amt - s_val
            sh = int(diff / d['curr'])
            if abs(sh) > 0: advice = f"<span class='{'buy-text' if sh>0 else 'sell-text'}'>{'加碼' if sh>0 else '減碼'} {abs(sh):,} 股</span>"
        elif "L" in sid:
            diff = t_l_amt - l_val
            sh = int(diff / d['curr'])
            if abs(sh) > 0: advice = f"<span class='{'buy-text' if sh>0 else 'sell-text'}'>{'加碼' if sh>0 else '減碼'} {abs(sh):,} 股</span>"
        elif sid == "CASH" or "865B" in sid:
            advice = f"調整額 ${int(t_c_amt - c_val):,}"

        html += f"<tr><td><b>{sid}</b></td><td>{int(d['sh']):,}</td><td>{d['curr']:.2f}</td><td>${int(d['m']):,}</td><td>{roi}</td><td>{pct:.1f}%</td><td>{advice}</td></tr>"
    html += "</tbody></table>"
    st.write(html, unsafe_allow_html=True)

with st.sidebar:
    st.header("🖊️ 快速錄入")
    op = st.selectbox("動作", ["買入", "賣出", "入金", "出金"])
    r_sid = st.text_input("代號", value="CASH").upper().strip()
    sid_in = r_sid.zfill(5) if r_sid.isdigit() and len(r_sid) <= 3 else r_sid
    sh_in = st.number_input("數量", min_value=0.0, step=100.0)
    pr_in = st.number_input("單價", min_value=0.0, value=1.0)
    if st.button("💾 確認存檔"):
        client = get_client()
        ws = client.open_by_key(GS_ID).worksheet("Transactions")
        ws.append_row([datetime.now().strftime("%Y-%m-%d"), op, sid_in, sh_in, pr_in, ""])
        st.cache_data.clear(); st.rerun()
