import streamlit as st
import pandas as pd
import yfinance as yf
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import plotly.graph_objects as go
import re
import pytz
import math

# --- 1. 核心連線設定 ---
st.set_page_config(page_title="退休戰情室 V84.0", layout="wide")
GS_ID = "1jgZhEi-nmaXGUa5fJaYwk79xE9-QG4LwhwV89xriGPs"
TW_TIMEZONE = pytz.timezone('Asia/Taipei')

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

# 🌟 強大防呆格式化函數 (防止 ValueError)
def fmt_int(val):
    if pd.isna(val) or math.isnan(val): return "0"
    try: return f"{int(float(val)):,}"
    except: return "0"

# --- 2. 數據引擎 ---
@st.cache_data(ttl=60)
def fetch_cloud_data():
    client = get_client()
    if not client: return pd.DataFrame(), {}, 0.0, pd.DataFrame()
    try:
        doc = client.open_by_key(GS_ID)
        df_t = pd.DataFrame(doc.worksheet("Transactions").get_all_records())
        try:
            df_snap = pd.DataFrame(doc.worksheet("DailySnapshots").get_all_records())
        except:
            ws_snap = doc.add_worksheet(title="DailySnapshots", rows="1000", cols="5")
            ws_snap.append_row(["date", "total_mkt"])
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
            hist = t.history(period="1mo").dropna(subset=['Close'])
            if not hist.empty:
                curr = hist['Close'].iloc[-1]
                prev = hist['Close'].iloc[-2] if len(hist) > 1 else curr
                ytd_hist = t.history(start=f"{datetime.now().year}-01-01").dropna(subset=['Close'])
                ytd_open = ytd_hist['Close'].iloc[0] if not ytd_hist.empty else curr
                
                # 安全轉換
                curr = float(curr) if pd.notna(curr) else 0.0
                prev = float(prev) if pd.notna(prev) else curr
                ytd_open = float(ytd_open) if pd.notna(ytd_open) else curr
                if curr > 0: return curr, prev, ytd_open
        except: continue
    return 0.0, 0.0, 0.0

