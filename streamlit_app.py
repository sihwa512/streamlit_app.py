import streamlit as st
import pandas as pd
import yfinance as yf
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import re

# --- 1. 核心連線設定 ---
st.set_page_config(page_title="退休戰情室 V78.2", layout="wide")
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

# --- 2. 數據引擎：聯動現金與百分比修正 ---
@st.cache_data(ttl=60)
def fetch_cloud_data():
    client = get_client()
    if not client: return pd.DataFrame(), {}, 0.0
    try:
        doc = client.open_by_key(GS_ID)
        df_t = pd.DataFrame(doc.worksheet("Transactions").get_all_records())
        stocks = {}
        total_cap = 0.0 
        running_cash = 0.0
        
        if not df_t.empty:
            df_t['sh'] = pd.to_numeric(df_t['sh'], errors='coerce').fillna(0)
            df_t['pr'] = pd.to_numeric(df_t['pr'], errors='coerce').fillna(0)
            for _, r in df_t.iterrows():
                raw_id = str(r['id']).upper().strip()
                sid = raw_id.zfill(5) if raw_id.isdigit() and len(raw_id) <= 3 else raw_id
                
                if r['type'] == "入金":
                    total_cap += r['sh']; running_cash += r['sh']
                elif r['type'] == "出金":
                    total_cap -= r['sh']; running_cash -= r['sh']
                elif r['type'] == "買入":
                    if sid not in stocks: stocks[sid] = {"sh": 0.0, "cost": 0.0}
                    stocks[sid]["sh"] += r['sh']
                    stocks[sid]["cost"] += (r['sh'] * r['pr'])
                    running_cash -= (r['sh'] * r['pr'])
                elif r['type'] == "賣出":
                    if sid in stocks and stocks[sid]["sh"] > 0:
                        stocks[sid]["cost"] -= (stocks[sid]["cost"] * (r['sh']/stocks[sid]["sh"]))
                        stocks[sid]["sh"] -= r['sh']
                        running_cash += (r['sh'] * r['pr'])
            
            stocks["CASH"] = {"sh": running_cash, "cost": running_cash, "avg": 1.0}
            
        for s in stocks:
            if s != "CASH":
                stocks[s]["avg"] = stocks[s]["cost"]/stocks[s]["sh"] if stocks[s]["sh"] > 0 else 0
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

