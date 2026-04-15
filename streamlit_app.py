import streamlit as st
import pandas as pd
import yfinance as yf
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import re

# --- 1. 核心連線設定 ---
st.set_page_config(page_title="退休戰情室 V78.6", layout="wide")
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
        stocks, total_cap, running_cash = {}, 0.0, 0.0
        if not df_t.empty:
            df_t['sh'] = pd.to_numeric(df_t['sh'], errors='coerce').fillna(0)
            df_t['pr'] = pd.to_numeric(df_t['pr'], errors='coerce').fillna(0)
            for _, r in df_t.iterrows():
                raw_id = str(r['id']).upper().strip()
                sid = raw_id.zfill(5) if raw_id.isdigit() and len(raw_id) <= 3 else raw_id
                if r['type'] == "入金": total_cap += r['sh']; running_cash += r['sh']
                elif r['type'] == "出金": total_cap -= r['sh']; running_cash -= r['sh']
                elif r['type'] == "買入":
                    if sid not in stocks: stocks[sid] = {"sh": 0.0, "cost": 0.0}
                    stocks[sid]["sh"] += r['sh']; stocks[sid]["cost"] += (r['sh'] * r['pr'])
                    running_cash -= (r['sh'] * r['pr'])
                elif r['type'] == "賣出":
                    if sid in stocks and stocks[sid]["sh"] > 0:
                        stocks[sid]["cost"] -= (stocks[sid]["cost"] * (r['sh']/stocks[sid]["sh"]))
                        stocks[sid]["sh"] -= r['sh']; running_cash += (r['sh'] * r['pr'])
            stocks["CASH"] = {"sh": running_cash, "cost": running_cash, "avg": 1.0}
        for s in stocks:
            if s != "CASH": stocks[s]["avg"] = stocks[s]["cost"]/stocks[s]["sh"] if stocks[s]["sh"] > 0 else 0
        return df_t, stocks, total_cap
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