# --- 3. 視覺樣式 (舒適護眼 + 防裁切) ---
st.markdown("""
<style>
    .stApp { background-color: #0d1117; color: #c9d1d9; }
    .metric-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 15px; margin-bottom: 25px; }
    .metric-card { background: #161b22; border: 1px solid #30363d; border-radius: 12px; padding: 22px 15px; text-align: center; }
    .label-bright { color: #8b949e; font-size: 1.05rem; font-weight: bold; margin-bottom: 10px; }
    .val-main { font-size: 2.2rem; font-weight: bold; color: #ffffff; font-family: 'Consolas', monospace; margin-bottom: 6px; line-height: 1.1; }
    .val-sub { font-size: 0.95rem; color: #8b949e; }
    .info-box { background: #161b22; border-radius: 12px; padding: 22px 15px; text-align: center; border: 1px solid #30363d; }
    .box-pct { font-size: 2rem; font-weight: bold; color: #ffffff; margin: 12px 0; }
    .b-blue { border-top: 5px solid #58a6ff; } .b-purple { border-top: 5px solid #bc8cff; } .b-green { border-top: 5px solid #3fb950; }
    .beta-tag { background: #21262d; color: #ff9f1c; padding: 6px 14px; border-radius: 6px; font-size: 1rem; font-weight: bold; font-family: 'Consolas'; border: 1px solid #ff9f1c; display: inline-block; }
    table { width: 100%; border-collapse: collapse; font-size: 1.15rem !important; }
    th { background: #21262d !important; color: #8b949e !important; padding: 14px !important; text-align: left !important; }
    td { padding: 14px !important; border-bottom: 1px solid #30363d !important; color: #c9d1d9 !important;}
    .up { color: #f85149; font-weight: bold; } .down { color: #3fb950; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# --- 4. 數據加載與分類 ---
df_hist, cur_stocks, total_capital, df_snap = fetch_cloud_data()
fx = yf.Ticker("TWD=X").fast_info.last_price or 32.3
if pd.isna(fx): fx = 32.3

total_mkt, today_delta, beta_sum = 0.0, 0.0, 0.0
s_v, l_v, c_v = 0.0, 0.0, 0.0
active_data = {}

for sid, v in cur_stocks.items():
    if v['sh'] == 0 and sid != "CASH": continue
    curr, prev, ytd = get_price_metrics(sid)
    
    # 🌟 API 備援機制：如果抓不到現價，改用成本均價避免資產歸零
    if curr == 0.0 and sid != "CASH":
        curr = v.get('avg', 0.0)
        prev = curr
        ytd = curr
        
    m = v['sh'] * curr
    total_mkt += m
    if sid != "CASH": today_delta += (curr - prev) * v['sh']
    
    b = 1.0
    if "L" in sid or "631" in sid: l_v += m; b = 2.0
    elif sid == "CASH" or "865B" in sid: c_v += m; b = 0.0
    else: s_v += m
    
    beta_sum += (b * m)
    active_data[sid] = {"sh": v['sh'], "curr": curr, "m": m, "avg": v.get('avg', 1.0), "ytd": ytd, "beta": b}

curr_beta = (beta_sum / total_mkt) if pd.notna(total_mkt) and total_mkt > 0 else 0.0

# --- 5. 智能自動快照 ---
now_tw = datetime.now(TW_TIMEZONE)
today_str = now_tw.strftime("%Y-%m-%d")

# 寫入前安全檢查
safe_mkt_int = int(total_mkt) if pd.notna(total_mkt) and not math.isnan(total_mkt) else 0

if not df_snap.empty:
    recorded_dates = df_snap['date'].astype(str).tolist()
    if today_str not in recorded_dates and safe_mkt_int > 0:
        client = get_client()
        ws_snap = client.open_by_key(GS_ID).worksheet("DailySnapshots")
        ws_snap.append_row([today_str, safe_mkt_int])
        st.cache_data.clear()

# --- 6. 儀表板 ---
st.markdown(f"### 🛡️ 退休戰情室 V84.0")
st.markdown(f"""
<div class="metric-grid">
    <div class="metric-card"><div class="label-bright">💵 USD/TWD 匯率</div><div class="val-main" style="color:#58a6ff">{fx:.3f}</div></div>
    <div class="metric-card"><div class="label-bright">💰 資產總市值</div><div class="val-main" style="color:#00d4ff">${fmt_int(total_mkt)}</div></div>
    <div class="metric-card"><div class="label-bright">📈 今日損益變動</div><div class="val-main {'up' if today_delta>=0 else 'down'}">${fmt_int(today_delta)}</div><div class="val-sub">基於最新報價差額</div></div>
    <div class="metric-card"><div class="label-bright">📊 真實累積總盈虧</div><div class="val-main {'up' if (total_mkt-total_capital)>=0 else 'down'}">${fmt_int(total_mkt-total_capital)}</div><div class="val-sub">本金: ${fmt_int(total_capital)}</div></div>
</div>
""", unsafe_allow_html=True)

with st.sidebar:
    st.header("🎯 闖關目標設定")
    goal_amt = st.number_input("設定財務自由目標 (NTD)", value=30000000, step=1000000)

st.write("🏆 **財務自由闖關進度**")
m1, m2, m3, m4 = goal_amt * 0.25, goal_amt * 0.50, goal_amt * 0.75, goal_amt
safe_display_mkt = safe_mkt_int if safe_mkt_int > 0 else 0
max_x = max(goal_amt * 1.05, safe_display_mkt * 1.05)

fig_prog = go.Figure()
fig_prog.add_trace(go.Bar(x=[max_x], y=["進度"], orientation='h', marker=dict(color='#21262d'), hoverinfo='skip'))
fig_prog.add_trace(go.Bar(x=[safe_display_mkt], y=["進度"], orientation='h', marker=dict(color='#00d4ff'), text=[f"目前: ${fmt_int(safe_display_mkt)}"], textposition='inside', insidetextanchor='middle', textfont=dict(size=15, color='#ffffff', family='Consolas')))

milestones = [(m1, "Lv1 啟航"), (m2, "Lv2 半山腰"), (m3, "Lv3 衝刺"), (m4, "👑 財務自由")]
for val, name in milestones:
    color = "#3fb950" if safe_display_mkt >= val else "#ff9f1c" 
    fig_prog.add_vline(x=val, line_width=2, line_dash="dash", line_color=color)
    fig_prog.add_annotation(x=val, y=0.5, text=f"{name}<br>{int(val/10000)}萬", showarrow=False, font=dict(color=color, size=13), xanchor="center", yanchor="bottom", yshift=20)

fig_prog.update_layout(barmode='overlay', xaxis=dict(range=[0, max_x], visible=False), yaxis=dict(visible=False), height=130, margin=dict(l=10, r=10, t=55, b=10), paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', showlegend=False)
st.plotly_chart(fig_prog, use_container_width=True)

st.divider()

# --- 7. 配置現況與目標 ---
s_p, l_p = round(s_v/total_mkt*100, 1), round(l_v/total_mkt*100, 1) if pd.notna(total_mkt) and total_mkt>0 else (0,0)
c_p = round(100.0 - s_p - l_p, 1)

c1, c2 = st.columns([1, 1])
with c1: st.write("⚖️ **配置現況**")
with c2: st.markdown(f"<div style='text-align:right; margin-bottom:10px;'><span class='beta-tag'>當前 Portfolio Beta: {curr_beta:.2f}</span></div>", unsafe_allow_html=True)

st.markdown(f"""
<div class="metric-grid" style="grid-template-columns: repeat(3, 1fr);">
    <div class="info-box b-blue"><div class="label-bright">現況 股票</div><div class="box-pct">{s_p}%</div><div style="font-family:'Consolas'; color:#8b949e; font-size:1.1rem;">${fmt_int(s_v)}</div></div>
    <div class="info-box b-purple"><div class="label-bright">現況 槓桿</div><div class="box-pct">{l_p}%</div><div style="font-family:'Consolas'; color:#8b949e; font-size:1.1rem;">${fmt_int(l_v)}</div></div>
    <div class="info-box b-green"><div class="label-bright">現況 類現金</div><div class="box-pct">{c_p}%</div><div style="font-family:'Consolas'; color:#8b949e; font-size:1.1rem;">${fmt_int(c_v)}</div></div>
</div>
""", unsafe_allow_html=True)

t_col1, t_col2, t_col3 = st.columns(3)
with t_col1: ts_pct = st.number_input("股票目標 %", 0, 100, 50, step=5)
with t_col2: tl_pct = st.number_input("槓桿目標 %", 0, 100, 10, step=5)
with t_col3: 
    tc_pct = 100 - ts_pct - tl_pct
    st.info(f"類現金目標: {tc_pct}%")

target_beta = (ts_pct * 1.0 + tl_pct * 2.0) / 100
st.markdown(f"<div style='text-align:right; margin-bottom:15px;'><span class='beta-tag'>預期目標 Beta: {target_beta:.2f}</span></div>", unsafe_allow_html=True)

ts_amt, tl_amt, tc_amt = total_mkt*ts_pct/100, total_mkt*tl_pct/100, total_mkt*tc_pct/100

st.markdown(f"""
<div class="metric-grid" style="grid-template-columns: repeat(3, 1fr);">
    <div class="info-box b-blue" style="background:#1c2128; opacity:0.85;"><div class="label-bright">🎯 目標 股票</div><div class="box-pct">{ts_pct}%</div><div style="font-family:'Consolas'; color:#8b949e; font-size:1.1rem;">${fmt_int(ts_amt)}</div></div>
    <div class="info-box b-purple" style="background:#1c2128; opacity:0.85;"><div class="label-bright">🎯 目標 槓桿</div><div class="box-pct">{tl_pct}%</div><div style="font-family:'Consolas'; color:#8b949e; font-size:1.1rem;">${fmt_int(tl_amt)}</div></div>
    <div class="info-box b-green" style="background:#1c2128; opacity:0.85;"><div class="label-bright">🎯 目標 類現金</div><div class="box-pct">{tc_pct}%</div><div style="font-family:'Consolas'; color:#8b949e; font-size:1.1rem;">${fmt_int(tc_amt)}</div></div>
</div>
""", unsafe_allow_html=True)

st.divider()

# --- 8. 資產明細表 ---
st.write("📋 **資產部位明細與 YTD 績效**")
if active_data:
    html = "<div><table><thead><tr><th>標的</th><th>持股數</th><th>報價</th><th>Beta</th><th>成本均價</th><th>市值</th><th>報酬</th><th>YTD</th><th>佔比</th><th>建議操作</th></tr></thead><tbody>"
    for sid, d in active_data.items():
        if sid == "CASH" and d['sh'] == 0: continue
        pct = (d['m']/total_mkt*100) if pd.notna(total_mkt) and total_mkt!=0 else 0
        roi = f"{((d['curr']-d['avg'])/d['avg']*100):.1f}%" if pd.notna(d['avg']) and d['avg']>0 else "0%"
        ytd_roi = f"{((d['curr']-d['ytd'])/d['ytd']*100):.1f}%" if pd.notna(d['ytd']) and d['ytd']>0 else "0%"
        
        advice = "-"
        if sid == "00662":
            sh = int((ts_amt - s_v) / d['curr']) if pd.notna(ts_amt) and pd.notna(s_v) and pd.notna(d['curr']) and d['curr']>0 else 0
            if abs(sh) > 0: advice = f"<span class='{'up' if sh>0 else 'down'}'>{'加碼' if sh>0 else '減碼'} {abs(sh):,} 股</span>"
        elif "L" in sid or "631" in sid:
            sh = int((tl_amt - l_v) / d['curr']) if pd.notna(tl_amt) and pd.notna(l_v) and pd.notna(d['curr']) and d['curr']>0 else 0
            if abs(sh) > 0: advice = f"<span class='{'up' if sh>0 else 'down'}'>{'加碼' if sh>0 else '減碼'} {abs(sh):,} 股</span>"
        elif sid == "CASH": 
            diff_cash = tc_amt - c_v if pd.notna(tc_amt) and pd.notna(c_v) else 0
            advice = f"調整 ${fmt_int(diff_cash)}"
        
        html += f"<tr><td><b>{sid}</b></td><td>{fmt_int(d['sh'])}</td><td>{d['curr']:.2f}</td><td>{d['beta']:.1f}</td><td>{d['avg']:.2f}</td><td>${fmt_int(d['m'])}</td><td><span class='{'up' if d['curr']>=d['avg'] else 'down'}'>{roi}</span></td><td><span class='{'up' if d['curr']>=d['ytd'] else 'down'}'>{ytd_roi}</span></td><td>{pct:.1f}%</td><td>{advice}</td></tr>"
    html += "</tbody></table></div>"
    st.write(html, unsafe_allow_html=True)

with st.sidebar:
    st.header("📸 數據操作")
    if st.button("強制重置今日快照", use_container_width=True):
        client = get_client()
        ws_snap = client.open_by_key(GS_ID).worksheet("DailySnapshots")
        today_str = datetime.now(TW_TIMEZONE).strftime("%Y-%m-%d")
        # 🌟 再次安全防護
        safe_val = int(total_mkt) if pd.notna(total_mkt) and not math.isnan(total_mkt) else 0
        ws_snap.append_row([today_str, safe_val])
        st.sidebar.success(f"已更新 {today_str} 快照！")
        st.cache_data.clear(); st.rerun()
    st.divider()
    st.header("🖊️ 交易錄入")
    op = st.selectbox("類型", ["買入", "賣出", "入金", "出金"])
    raw_sid = st.text_input("代號", value="00662").upper().strip()
    sid_in = raw_sid.zfill(5) if raw_sid.isdigit() and len(raw_sid) <= 3 else raw_sid
    sh_in = st.number_input("數量/金額", min_value=0.0, step=100.0)
    pr_in = st.number_input("單價", min_value=0.0, value=1.0)
    if st.button("💾 同步至雲端", use_container_width=True):
        client = get_client()
        ws = client.open_by_key(GS_ID).worksheet("Transactions")
        ws.append_row([datetime.now().strftime("%Y-%m-%d"), op, sid_in, sh_in, pr_in, ""])
        st.cache_data.clear(); st.rerun()
