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
st.set_page_config(page_title="退休戰情室 V84.1", layout="wide")
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

# 🌟 防呆格式化函數
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
                
                curr = float(curr) if pd.notna(curr) else 0.0
                prev = float(prev) if pd.notna(prev) else curr
                ytd_open = float(ytd_open) if pd.notna(ytd_open) else curr
                if curr > 0: return curr, prev, ytd_open
        except: continue
    return 0.0, 0.0, 0.0

# --- 3. 視覺樣式 (極致緊湊一行版) ---
st.markdown("""
<style>
    .stApp { background-color: #0d1117; color: #c9d1d9; }
    
    /* 🌟 強制 4 格一列 */
    .metric-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin-bottom: 12px; }
    @media (max-width: 1000px) { .metric-grid { grid-template-columns: repeat(2, 1fr); } }
    
    /* 卡片高度壓縮 */
    .metric-card { background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 12px 10px; text-align: center; }
    .label-bright { color: #8b949e; font-size: 0.95rem; font-weight: bold; margin-bottom: 4px; }
    .val-main { font-size: 1.8rem; font-weight: bold; color: #ffffff; font-family: 'Consolas', monospace; margin-bottom: 2px; line-height: 1.1; }
    .val-sub { font-size: 0.85rem; color: #8b949e; }
    
    .responsive-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin-bottom: 12px; }
    .info-box { background: #161b22; border-radius: 8px; padding: 12px 10px; text-align: center; border: 1px solid #30363d; }
    .box-pct { font-size: 1.7rem; font-weight: bold; color: #ffffff; margin: 6px 0; line-height: 1.1; }
    
    .b-blue { border-top: 4px solid #58a6ff; }
    .b-purple { border-top: 4px solid #bc8cff; }
    .b-green { border-top: 4px solid #3fb950; }
    
    .beta-tag { background: #21262d; color: #ff9f1c; padding: 2px 8px; border-radius: 4px; font-size: 0.85rem; font-family: 'Consolas'; border: 1px solid #ff9f1c; }
    
    /* 表格壓縮 */
    table { width: 100%; border-collapse: collapse; font-size: 1.1rem !important; }
    th { background: #21262d !important; color: #8b949e !important; padding: 8px 10px !important; text-align: left !important; }
    td { padding: 8px 10px !important; border-bottom: 1px solid #30363d !important; color: #c9d1d9 !important;}
    
    .up { color: #f85149; font-weight: bold; } 
    .down { color: #3fb950; font-weight: bold; }
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
    
    if curr == 0.0 and sid != "CASH":
        curr = v.get('avg', 0.0)
        prev = curr; ytd = curr
        
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

# --- 5. 智能自動快照與昨日紀錄 ---
now_tw = datetime.now(TW_TIMEZONE)
today_str = now_tw.strftime("%Y-%m-%d")

safe_mkt_int = int(total_mkt) if pd.notna(total_mkt) and not math.isnan(total_mkt) else 0

if not df_snap.empty:
    recorded_dates = df_snap['date'].astype(str).tolist()
    if today_str not in recorded_dates and safe_mkt_int > 0:
        client = get_client()
        ws_snap = client.open_by_key(GS_ID).worksheet("DailySnapshots")
        ws_snap.append_row([today_str, safe_mkt_int])
        st.cache_data.clear()

# 🌟 抓取昨日紀錄
yesterday_mkt = 0.0
if not df_snap.empty:
    valid_snaps = df_snap[df_snap['date'].astype(str) != today_str]
    if not valid_snaps.empty:
        yesterday_mkt = float(valid_snaps.iloc[-1]['total_mkt'])

# --- 6. 儀表板 (四格一列) ---
st.markdown(f"#### 🛡️ 退休戰情室 V84.1")
st.markdown(f"""
<div class="metric-grid">
    <div class="metric-card"><div class="label-bright">💵 USD/TWD</div><div class="val-main" style="color:#58a6ff">{fx:.3f}</div></div>
    <div class="metric-card"><div class="label-bright">💰 總資產市值</div><div class="val-main" style="color:#00d4ff">${fmt_int(total_mkt)}</div><div class="val-sub">昨日紀錄: ${fmt_int(yesterday_mkt)}</div></div>
    <div class="metric-card"><div class="label-bright">📈 今日損益變動</div><div class="val-main {'up' if today_delta>=0 else 'down'}">${fmt_int(today_delta)}</div><div class="val-sub">基於最新報價差額</div></div>
    <div class="metric-card"><div class="label-bright">📊 累積總盈虧</div><div class="val-main {'up' if (total_mkt-total_capital)>=0 else 'down'}">${fmt_int(total_mkt-total_capital)}</div><div class="val-sub">本金: ${fmt_int(total_capital)}</div></div>
</div>
""", unsafe_allow_html=True)

# --- 7. 🏆 闖關進度圖 ---
with st.sidebar:
    st.header("🎯 闖關目標設定")
    goal_amt = st.number_input("設定財務自由目標 (NTD)", value=30000000, step=1000000)

st.write("🏆 **財務自由闖關進度**")
m1, m2, m3, m4 = goal_amt * 0.25, goal_amt * 0.50, goal_amt * 0.75, goal_amt
safe_display_mkt = safe_mkt_int if safe_mkt_int > 0 else 0
max_x = max(goal_amt * 1.05, safe_display_mkt * 1.05)

fig_prog = go.Figure()
fig_prog.add_trace(go.Bar(x=[max_x], y=["進度"], orientation='h', marker=dict(color='#21262d'), hoverinfo='skip'))
fig_prog.add_trace(go.Bar(x=[safe_display_mkt], y=["進度"], orientation='h', marker=dict(color='#00d4ff'), text=[f"目前: ${fmt_int(safe_display_mkt)}"], textposition='inside', insidetextanchor='middle', textfont=dict(size=14, color='#ffffff', family='Consolas')))

milestones = [(m1, "Lv1 啟航"), (m2, "Lv2 半山腰"), (m3, "Lv3 衝刺"), (m4, "👑 財務自由")]
for val, name in milestones:
    color = "#3fb950" if safe_display_mkt >= val else "#ff9f1c" 
    fig_prog.add_vline(x=val, line_width=2, line_dash="dash", line_color=color)
    fig_prog.add_annotation(x=val, y=0.5, text=f"{name}<br>{int(val/10000)}萬", showarrow=False, font=dict(color=color, size=11), xanchor="center", yanchor="bottom", yshift=15)

fig_prog.update_layout(barmode='overlay', xaxis=dict(range=[0, max_x], visible=False), yaxis=dict(visible=False), height=90, margin=dict(l=10, r=10, t=35, b=5), paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', showlegend=False)
st.plotly_chart(fig_prog, use_container_width=True)

# --- 8. 配置現