# --- 3. 寬螢幕對齊視覺樣式 ---
st.markdown("""
<style>
    .stApp { background-color: #0d1117; color: #e6edf3; }
    
    /* 核心：電腦版強迫 4 欄，手機版自動切換 */
    .metric-grid {
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        gap: 8px;
        margin-bottom: 12px;
    }
    @media (max-width: 1200px) { .metric-grid { grid-template-columns: repeat(2, 1fr); } }
    @media (max-width: 600px) { .metric-grid { grid-template-columns: 1fr; } }

    .responsive-grid {
        display: grid;
        grid-template-columns: repeat(3, 1fr);
        gap: 8px;
        margin-bottom: 10px;
    }
    @media (max-width: 600px) { .responsive-grid { grid-template-columns: 1fr; } }

    /* 指標方塊極致壓縮 */
    .metric-card { background: #1c2128; border: 1px solid #444c56; border-radius: 8px; padding: 10px; text-align: center; }
    .label-bright { color: #ffffff !important; font-size: 0.95rem; font-weight: 600; margin-bottom: 2px; }
    .val-main { font-size: 1.8rem; font-weight: 800; font-family: 'Consolas', monospace; line-height: 1.1; }
    
    .info-box { background: #161b22; border-radius: 8px; padding: 10px; text-align: center; border: 1px solid #30363d; }
    .box-pct { font-size: 1.7rem; font-weight: 900; line-height: 1.1; }
    .box-amt { font-family: 'Consolas'; font-size: 1.05rem; opacity: 0.9; }
    
    .b-blue { border-top: 4px solid #58a6ff; color: #58a6ff; }
    .b-purple { border-top: 4px solid #bc8cff; color: #bc8cff; }
    .b-green { border-top: 4px solid #3fb950; color: #3fb950; }
    .beta-tag { background: #30363d; color: #ff9f1c; padding: 1px 6px; border-radius: 4px; font-size: 0.8rem; font-family: 'Consolas'; }
    
    /* 表格行高 */
    table { width: 100%; border-collapse: collapse; font-size: 1.15rem !important; }
    th { background: #1c2128 !important; color: #ffffff !important; padding: 6px 10px !important; }
    td { padding: 6px 10px !important; border-bottom: 1px solid #30363d !important; }
    .up { color: #ff3e3e; font-weight: bold; } .down { color: #3fb950; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# --- 4. 數據整理 ---
df_hist, cur_stocks, total_capital = fetch_cloud_data()
fx = yf.Ticker("TWD=X").fast_info.last_price or 32.3

total_mkt, today_delta, beta_sum = 0.0, 0.0, 0.0
s_v, l_v, c_v = 0.0, 0.0, 0.0
active_data = {}

for sid, v in cur_stocks.items():
    if v['sh'] == 0 and sid != "CASH": continue
    curr, prev, ytd = get_price_metrics(sid)
    m = v['sh'] * curr
    total_mkt += m
    if sid != "CASH": today_delta += (curr - prev) * v['sh']
    
    b = 1.0
    if "L" in sid or "631" in sid: l_v += m; b = 2.0
    elif sid == "CASH" or "865B" in sid: c_v += m; b = 0.0
    else: s_v += m
    beta_sum += (b * m)
    active_data[sid] = {"sh": v['sh'], "curr": curr, "m": m, "avg": v.get('avg', 1.0), "beta": b}

curr_beta = (beta_sum / total_mkt) if total_mkt > 0 else 0.0
if total_mkt != 0:
    s_p, l_p = round(s_v/total_mkt*100, 1), round(l_v/total_mkt*100, 1)
    c_p = round(100.0 - s_p - l_p, 1)
else: s_p = l_p = c_p = 0.0

# --- 5. 畫面呈現 ---
st.markdown(f"#### 🛡️ 退休戰情室 V78.6")

# 🌟 強制 4 欄一列
st.markdown(f"""
<div class="metric-grid">
    <div class="metric-card"><div class="label-bright">💵 USD/TWD</div><div class="val-main" style="color:#58a6ff">{fx:.3f}</div></div>
    <div class="metric-card"><div class="label-bright">💰 總市值</div><div class="val-main" style="color:#00d4ff">${int(total_mkt):,}</div></div>
    <div class="metric-card"><div class="label-bright">📈 今日損益</div><div class="val-main {'up' if today_delta>=0 else 'down'}">${int(today_delta):,}</div></div>
    <div class="metric-card"><div class="label-bright">📊 累計損益</div><div class="val-main {'up' if (total_mkt-total_capital)>=0 else 'down'}">${int(total_mkt-total_capital):,}</div><div style="color:#ffffff; font-size:0.8rem;">本金: ${int(total_capital):,}</div></div>
</div>
""", unsafe_allow_html=True)

# --- 6. 配置現況 ---
t1, t2 = st.columns([1, 1])
with t1: st.write("⚖️ **配置現況**")
with t2: st.markdown(f"<div style='text-align:right;'><span class='beta-tag'>組合 Beta: {curr_beta:.2f}</span></div>", unsafe_allow_html=True)

st.markdown(f"""
<div class="responsive-grid">
    <div class="info-box b-blue"><div class="label-bright">現況 股票</div><div class="box-pct">{s_p}%</div><div class="box-amt">${int(s_v):,}</div></div>
    <div class="info-box b-purple"><div class="label-bright">現況 槓桿</div><div class="box-pct">{l_p}%</div><div class="box-amt">${int(l_v):,}</div></div>
    <div class="info-box b-green"><div class="label-bright">現況 類現金</div><div class="box-pct">{c_p}%</div><div class="box-amt">${int(c_v):,}</div></div>
</div>
""", unsafe_allow_html=True)

# 目標與 Beta
t_c1, t_c2, t_c3 = st.columns(3)
with t_c1: ts_pct = st.number_input("股票目標 %", 0, 100, 50, step=5)
with t_c2: tl_pct = st.number_input("槓桿目標 %", 0, 100, 10, step=5)
with t_c3: 
    tc_pct = 100 - ts_pct - tl_pct
    t_beta = (ts_pct * 1.0 + tl_pct * 2.0) / 100
    st.markdown(f"<div style='margin-top:25px; text-align:right;'><span class='beta-tag' style='border:1px solid #ff9f1c'>目標 Beta: {t_beta:.2f}</span></div>", unsafe_allow_html=True)

ts_amt, tl_amt, tc_amt = total_mkt*ts_pct/100, total_mkt*tl_pct/100, total_mkt*tc_pct/100

st.markdown(f"""
<div class="responsive-grid">
    <div class="info-box b-blue" style="background:#1c2128; opacity:0.8;"><div class="label-bright">🎯 目標 股票</div><div class="box-pct">{ts_pct}%</div><div class="box-amt">${int(ts_amt):,}</div></div>
    <div class="info-box b-purple" style="background:#1c2128; opacity:0.8;"><div class="label-bright">🎯 目標 槓桿</div><div class="box-pct">{tl_pct}%</div><div class="box-amt">${int(tl_amt):,}</div></div>
    <div class="info-box b-green" style="background:#1c2128; opacity:0.8;"><div
