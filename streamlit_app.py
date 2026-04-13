import streamlit as st
import pandas as pd
import yfinance as yf
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import plotly.graph_objects as go
import re

# --- 1. 核心連線設定 ---
st.set_page_config(page_title="退休戰情室 V78.0", layout="wide")
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
                raw_id = str(r['id']).upper().strip()
                # 補零邏輯：ETF(3位內)補至5位，個股(4位)不變
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

# --- 3. 手機版 RWD 視覺優化 ---
st.markdown("""
<style>
    /* 全域設定 */
    .stApp { background-color: #0d1117; color: #e6edf3; }
    
    /* 響應式卡片容器：手機變垂直，電腦變橫向 */
    .responsive-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
        gap: 15px;
        margin-bottom: 20px;
    }
    
    /* 專業指標方塊 */
    .metric-card {
        background: #1c2128;
        border: 1px solid #444c56;
        border-radius: 12px;
        padding: 20px;
        text-align: center;
        box-shadow: 0 4px 12px rgba(0,0,0,0.5);
    }
    .metric-label { color: #ffffff !important; font-size: 1.1rem; font-weight: 600; margin-bottom: 8px; }
    .metric-value { font-size: 2.3rem; font-weight: 800; font-family: 'Consolas', monospace; }
    
    /* 再平衡卡片樣式 */
    .info-box {
        background: #161b22;
        border-radius: 12px;
        padding: 18px;
        text-align: center;
        border: 1px solid #30363d;
    }
    .box-title { color: #ffffff !important; font-size: 1.1rem; font-weight: bold; margin-bottom: 10px; }
    .box-pct { font-size: 2rem; font-weight: 900; }
    .box-amt { font-family: 'Consolas'; font-size: 1.2rem; opacity: 0.9; }
    
    .b-blue { border-top: 6px solid #58a6ff; color: #58a6ff; }
    .b-purple { border-top: 6px solid #bc8cff; color: #bc8cff; }
    .b-green { border-top: 6px solid #3fb950; color: #3fb950; }
    
    /* 表格手機優化：允許橫向捲動 */
    .table-container { overflow-x: auto; width: 100%; border-radius: 8px; }
    table { width: 100%; min-width: 600px; border-collapse: collapse; font-size: 1.25rem !important; }
    th { background: #1c2128 !important; color: #ffffff !important; padding: 15px !important; text-align: left !important; font-weight: bold; }
    td { padding: 15px !important; border-bottom: 1px solid #30363d !important; color: #e6edf3 !important; }
    
    /* 手機版字體微調 */
    @media (max-width: 600px) {
        .metric-value { font-size: 1.9rem; }
        .box-pct { font-size: 1.7rem; }
    }
</style>
""", unsafe_allow_html=True)

# --- 4. 數據加載 ---
df_hist, cur_stocks, total_capital = fetch_cloud_data()
fx = yf.Ticker("TWD=X").fast_info.last_price or 32.25

total_mkt, today_delta = 0.0, 0.0
s_val, l_val, c_val = 0.0, 0.0, 0.0
beta_sum = 0.0
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

# --- 5. 畫面呈現 ---
st.title("🛡️ 專業退休戰情室 V78.0")

# 響應式頂部指標 (手機會變 2x2 或 1x4)
st.markdown(f"""
<div class="responsive-grid">
    <div class="metric-card"><div class="metric-label">💵 USD/TWD</div><div class="metric-value" style="color:#58a6ff">{fx:.3f}</div></div>
    <div class="metric-card"><div class="metric-label">💰 總市值</div><div class="metric-value" style="color:#00d4ff">${int(total_mkt):,}</div></div>
    <div class="metric-card"><div class="metric-label">📈 今日跳動</div><div class="metric-value {'up-txt' if today_delta>=0 else 'down-txt'}" style="color:{'#ff3e3e' if today_delta>=0 else '#3fb950'}">${int(today_delta):,}</div></div>
    <div class="metric-card"><div class="metric-label">📊 累計損益</div><div class="metric-value {'up-txt' if (total_mkt-total_capital)>=0 else 'down-txt'}" style="color:{'#ff3e3e' if (total_mkt-total_capital)>=0 else '#3fb950'}">${int(total_mkt-total_capital):,}</div></div>
</div>
""", unsafe_allow_html=True)

st.divider()

# --- 6. 目標再平衡區 (響應式方塊) ---
st.subheader("⚖️ 資產配置現況與目標")

