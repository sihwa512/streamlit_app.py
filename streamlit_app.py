import streamlit as st
import pandas as pd
import yfinance as yf
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import plotly.graph_objects as go
import re

# --- 1. 核心連線設定 ---
st.set_page_config(page_title="退休戰情室 V80.0", layout="wide")
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
        df_t = pd.DataFrame(doc.worksheet("Transactions").get_all_records())
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
    .b-purple { border-top: 5px solid #bc8cff; color: #bc8cff; }
    .b-green { border-top: 5px solid #3fb950; color: #3fb950; }
    
    .beta-tag { background: #30363d; color: #ff9f1c; padding: 2px 8px; border-radius: 4px; font-size: 0.85rem; font-family: 'Consolas', monospace; border: 1px solid #444c56; }
    
    table { width: 100%; border-collapse: collapse; font-size: 1.15rem !important; }
    th { background: #1c2128 !important; color: #ffffff !important; padding: 8px !important; }
    td { padding: 8px !important; border-bottom: 1px solid #30363d !important; }
    .up { color: #ff3e3e; font-weight: bold; } .down { color: #3fb950; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# --- 4. 數據加載與運算 ---
df_hist, cur_stocks, total_capital, df_snap = fetch_cloud_data()
fx = yf.Ticker("TWD=X").fast_info.last_price or 32.3

total_mkt, today_delta, beta_sum = 0.0, 0.0, 0.0
s_v, l_v, c_v = 0.0, 0.0, 0.0
active_data = {}

for sid, v in cur_stocks.items():
    if v['sh'] == 0 and sid != "CASH": continue
    curr, prev, ytd = get_price_metrics(sid)
    m = v['sh'] * curr
    total_mkt += m
    
    b = 1.0
    if "L" in sid or "631" in sid: l_v += m; b = 2.0
    elif sid == "CASH" or "865B" in sid: c_v += m; b = 0.0
    else: s_v += m
    
    beta_sum += (b * m)
    active_data[sid] = {"sh": v['sh'], "curr": curr, "m": m, "avg": v.get('avg', 1.0), "ytd": ytd, "beta": b}

curr_beta = (beta_sum / total_mkt) if total_mkt > 0 else 0.0

# 昨日市值快照對比
yesterday_mkt = 0.0
if not df_snap.empty:
    valid_snaps = df_snap[df_snap['date'] != datetime.now().strftime("%Y-%m-%d")]
    if not valid_snaps.empty: yesterday_mkt = float(valid_snaps.iloc[-1]['total_mkt'])

snap_delta = total_mkt - yesterday_mkt if yesterday_mkt > 0 else 0.0

# --- 5. 儀表板 ---
st.markdown(f"#### 🛡️ 退休戰情室 V80.0")
st.markdown(f"""
<div class="metric-grid">
    <div class="metric-card"><div class="label-bright">💵 USD/TWD</div><div class="val-main" style="color:#58a6ff">{fx:.3f}</div></div>
    <div class="metric-card"><div class="label-bright">💰 總市值</div><div class="val-main" style="color:#00d4ff">${int(total_mkt):,}</div><div class="val-sub">昨日: ${int(yesterday_mkt):,}</div></div>
    <div class="metric-card"><div class="label-bright">📈 今日損益 (快照)</div><div class="val-main {'up' if snap_delta>=0 else 'down'}">${int(snap_delta):,}</div><div class="val-sub">對比上一次快照</div></div>
    <div class="metric-card"><div class="label-bright">📊 累計總損益</div><div class="val-main {'up' if (total_mkt-total_capital)>=0 else 'down'}">${int(total_mkt-total_capital):,}</div><div style="color:#ffffff; font-size:0.8rem;">本金: ${int(total_capital):,}</div></div>
</div>
""", unsafe_allow_html=True)

# --- 6. 🏆 總市值闖關進度圖 ---
with st.sidebar:
    st.header("🎯 終極目標設定")
    goal_amt = st.number_input("設定財務自由目標 (NTD)", value=30000000, step=1000000)

st.write("🏆 **財務自由闖關進度**")
m1, m2, m3, m4 = goal_amt * 0.25, goal_amt * 0.50, goal_amt * 0.75, goal_amt
max_x = max(goal_amt * 1.05, total_mkt * 1.05) # 圖表動態邊界

fig_prog = go.Figure()
# 背景底色條 (尚未達成的部分)
fig_prog.add_trace(go.Bar(
    x=[max_x], y=["進度"], orientation='h', 
    marker=dict(color='#1c2128', line=dict(width=1, color='#30363d')), hoverinfo='skip'
))
# 實際進度條
fig_prog.add_trace(go.Bar(
    x=[total_mkt], y=["進度"], orientation='h', 
    marker=dict(color='#00d4ff', line=dict(width=2, color='#58a6ff')), 
    text=[f"目前總市值: ${int(total_mkt):,}"], 
    textposition='inside', insidetextanchor='middle', textfont=dict(size=16, color='white', family='Consolas')
))

# 加入關卡線與標籤
milestones = [(m1, "Lv1 啟航"), (m2, "Lv2 半山腰"), (m3, "Lv3 衝刺"), (m4, "👑 財務自由")]
for val, name in milestones:
    # 達成關卡變綠色，未達成橘色
    color = "#3fb950" if total_mkt >= val else "#ff9f1c" 
    fig_prog.add_vline(x=val, line_width=2, line_dash="dash", line_color=color)
    fig_prog.add_annotation(
        x=val, y=0.5, text=f"{name}<br>{int(val/10000)}萬", 
        showarrow=False, font=dict(color=color, size=13, family='Consolas'), 
        xanchor="center", yanchor="bottom", yshift=18
    )

fig_prog.update_layout(
    barmode='overlay', xaxis=dict(range=[0, max_x], visible=False), yaxis=dict(visible=False),
    height=100, margin=dict(l=10, r=10, t=45, b=10), paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', showlegend=False
)
st.plotly_chart(fig_prog, use_container_width=True)

st.divider()

# --- 7. 配置現況與目標 ---
s_p, l_p = round(s_v/total_mkt*100, 1), round(l_v/total_mkt*100, 1) if total_mkt>0 else (0,0)
c_p = round(100.0 - s_p - l_p, 1)

c1, c2 = st.columns([1, 1])
with c1: st.write("⚖️ **配置現況與 Beta 導航**")
with c2: st.markdown(f"<div style='text-align:right;'><span class='beta-tag'>當前 Portfolio Beta: {curr_beta:.2f}</span></div>", unsafe_allow_html=True)

st.markdown(f"""
<div class="metric-grid" style="grid-template-columns: repeat(3, 1fr);">
    <div class="info-box b-blue"><div class="label-bright">現況 股票</div><div class="box-pct">{s_p}%</div><div>${int(s_v):,}</div></div>
    <div class="info-box b-purple"><div class="label-bright">現況 槓桿</div><div class="box-pct">{l_p}%</div><div>${int(l_v):,}</div></div>
    <div class="info-box b-green"><div class="label-bright">現況 類現金</div><div class="box-pct">{c_p}%</div><div>${int(c_v):,}</div></div>
</div>
""", unsafe_allow_html=True)

t_col1, t_col2, t_col3 = st.columns(3)
with t_col1: ts_pct = st.number_input("股票目標 %", 0, 100, 50, step=5)
with t_col2: tl_pct = st.number_input("槓桿目標 %", 0, 100, 10, step=5)
with t_col3: 
    tc_pct = 100 - ts_pct - tl_pct
    target_beta = (ts_pct * 1.0 + tl_pct * 2.0) / 100
    st.markdown(f"<div style='margin-top:25px; text-align:right;'><span class='beta-tag' style='border:1px solid #ff9f1c'>預期目標 Beta: {target_beta:.2f}</span></div>", unsafe_allow_html=True)

ts_amt, tl_amt, tc_amt = total_mkt*ts_pct/100, total_mkt*tl_pct/100, total_mkt*tc_pct/100

st.markdown(f"""
<div class="metric-grid" style="grid-template-columns: repeat(3, 1fr);">
    <div class="info-box b-blue" style="background:#1c2128; opacity:0.8;"><div class="label-bright">🎯 目標 股票</div><div class="box-pct">{ts_pct}%</div><div>${int(ts_amt):,}</div></div>
    <div class="info-box b-purple" style="background:#1c2128; opacity:0.8;"><div class="label-bright">🎯 目標 槓桿</div><div class="box-pct">{tl_pct}%</div><div>${int(tl_amt):,}</div></div>
    <div class="info-box b-green" style="background:#1c2128; opacity:0.8;"><div class="label-bright">🎯 目標 類現金</div><div class="box-pct">{tc_pct}%</div><div>${int(tc_amt):,}</div></div>
</div>
""", unsafe_allow_html=True)

# --- 8. 資產明細表 ---
st.write("📋 **資產部位明細**")
if active_data:
    html = "<div><table><thead><tr><th>標的</th><th>持股數</th><th>報價</th><th>Beta</th><th>成本均價</th><th>市值</th><th>報酬</th><th>YTD</th><th>佔比</th><th>建議操作</th></tr></thead><tbody>"
    for sid, d in active_data.items():
        if sid == "CASH" and d['sh'] == 0: continue
        pct = (d['m']/total_mkt*100) if total_mkt!=0 else 0
        roi = f"{((d['curr']-d['avg'])/d['avg']*100):.1f}%" if d['avg']>0 else "0%"
        ytd_roi = f"{((d['curr']-d['ytd'])/d['ytd']*100):.1f}%" if d['ytd']>0 else "0%"
        advice = "-"
        if sid == "00662":
            sh = int((ts_amt - s_v) / d['curr'])
            if abs(sh) > 0: advice = f"<span class='{'up' if sh>0 else 'down'}'>{'加碼' if sh>0 else '減碼'} {abs(sh):,} 股</span>"
        elif "L" in sid or "631" in sid:
            sh = int((tl_amt - l_v) / d['curr'])
            if abs(sh) > 0: advice = f"<span class='{'up' if sh>0 else 'down'}'>{'加碼' if sh>0 else '減碼'} {abs(sh):,} 股</span>"
        elif sid == "CASH": advice = f"調整 ${int(tc_amt - c_v):,}"
        html += f"<tr><td><b>{sid}</b></td><td>{int(d['sh']):,}</td><td>{d['curr']:.2f}</td><td>{d['beta']:.1f}</td><td>{d['avg']:.2f}</td><td>${int(d['m']):,}</td><td>{roi}</td><td>{ytd_roi}</td><td>{pct:.1f}%</td><td>{advice}</td></tr>"
    html += "</tbody></table></div>"
    st.write(html, unsafe_allow_html=True)

with st.sidebar:
    st.header("📸 數據快照")
    if st.button("紀錄今日市值快照", use_container_width=True):
        client = get_client()
        ws_snap = client.open_by_key(GS_ID).worksheet("DailySnapshots")
        today_str = datetime.now().strftime("%Y-%m-%d")
        ws_snap.append_row([today_str, int(total_mkt)])
        st.sidebar.success(f"成功紀錄 {today_str}！")
        st.cache_data.clear(); st.rerun()
    st.divider()
    st.header("🖊️ 交易錄入")
    op = st.selectbox("類型", ["買入", "賣出", "入金", "出金"])
    raw_sid = st.text_input("代號", value="00662").upper().strip()
    sid_in = raw_sid.zfill(5) if raw_sid.isdigit() and len(raw_sid) <= 3 else raw_sid
    sh_in = st.number_input("數量/金額", min_value=0.0, step=100.0)
    pr_in = st.number_input("單價", min_value=0.0, value=1.0)
    if st.button("💾 同步交易", use_container_width=True):
        client = get_client()
        ws = client.open_by_key(GS_ID).worksheet("Transactions")
        ws.append_row([datetime.now().strftime("%Y-%m-%d"), op, sid_in, sh_in, pr_in, ""])
        st.cache_data.clear(); st.rerun()
