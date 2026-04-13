import streamlit as st
import pandas as pd
import yfinance as yf
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import plotly.graph_objects as go
import re

# --- 1. 核心連線設定 ---
st.set_page_config(page_title="專業退休戰情室 V77.5", layout="wide")
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

# --- 2. 數據引擎：智能代號識別 ---
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
                # 🌟 補零邏輯：3位數(ETF)才補零，4位數(個股)保持原樣
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

# --- 3. 視覺樣式優化 (超高對比) ---
st.markdown("""
<style>
    /* 全域字體與背景 */
    .stApp { background-color: #0d1117; }
    
    /* 頂部指標區文字加亮 */
    .metric-box { background: #1c2128; border: 1px solid #444c56; border-radius: 12px; padding: 15px; text-align: center; }
    .label-bright { color: #ffffff !important; font-size: 1.1rem; font-weight: 500; margin-bottom: 5px; }
    .val-main { font-size: 2.2rem; font-weight: 800; font-family: 'Consolas', monospace; }
    
    /* 方塊容器 */
    .card-row { display: flex; justify-content: space-around; gap: 15px; margin-bottom: 25px; }
    .info-card { background: #161b22; border: 1px solid #30363d; border-radius: 12px; padding: 18px; flex: 1; text-align: center; }
    
    /* 文字清晰度強化 */
    .sub-label { color: #f0f6fc !important; font-size: 1.05rem; font-weight: bold; margin-bottom: 8px; }
    .pct-val { font-size: 2rem; font-weight: 900; margin-bottom: 5px; }
    .amt-val { font-family: 'Consolas'; font-size: 1.25rem; font-weight: 400; }
    
    /* 顏色定義 */
    .c-stock { color: #58a6ff; } .b-stock { border-top: 6px solid #58a6ff; }
    .c-lever { color: #bc8cff; } .b-lever { border-top: 6px solid #bc8cff; }
    .c-cash { color: #3fb950; } .b-cash { border-top: 6px solid #3fb950; }
    
    /* 表格清晰化 */
    table { width: 100%; border-collapse: collapse; font-size: 1.3rem !important; }
    th { background: #1c2128 !important; color: #ffffff !important; font-weight: 900 !important; padding: 15px !important; }
    td { padding: 15px !important; border-bottom: 1px solid #30363d !important; color: #e6edf3 !important; }
    b { color: #ffffff !important; }
    .up-txt { color: #ff3e3e; font-weight: bold; } .down-txt { color: #3fb950; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# --- 4. 數據整合 ---
df_hist, cur_stocks, total_capital = fetch_cloud_data()
fx = yf.Ticker("TWD=X").fast_info.last_price or 32.2

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
    active_data[sid] = {"sh": v['sh'], "curr": curr, "m": m, "avg": v['avg'], "ytd": ytd}

curr_beta = (beta_sum / total_mkt) if total_mkt > 0 else 0.0

# --- 5. 頂部儀表板 (文字強化版) ---
st.title("🛡️ 專業退休戰情室 V77.5")

m1, m2, m3, m4 = st.columns(4)
with m1: st.markdown(f"<div class='metric-box'><div class='label-bright'>💵 USD/TWD 匯率</div><div class='val-main' style='color:#58a6ff'>{fx:.3f}</div></div>", unsafe_allow_html=True)
with m2: st.markdown(f"<div class='metric-box'><div class='label-bright'>💰 總市值 (NTD)</div><div class='val-main' style='color:#00d4ff'>${int(total_mkt):,}</div></div>", unsafe_allow_html=True)
with m3:
    c = "up-txt" if today_delta >= 0 else "down-txt"
    st.markdown(f"<div class='metric-box'><div class='label-bright'>📈 今日跳動損益</div><div class='val-main {c}'>${int(today_delta):,}</div></div>", unsafe_allow_html=True)
with m4:
    net = total_mkt - total_capital
    c = "up-txt" if net >= 0 else "down-txt"
    st.markdown(f"<div class='metric-box'><div class='label-bright'>📊 累計資產損益</div><div class='val-main {c}'>${int(net):,}</div><div style='color:#ffffff; font-size:0.9rem;'>本金: ${int(total_capital):,}</div></div>", unsafe_allow_html=True)

st.divider()

# --- 6. 配置對照 (目標數值化與美化) ---
st.subheader("⚖️ 配置現況與目標對帳")

# 1. 現況卡片
st.markdown(f"""
<div class='card-row'>
    <div class='info-card b-stock'><div class='sub-label'>現況 股票</div><div class='pct-val c-stock'>{(s_val/total_mkt*100) if total_mkt>0 else 0:.1f}%</div><div class='amt-val c-stock'>${int(s_val):,}</div></div>
    <div class='info-card b-lever'><div class='sub-label'>現況 槓桿</div><div class='pct-val c-lever'>{(l_val/total_mkt*100) if total_mkt>0 else 0:.1f}%</div><div class='amt-val c-lever'>${int(l_val):,}</div></div>
    <div class='info-card b-cash'><div class='sub-label'>現況 類現金</div><div class='pct-val c-cash'>{(c_val/total_mkt*100) if total_mkt>0 else 0:.1f}%</div><div class='amt-val c-cash'>${int(c_val):,}</div></div>
</div>
""", unsafe_allow_html=True)

# 2. 目標調整與計算
t_c1, t_c2, t_c3 = st.columns(3)
with t_c1: ts_pct = st.number_input("股票目標 %", 0, 100, 50, step=5)
with t_c2: tl_pct = st.number_input("槓桿目標 %", 0, 100, 10, step=5)
with t_c3: tc_pct = 100 - ts_pct - tl_pct; st.info(f"類現金目標: {tc_pct}%")

ts_amt, tl_amt, tc_amt = total_mkt*ts_pct/100, total_mkt*tl_pct/100, total_mkt*tc_pct/100
t_beta = (ts_pct*1.0 + tl_pct*2.0)/100

# 3. 目標卡片 (實體邊框加強版)
st.markdown(f"""
<div class='card-row'>
    <div class='info-card b-stock' style='background:#1c2128'><div class='sub-label'>🎯 目標 股票</div><div class='pct-val c-stock' style='opacity:0.8'>{ts_pct}%</div><div class='amt-val c-stock'>${int(ts_amt):,}</div></div>
    <div class='info-card b-lever' style='background:#1c2128'><div class='sub-label'>🎯 目標 槓桿</div><div class='pct-val c-lever' style='opacity:0.8'>{tl_pct}%</div><div class='amt-val c-lever'>${int(tl_amt):,}</div></div>
    <div class='info-card b-cash' style='background:#1c2128'><div class='sub-label'>🎯 目標 類現金</div><div class='pct-val c-cash' style='opacity:0.8'>{tc_pct}%</div><div class='amt-val c-cash'>${int(tc_amt):,}</div></div>
</div>
<div style='text-align:right; margin-top:-10px; margin-bottom:10px;'>
    <span style='color:#8b949e; font-size:0.9rem;'>現況 Beta: {curr_beta:.2f} ➔ </span>
    <span style='color:#ff9f1c; font-weight:bold; font-size:1rem; border:1px solid #ff9f1c; padding:2px 8px; border-radius:5px;'>目標 Beta: {t_beta:.2f}</span>
</div>
""", unsafe_allow_html=True)

st.divider()

# --- 7. 資產明細與建議 (表格文字強化) ---
st.subheader("📋 資產部位明細與再平衡操作")
if active_data:
    html = "<table><thead><tr><th>標的</th><th>持股數</th><th>報價</th><th>市值</th><th>報酬</th><th>佔比</th><th>操作建議</th></tr></thead><tbody>"
    for sid, d in active_data.items():
        pct = (d['m']/total_mkt*100) if total_mkt>0 else 0
        roi = f"{((d['curr']-d['avg'])/d['avg']*100):.1f}%" if d['avg']>0 else "0%"
        
        advice = "-"
        if sid == "00662":
            diff = ts_amt - s_val
            sh = int(diff / d['curr'])
            if abs(sh) > 0: advice = f"<span class='{'up-txt' if sh>0 else 'down-txt'}'>{'加碼' if sh>0 else '減碼'} {abs(sh):,} 股</span>"
        elif "L" in sid:
            diff = tl_amt - l_val
            sh = int(diff / d['curr'])
            if abs(sh) > 0: advice = f"<span class='{'up-txt' if sh>0 else 'down-txt'}'>{'加碼' if sh>0 else '減碼'} {abs(sh):,} 股</span>"
        elif sid == "CASH" or "865B" in sid:
            advice = f"調整額 ${int(tc_amt - c_val):,}"

        html += f"<tr><td><b>{sid}</b></td><td>{int(d['sh']):,}</td><td>{d['curr']:.2f}</td><td>${int(d['m']):,}</td><td>{roi}</td><td>{pct:.1f}%</td><td>{advice}</td></tr>"
    html += "</tbody></table>"
    st.write(html, unsafe_allow_html=True)

with st.sidebar:
    st.header("🖊️ 交易錄入")
    op = st.selectbox("動作類型", ["買入", "賣出", "入金", "出金"])
    raw_sid = st.text_input("代號", value="CASH").upper().strip()
    sid_in = raw_sid.zfill(5) if raw_sid.isdigit() and len(raw_sid) <= 3 else raw_sid
    sh_in = st.number_input("數量", min_value=0.0, step=100.0)
    pr_in = st.number_input("單價", min_value=0.0, value=1.0)
    if st.button("💾 同步存檔"):
        client = get_client()
        ws = client.open_by_key(GS_ID).worksheet("Transactions")
        ws.append_row([datetime.now().strftime("%Y-%m-%d"), op, sid_in, sh_in, pr_in, ""])
        st.cache_data.clear(); st.rerun()