# 現況方塊
st.markdown(f"""
<div class="responsive-grid">
    <div class="info-box b-blue"><div class="box-title">現況 股票</div><div class="box-pct">{(s_val/total_mkt*100) if total_mkt>0 else 0:.1f}%</div><div class="box-amt">${int(s_val):,}</div></div>
    <div class="info-box b-purple"><div class="box-title">現況 槓桿</div><div class="box-pct">{(l_val/total_mkt*100) if total_mkt>0 else 0:.1f}%</div><div class="box-amt">${int(l_val):,}</div></div>
    <div class="info-box b-green"><div class="box-title">現況 類現金</div><div class="box-pct">{(c_val/total_mkt*100) if total_mkt>0 else 0:.1f}%</div><div class="box-amt">${int(c_val):,}</div></div>
</div>
""", unsafe_allow_html=True)

# 目標調整
t_c1, t_c2, t_c3 = st.columns(3)
with t_c1: ts_pct = st.number_input("股票目標 %", 0, 100, 50, step=5)
with t_c2: tl_pct = st.number_input("槓桿目標 %", 0, 100, 10, step=5)
with t_c3: tc_pct = 100 - ts_pct - tl_pct; st.info(f"類現金目標: {tc_pct}%")

ts_amt, tl_amt, tc_amt = total_mkt*ts_pct/100, total_mkt*tl_pct/100, total_mkt*tc_pct/100

# 目標方塊
st.markdown(f"""
<div class="responsive-grid">
    <div class="info-box b-blue" style="background:#1c2128"><div class="box-title">🎯 目標 股票</div><div class="box-pct" style="opacity:0.8">{ts_pct}%</div><div class="box-amt">${int(ts_amt):,}</div></div>
    <div class="info-box b-purple" style="background:#1c2128"><div class="box-title">🎯 目標 槓桿</div><div class="box-pct" style="opacity:0.8">{tl_pct}%</div><div class="box-amt">${int(tl_amt):,}</div></div>
    <div class="info-box b-green" style="background:#1c2128"><div class="box-title">🎯 目標 類現金</div><div class="box-pct" style="opacity:0.8">{tc_pct}%</div><div class="box-amt">${int(tc_amt):,}</div></div>
</div>
""", unsafe_allow_html=True)

st.divider()

# --- 7. 資產明細表 (手機可左右滑動) ---
st.subheader("📋 資產部位明細與操作")
if active_data:
    html = "<div class='table-container'><table><thead><tr><th>標的</th><th>持股數</th><th>報價</th><th>市值</th><th>報酬</th><th>佔比</th><th>建議操作</th></tr></thead><tbody>"
    for sid, d in active_data.items():
        pct = (d['m']/total_mkt*100) if total_mkt>0 else 0
        roi = f"{((d['curr']-d['avg'])/d['avg']*100):.1f}%" if d['avg']>0 else "0%"
        advice = "-"
        if sid == "00662":
            diff = ts_amt - s_val
            sh = int(diff / d['curr'])
            if abs(sh) > 0: advice = f"<span style='color:{'#ff3e3e' if sh>0 else '#3fb950'}'>{'加碼' if sh>0 else '減碼'} {abs(sh):,} 股</span>"
        elif "L" in sid:
            diff = tl_amt - l_val
            sh = int(diff / d['curr'])
            if abs(sh) > 0: advice = f"<span style='color:{'#ff3e3e' if sh>0 else '#3fb950'}'>{'加碼' if sh>0 else '減碼'} {abs(sh):,} 股</span>"
            
        html += f"<tr><td><b>{sid}</b></td><td>{int(d['sh']):,}</td><td>{d['curr']:.2f}</td><td>${int(d['m']):,}</td><td>{roi}</td><td>{pct:.1f}%</td><td>{advice}</td></tr>"
    html += "</tbody></table></div>"
    st.write(html, unsafe_allow_html=True)

with st.sidebar:
    st.header("🖊️ 快速錄入")
    op = st.selectbox("類型", ["買入", "賣出", "入金", "出金"])
    raw_sid = st.text_input("代號", value="CASH").upper().strip()
    sid_in = raw_sid.zfill(5) if raw_sid.isdigit() and len(raw_sid) <= 3 else raw_sid
    sh_in = st.number_input("數量/金額", min_value=0.0, step=100.0)
    pr_in = st.number_input("單價", min_value=0.0, value=1.0)
    if st.button("💾 確認並存檔"):
        client = get_client()
        ws = client.open_by_key(GS_ID).worksheet("Transactions")
        ws.append_row([datetime.now().strftime("%Y-%m-%d"), op, sid_in, sh_in, pr_in, ""])
        st.cache_data.clear(); st.rerun()
