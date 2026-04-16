import streamlit as st
import pandas as pd
import yfinance as yf
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import plotly.graph_objects as go
import re

# --- 1. 連線設定 ---
st.set_page_config(page_title="退休戰情室 V79.0", layout="wide")
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
    if not client: return pd.DataFrame(), {}, 0.0, pd.DataFrame()
    try:
        doc = client.open_by_key(GS_ID)
        # A. 讀取交易流水
        df_t = pd.DataFrame(doc.worksheet("Transactions").get_all_records())
        # B. 讀取歷史快照 (用於昨日對標與圖表)
        try:
            df_snap = pd.DataFrame(doc.worksheet("DailySnapshots").get_all_records())
        except:
            ws_new = doc.add_worksheet(title="DailySnapshots", rows="1000", cols="5")
            ws_new.append_row(["date", "total_mkt"])
            df_snap = pd.DataFrame(columns=["date", "total_mkt"])
            
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
        return df_t, stocks, total_cap, df_snap
    except: return pd.DataFrame(), {}, 0.0, pd.DataFrame()

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

# --- 3. 視覺樣式 ---
st.markdown("""
<style>
    .stApp { background-color: #0d1117; color: #e6edf3; }
    .metric-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin-bottom: 12px; }
    .metric-card { background: #1c2128; border: 1px solid #444c56; border-radius: 10px; padding: 12px; text-align: center; }
    .label-bright { color: #ffffff !important; font-size: 1.0rem; font-weight: 600; }
    .val-main { font-size: 1.9rem; font-weight: 800; font-family: 'Consolas', monospace; line-height: 1.1; }
    .val-sub { font-size: 0.85rem; color: #8b949e; margin-top: 4px; }
    
    .info-box { background: #161b22; border-radius: 10px; padding: 12px; text-align: center; border: 1px solid #30363d; }
    .box-pct { font-size: 1.7rem; font-weight: 900; line-height: 1.1; }
    
    .b-blue { border-top: 5px solid #58a6ff; color: #58a6ff; }
    .b-purple { border-top: 6px solid #bc8cff; color: #bc8cff; }
    .b-green { border-top: 6px solid #3fb950; color: #3fb950; }
    
    table { width: 100%; border-collapse: collapse; font-size: 1.15rem !important; }
    th { background: #1c2128 !important; color: #ffffff !important; padding: 8px !important; }
    td { padding: 8px !important; border-bottom: 1px solid #30363d !important; }
    .up { color: #ff3e3e; font-weight: bold; } .down { color: #3fb950; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# --- 4. 數據整合 ---
df_hist, cur_stocks, total_capital, df_snap = fetch_cloud_data()
fx = yf.Ticker("TWD=X").fast_info.last_price or 32.3

total_mkt = 0.0
s_v, l_v, c_v = 0.0, 0.0, 0.0
active_data = {}

for sid, v in cur_stocks.items():
    if v['sh'] == 0 and sid != "CASH": continue
    curr, prev, ytd = get_price_metrics(sid)
    m = v['sh'] * curr
    total_mkt += m
    if "L" in sid or "631" in sid: l_v += m
    elif sid == "CASH" or "865B" in sid: c_v += m
    else: s_v += m
    active_data[sid] = {"sh": v['sh'], "curr": curr, "m": m, "avg": v.get('avg', 1.0), "ytd": ytd}

# 🌟 昨日總市值邏輯：從快照中抓取最後一筆非今天的紀錄
yesterday_mkt = 0.0
if not df_snap.empty:
    valid_snaps = df_snap[df_snap['date'] != datetime.now().strftime("%Y-%m-%d")]
    if not valid_snaps.empty:
        yesterday_mkt = float(valid_snaps.iloc[-1]['total_mkt'])

today_delta = total_mkt - yesterday_mkt if yesterday_mkt > 0 else 0.0

# --- 5. 儀表板 ---
st.markdown(f"#### 🛡️ 退休戰情室 V79.0")

st.markdown(f"""
<div class="metric-grid">
    <div class="metric-card"><div class="label-bright">💵 USD/TWD</div><div class="val-main" style="color:#58a6ff">{fx:.3f}</div></div>
    <div class="metric-card">
        <div class="label-bright">💰 總市值</div>
        <div class="val-main" style="color:#00d4ff">${int(total_mkt):,}</div>
        <div class="val-sub">昨日: ${int(yesterday_mkt):,}</div>
    </div>
    <div class="metric-card">
        <div class="label-bright">📈 今日損益 (快照)</div>
        <div class="val-main {'up' if today_delta>=0 else 'down'}">${int(today_delta):,}</div>
        <div class="val-sub">基於最後一次快照對比</div>
    </div>
    <div class="metric-card">
        <div class="label-bright">📊 累計總損益</div>
        <div class="val-main {'up' if (total_mkt-total_capital)>=0 else 'down'}">${int(total_mkt-total_capital):,}</div>
        <div style="color:#ffffff; font-size:0.8rem;">本金: ${int(total_capital):,}</div>
    </div>
</div>
""", unsafe_allow_html=True)

# --- 6. 每日總市值圖 ---
if not df_snap.empty:
    st.write("📈 **資產成長曲線 (每日總市值圖)**")
    fig = go.Figure(go.Scatter(x=df_snap['date'], y=df_snap['total_mkt'], fill='tozeroy', line=dict(color='#00d4ff', width=3)))
    fig.update_layout(template="plotly_dark", height=250, margin=dict(l=10,r=10,t=10,b=10), paper_bgcolor='rgba(0,0,0,0)', xaxis=dict(showgrid=False), yaxis=dict(showgrid=True, gridcolor='#30363d'))
    st.plotly_chart(fig, use_container_width=True)

st.divider()

# --- 7. 配置現況與目標 ---
s_p, l_p = round(s_v/total_mkt*100, 1), round(l_v/total_mkt*100, 1) if total_mkt>0 else (0,0)
c_p = round(100.0 - s_p - l_p, 1)

st.markdown(f"""
<div class="responsive-grid" style="display:grid; grid-template-columns: repeat(3, 1fr); gap:10px;">
    <div class="info-box b-blue"><div class="label-bright">現況 股票</div><div class="box-pct">{s_p}%</div><div>${int(s_v):,}</div></div>
    <div class="info-box b-purple"><div class="label-bright">現況 槓桿</div><div class="box-pct">{l_p}%</div><div>${int(l_v):,}</div></div>
    <div class="info-box b-green"><div class="label-bright">現況 類現金</div><div class="box-pct">{c_p}%</div><div>${int(c_v):,}</div></div>
</div>
""", unsafe_allow_html=True)

# 目標調整
t_c1, t_c2, t_c3 = st.columns(3)
with t_c1: ts_pct = st.number_input("股票目標 %", 0, 100, 50, step=5)
with t_c2: tl_pct = st.number_input("槓桿目標 %", 0, 100, 10, step=5)
with t_c3: tc_pct = 100 - ts_pct - tl_pct; st.info(f"類現金目標: {tc_pct}%")

ts_amt, tl_amt, tc_amt = total_mkt*ts_pct/100, total_mkt*tl_pct/100, total_mkt*tc_pct/100

st.divider()

# --- 8. 資產明細表 (加入成本均價與 YTD) ---
st.write("📋 **資產部位明細 (含成本均價、YTD)**")
if active_data:
    html = "<div><table><thead><tr><th>標的</th><th>持股數</th><th>報價</th><th>成本均價</th><th>市值</th><th>報酬</th><th>YTD</th><th>佔比</th><th>操作建議</th></tr></thead><tbody>"
    for sid, d in active_data.items():
        if sid == "CASH" and d['sh'] == 0: continue
        pct = (d['m']/total_mkt*100) if total_mkt!=0 else 0
        roi = f"{((d['curr']-d['avg'])/d['avg']*100):.1f}%" if d['avg']>0 else "0%"
        ytd_roi = f"{((d['curr']-d['ytd'])/d['ytd']*100):.1f}%" if d['ytd']>0 else "0%"
        
        advice = "-"
        if sid == "00662":
            sh = int((ts_amt - s_v) / d['curr'])
            if abs(sh) > 0: advice = f"<span class='{'up' if sh>0 else 'down'}'>{'加碼' if sh>0 else '減碼'} {abs(sh):,} 股</span>"
        elif "L" in sid:
            sh = int((tl_amt - l_v) / d['curr'])
            if abs(sh) > 0: advice = f"<span class='{'up' if sh>0 else 'down'}'>{'加碼' if sh>0 else '減碼'} {abs(sh):,} 股</span>"
            
        html += f"<tr><td><b>{sid}</b></td><td>{int(d['sh']):,}</td><td>{d['curr']:.2f}</td><td>{d['avg']:.2f}</td><td>${int(d['m']):,}</td><td>{roi}</td><td>{ytd_roi}</td><td>{pct:.1f}%</td><td>{advice}</td></tr>"
    html += "</tbody></table></div>"
    st.write(html, unsafe_allow_html=True)

with st.sidebar:
    st.header("🖊️ 數據操作")
    if st.button("📸 紀錄今日市值快照", use_container_width=True):
        client = get_client()
        ws_snap = client.open_by_key(GS_ID).worksheet("DailySnapshots")
        today_str = datetime.now().strftime("%Y-%m-%d")
        # 避免重複紀錄同一天
        existing_dates = ws_snap.col_values(1)
        if today_str in existing_dates:
            st.sidebar.warning("今天已經紀錄過快照了！")
        else:
            ws_snap.append_row([today_str, int(total_mkt)])
            st.sidebar.success(f"成功紀錄 {today_str} 市值！")
            st.cache_data.clear(); st.rerun()

    st.divider()
    op = st.selectbox("類型", ["買入", "賣出", "入金", "出金"])
    raw_sid = st.text_input("代號", value="00662").upper().strip()
    sid_in = raw_sid.zfill(5) if raw_sid.isdigit() and len(raw_sid) <= 3 else raw_sid
    sh_in = st.number_input("數量/金額", min_value=0.0, step=100.0)
    pr_in = st.number_input("單價", min_value=0.0, value=1.0)
    if st.button("💾 同步交易資料", use_container_width=True):
        client = get_client()
        ws = client.open_by_key(GS_ID).worksheet("Transactions")
        ws.append_row([datetime.now().strftime("%Y-%m-%d"), op, sid_in, sh_in, pr_in, ""])
        st.cache_data.clear(); st.rerun()