# --- 3. 視覺樣式 (RWD 高對比) ---
st.markdown("""
<style>
    .stApp { background-color: #0d1117; color: #e6edf3; }
    .responsive-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 15px; margin-bottom: 20px; }
    .metric-card { background: #1c2128; border: 1px solid #444c56; border-radius: 12px; padding: 20px; text-align: center; }
    .label-bright { color: #ffffff !important; font-size: 1.1rem; font-weight: 600; margin-bottom: 8px; }
    .val-main { font-size: 2.3rem; font-weight: 800; font-family: 'Consolas', monospace; }
    
    .info-box { background: #161b22; border-radius: 12px; padding: 20px; text-align: center; border: 1px solid #30363d; }
    .b-blue { border-top: 6px solid #58a6ff; color: #58a6ff; }
    .b-purple { border-top: 6px solid #bc8cff; color: #bc8cff; }
    .b-green { border-top: 6px solid #3fb950; color: #3fb950; }
    
    table { width: 100%; border-collapse: collapse; font-size: 1.3rem !important; }
    th { background: #1c2128 !important; color: #ffffff !important; padding: 15px !important; text-align: left !important; }
    td { padding: 15px !important; border-bottom: 1px solid #30363d !important; }
    .up { color: #ff3e3e; font-weight: bold; } .down { color: #3fb950; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# --- 4. 數據整合計算 ---
df_hist, cur_stocks, total_capital = fetch_cloud_data()
fx = yf.Ticker("TWD=X").fast_info.last_price or 32.3

total_mkt, today_delta = 0.0, 0.0
s_v, l_v, c_v = 0.0, 0.0, 0.0
active_data = {}

for sid, v in cur_stocks.items():
    if v['sh'] == 0 and sid != "CASH": continue
    curr, prev, ytd = get_price_metrics(sid)
    m = v['sh'] * curr
    total_mkt += m
    if sid != "CASH": today_delta += (curr - prev) * v['sh']
    if "L" in sid or "631" in sid: l_v += m
    elif sid == "CASH" or "865B" in sid: c_v += m
    else: s_v += m
    active_data[sid] = {"sh": v['sh'], "curr": curr, "m": m, "avg": v.get('avg', 1.0)}

# 🌟 百分比校正邏輯：確保加起來剛好 100%
if total_mkt != 0:
    s_p = round(s_v / total_mkt * 100, 1)
    l_p = round(l_v / total_mkt * 100, 1)
    c_p = round(100.0 - s_p - l_p, 1) # 殘值校正法
else:
    s_p = l_p = c_p = 0.0

# --- 5. 畫面呈現 ---
st.title("🛡️ 退休戰情室 V78.2")

st.markdown(f"""
<div class="responsive-grid">
    <div class="metric-card"><div class="label-bright">💵 USD/TWD</div><div class="val-main" style="color:#58a6ff">{fx:.3f}</div></div>
    <div class="metric-card"><div class="label-bright">💰 總資產市值</div><div class="val-main" style="color:#00d4ff">${int(total_mkt):,}</div></div>
    <div class="metric-card"><div class="label-bright">📈 今日損益</div><div class="val-main {'up' if today_delta>=0 else 'down'}">${int(today_delta):,}</div></div>
    <div class="metric-card"><div class="label-bright">📊 累計總盈虧</div><div class="val-main {'up' if (total_mkt-total_capital)>=0 else 'down'}">${int(total_mkt-total_capital):,}</div><div style="color:#ffffff; font-size:0.9rem;">本金: ${int(total_capital):,}</div></div>
</div>
""", unsafe_allow_html=True)

st.divider()

# --- 6. 修正後的配置方塊 ---
st.subheader("⚖️ 資產配置現況 (精準對帳版)")
st.markdown(f"""
<div class="responsive-grid">
    <div class="info-box b-blue"><div class="label-bright">現況 股票</div><div style="font-size:2.2rem; font-weight:900;">{s_p}%</div><div style="font-size:1.2rem;">${int(s_v):,}</div></div>
    <div class="info-box b-purple"><div class="label-bright">現況 槓桿</div><div style="font-size:2.2rem; font-weight:900;">{l_p}%</div><div style="font-size:1.2rem;">${int(l_v):,}</div></div>
    <div class="info-box b-green"><div class="label-bright">現況 類現金</div><div style="font-size:2.2rem; font-weight:900;">{c_p}%</div><div style="font-size:1.2rem;">${int(c_v):,}</div></div>
</div>
""", unsafe_allow_html=True)

# 目標設定
t_c1, t_c2, t_c3 = st.columns(3)
with t_c1: ts_pct = st.number_input("股票目標 %", 0, 100, 50, step=5)
with t_c2: tl_pct = st.number_input("槓桿目標 %", 0, 100, 10, step=5)
with t_c3: tc_pct = 100 - ts_pct - tl_pct; st.info(f"類現金目標: {tc_pct}%")

ts_amt, tl_amt, tc_amt = total_mkt*ts_pct/100, total_mkt*tl_pct/100, total_mkt*tc_pct/100

st.markdown(f"""
<div class="responsive-grid">
    <div class="info-box b-blue" style="background:#1c2128; opacity:0.85;"><div class="label-bright">🎯 目標 股票</div><div style="font-size:1.9rem; font-weight:800;">{ts_pct}%</div><div>${int(ts_amt):,}</div></div>
    <div class="info-box b-purple" style="background:#1c2128; opacity:0.85;"><div class="label-bright">🎯 目標 槓桿</div><div style="font-size:1.9rem; font-weight:800;">{tl_pct}%</div><div>${int(tl_amt):,}</div></div>
    <div class="info-box b-green" style="background:#1c2128; opacity:0.85;"><div class="label-bright">🎯 目標 類現金</div><div style="font-size:1.9rem; font-weight:800;">{tc_pct}%</div><div>${int(tc_amt):,}</div></div>
</div>
""", unsafe_allow_html=True)

st.divider()

# --- 7. 資產明細表 ---
st.subheader("📋 資產明細與再平衡操作")
if active_data:
    html = "<div style='overflow-x:auto;'><table><thead><tr><th>標的</th><th>持股數</th><th>報價</th><th>市值</th><th>報酬</th><th>佔比</th><th>操作建議</th></tr></thead><tbody>"
    for sid, d in active_data.items():
        if sid == "CASH" and d['sh'] == 0: continue
        pct = (d['m']/total_mkt*100) if total_mkt!=0 else 0
        roi = f"{((d['curr']-d['avg'])/d['avg']*100):.1f}%" if d['avg']>0 else "0%"
        advice = "-"
        if sid == "00662":
            diff = ts_amt - s_v
            sh = int(diff / d['curr'])
            if abs(sh) > 0: advice = f"<span class='{'up' if sh>0 else 'down'}'>{'加碼' if sh>0 else '減碼'} {abs(sh):,} 股</span>"
        elif "L" in sid:
            diff = tl_amt - l_v
            sh = int(diff / d['curr'])
            if abs(sh) > 0: advice = f"<span class='{'up' if sh>0 else 'down'}'>{'加碼' if sh>0 else '減碼'} {abs(sh):,} 股</span>"
            
        html += f"<tr><td><b>{sid}</b></td><td>{int(d['sh']):,}</td><td>{d['curr']:.2f}</td><td>${int(d['m']):,}</td><td>{roi}</td><td>{pct:.1f}%</td><td>{advice}</td></tr>"
    html += "</tbody></table></div>"
    st.write(html, unsafe_allow_html=True)

with st.sidebar:
    st.header("🖊️ 快速錄入")
    op = st.selectbox("動作類型", ["買入", "賣出", "入金", "出金"])
    raw_sid = st.text_input("代號", value="00662").upper().strip()
    sid_in = raw_sid.zfill(5) if raw_sid.isdigit() and len(raw_sid) <= 3 else raw_sid
    sh_in = st.number_input("數量/金額", min_value=0.0, step=100.0)
    pr_in = st.number_input("單價", min_value=0.0, value=1.0)
    if st.button("💾 確認存檔"):
        client = get_client()
        ws = client.open_by_key(GS_ID).worksheet("Transactions")
        ws.append_row([datetime.now().strftime("%Y-%m-%d"), op, sid_in, sh_in, pr_in, ""])
        st.cache_data.clear(); st.rerun()
