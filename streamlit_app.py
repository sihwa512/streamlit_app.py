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
import requests

# --- 1. 核心連線設定 ---
st.set_page_config(page_title="退休戰情室 V88.3", layout="wide")
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

def fmt_int(val):
    if pd.isna(val) or math.isnan(val): return "0"
    try: return f"{int(float(val)):,}"
    except: return "0"

# --- 2. 數據引擎 ---
@st.cache_data(ttl=60)
def fetch_cloud_data():
    client = get_client()
    if not client: return pd.DataFrame(), {}, 0.0, pd.DataFrame(), {}
    try:
        doc = client.open_by_key(GS_ID)
        df_t = pd.DataFrame(doc.worksheet("Transactions").get_all_records())
        try: df_snap = pd.DataFrame(doc.worksheet("DailySnapshots").get_all_records())
        except:
            ws_snap = doc.add_worksheet(title="DailySnapshots", rows="1000", cols="5")
            ws_snap.append_row(["date", "total_mkt"])
            df_snap = pd.DataFrame(columns=["date", "total_mkt"])
            
        try: df_settings = pd.DataFrame(doc.worksheet("Settings").get_all_records())
        except:
            ws_settings = doc.add_worksheet(title="Settings", rows="10", cols="2")
            ws_settings.append_row(["key", "value"])
            default_settings = [
                {"key": "target_stock", "value": 40}, {"key": "target_leverage", "value": 30},
                {"key": "goal_amt", "value": 30000000}, {"key": "deviation_band", "value": 5.0},
                {"key": "borrowed_amt", "value": 0}, {"key": "expected_yield", "value": 5.0}, 
                {"key": "line_channel_token", "value": ""}, {"key": "line_user_id", "value": ""}
            ]
            for s in default_settings: ws_settings.append_row([s["key"], s["value"]])
            df_settings = pd.DataFrame(default_settings)
            
        settings_dict = dict(zip(df_settings['key'], df_settings['value']))
            
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
                    stocks[sid]["sh"] += r['sh']; stocks[sid]["cost"] += (r['sh'] * r['pr']); running_cash -= (r['sh'] * r['pr'])
                elif r['type'] == "賣出":
                    if sid in stocks and stocks[sid]["sh"] > 0:
                        stocks[sid]["cost"] -= (stocks[sid]["cost"] * (r['sh']/stocks[sid]["sh"]))
                        stocks[sid]["sh"] -= r['sh']; running_cash += (r['sh'] * r['pr'])
            stocks["CASH"] = {"sh": running_cash, "cost": running_cash, "avg": 1.0}
        for s in stocks:
            if s != "CASH": stocks[s]["avg"] = stocks[s]["cost"]/stocks[s]["sh"] if stocks[s]["sh"] > 0 else 0
        return df_t, stocks, total_cap, df_snap, settings_dict
    except: return pd.DataFrame(), {}, 0.0, pd.DataFrame(), {}

@st.cache_data(ttl=300)
def get_price_metrics(sid):
    if sid == "CASH": return 1.0, 1.0, 1.0
    for tsid in [f"{sid}.TW", f"{sid}.TWO", sid]:
        try:
            t = yf.Ticker(tsid)
            try: curr = float(t.fast_info.last_price)
            except: curr = 0.0
            hist = t.history(period="1mo").dropna(subset=['Close'])
            if not hist.empty:
                if pd.isna(curr) or curr == 0.0: curr = float(hist['Close'].iloc[-1])
                prev = float(hist['Close'].iloc[-2]) if len(hist) > 1 else curr
                ytd_hist = t.history(start=f"{datetime.now().year}-01-01").dropna(subset=['Close'])
                ytd_open = float(ytd_hist['Close'].iloc[0]) if not ytd_hist.empty else curr
                if curr > 0: return curr, prev, ytd_open
        except: continue
    return 0.0, 0.0, 0.0

@st.cache_data(ttl=3600)
def get_benchmark_data(start_date):
    try:
        t = yf.Ticker("0050.TW")
        hist = t.history(start=start_date)
        if not hist.empty and 'Close' in hist.columns:
            df = hist[['Close']].copy().reset_index()
            df.columns = ['Date', 'Close'] 
            df['Date'] = pd.to_datetime(df['Date']).dt.strftime('%Y-%m-%d')
            return df
    except: pass
    return pd.DataFrame()

# --- 3. 視覺樣式 ---
st.markdown("""
<style>
    .stApp { background-color: #0d1117; color: #c9d1d9; }
    .metric-grid { display: grid; grid-template-columns: repeat(6, 1fr); gap: 10px; margin-bottom: 12px; }
    @media (max-width: 1400px) { .metric-grid { grid-template-columns: repeat(3, 1fr); } }
    @media (max-width: 800px) { .metric-grid { grid-template-columns: repeat(2, 1fr); } }
    .metric-card { background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 12px 10px; text-align: center; }
    .label-bright { color: #8b949e; font-size: 0.9rem; font-weight: bold; margin-bottom: 4px; white-space: nowrap;}
    .val-main { font-size: 1.6rem; font-weight: bold; color: #ffffff; font-family: 'Consolas', monospace; margin-bottom: 2px; line-height: 1.1; }
    .val-sub { font-size: 0.8rem; color: #8b949e; white-space: nowrap;}
    .responsive-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin-bottom: 12px; }
    .info-box { background: #161b22; border-radius: 8px; padding: 12px 10px; text-align: center; border: 1px solid #30363d; }
    .box-pct { font-size: 1.7rem; font-weight: bold; color: #ffffff; margin: 6px 0; line-height: 1.1; }
    .b-blue { border-top: 4px solid #58a6ff; } .b-purple { border-top: 4px solid #bc8cff; } .b-green { border-top: 4px solid #3fb950; }
    .beta-tag { background: #21262d; color: #ff9f1c; padding: 4px 10px; border-radius: 4px; font-size: 0.95rem; font-family: 'Consolas'; border: 1px solid #ff9f1c; white-space: nowrap; }
    .alert-tag { background: #4a0000; color: #ff7b72; padding: 2px 6px; border-radius: 4px; font-size: 0.85rem; font-weight: bold; border: 1px solid #ff7b72; margin-left: 5px;}
    table { width: 100%; border-collapse: collapse; font-size: 1.05rem !important; }
    th { background: #21262d !important; color: #8b949e !important; padding: 8px 10px !important; text-align: left !important; }
    td { padding: 8px 10px !important; border-bottom: 1px solid #30363d !important; color: #c9d1d9 !important;}
    .up { color: #f85149; font-weight: bold; } .down { color: #3fb950; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# --- 4. 數據加載與設定提取 ---
df_hist, cur_stocks, total_capital, df_snap, settings_dict = fetch_cloud_data()
fx = yf.Ticker("TWD=X").fast_info.last_price or 32.3
if pd.isna(fx): fx = 32.3

default_ts = int(settings_dict.get("target_stock", 40)) if settings_dict else 40
default_tl = int(settings_dict.get("target_leverage", 30)) if settings_dict else 30
default_goal = int(settings_dict.get("goal_amt", 30000000)) if settings_dict else 30000000
default_dev = float(settings_dict.get("deviation_band", 5.0)) if settings_dict else 5.0
default_borrowed = float(settings_dict.get("borrowed_amt", 0.0)) if settings_dict else 0.0
default_yield = float(settings_dict.get("expected_yield", 5.0)) if settings_dict else 5.0
line_channel_token = str(settings_dict.get("line_channel_token", "")) if settings_dict else ""
line_user_id = str(settings_dict.get("line_user_id", "")) if settings_dict else ""

total_mkt, beta_sum, s_v, l_v, c_v = 0.0, 0.0, 0.0, 0.0, 0.0
active_data = {}

for sid, v in cur_stocks.items():
    if v['sh'] == 0 and sid != "CASH": continue
    curr, prev, ytd = get_price_metrics(sid)
    if curr == 0.0 and sid != "CASH": curr = v.get('avg', 0.0); prev = curr; ytd = curr
    m = v['sh'] * curr
    total_mkt += m
    b = 1.0
    if "L" in sid or "631" in sid: l_v += m; b = 2.0
    elif sid == "CASH" or "865B" in sid: c_v += m; b = 0.0
    else: s_v += m
    beta_sum += (b * m)
    active_data[sid] = {"sh": v['sh'], "curr": curr, "m": m, "avg": v.get('avg', 1.0), "ytd": ytd, "beta": b}

curr_beta = (beta_sum / total_mkt) if pd.notna(total_mkt) and total_mkt > 0 else 0.0

# --- 5. 自動結算與 MDD 計算 ---
now_tw = datetime.now(TW_TIMEZONE)
today_str = now_tw.strftime("%Y-%m-%d")
safe_mkt_int = int(total_mkt) if pd.notna(total_mkt) and not math.isnan(total_mkt) else 0
yesterday_mkt, historical_high = 0.0, safe_mkt_int

if not df_snap.empty:
    recorded_dates = df_snap['date'].astype(str).tolist()
    df_snap['total_mkt'] = pd.to_numeric(df_snap['total_mkt'], errors='coerce').fillna(0)
    historical_high = max(df_snap['total_mkt'].max(), safe_mkt_int)
    
    valid_snaps = df_snap[df_snap['date'].astype(str) != today_str]
    if not valid_snaps.empty: yesterday_mkt = float(valid_snaps.iloc[-1]['total_mkt'])

    if safe_mkt_int > 0:
        client = get_client()
        if client:
            ws_snap = client.open_by_key(GS_ID).worksheet("DailySnapshots")
            if today_str not in recorded_dates:
                ws_snap.append_row([today_str, safe_mkt_int])
                st.cache_data.clear()
            else:
                row_idx = recorded_dates.index(today_str)
                if int(df_snap.iloc[row_idx]['total_mkt']) != safe_mkt_int:
                    ws_snap.update_cell(row_idx + 2, 2, safe_mkt_int)
                    st.cache_data.clear()
else:
    if safe_mkt_int > 0:
        client = get_client()
        if client:
            client.open_by_key(GS_ID).worksheet("DailySnapshots").append_row([today_str, safe_mkt_int])
            st.cache_data.clear()

today_delta = total_mkt - yesterday_mkt if yesterday_mkt > 0 else 0.0
drawdown_pct = ((total_mkt - historical_high) / historical_high * 100) if historical_high > 0 else 0.0

margin_ratio = (total_mkt / default_borrowed * 100) if default_borrowed > 0 else float('inf')
margin_color = "#ff7b72" if margin_ratio < 160 else "#3fb950"
margin_display = f"{margin_ratio:.0f}%" if margin_ratio != float('inf') else "無借款"

monthly_cf = (total_mkt * (default_yield / 100)) / 12

# --- 6. 儀表板 ---
st.markdown(f"#### 🛡️ 退休戰情室 V88.3 (全版圖歸位版)")
st.markdown(f"""
<div class="metric-grid">
    <div class="metric-card"><div class="label-bright">💵 USD/TWD</div><div class="val-main" style="color:#58a6ff">{fx:.3f}</div><div class="val-sub">匯率參考</div></div>
    <div class="metric-card"><div class="label-bright">💰 總資產市值</div><div class="val-main" style="color:#2f81f7">${fmt_int(total_mkt)}</div><div class="val-sub">昨日紀錄: ${fmt_int(yesterday_mkt)}</div></div>
    <div class="metric-card"><div class="label-bright">📈 今日損益</div><div class="val-main {'up' if today_delta>=0 else 'down'}">${fmt_int(today_delta)}</div><div class="val-sub">與昨日對比</div></div>
    <div class="metric-card"><div class="label-bright">📉 距前高跌幅 (MDD)</div><div class="val-main" style="color:{'#ff7b72' if drawdown_pct < -5 else '#c9d1d9'}">{drawdown_pct:.1f}%</div><div class="val-sub">前高: ${fmt_int(historical_high)}</div></div>
    <div class="metric-card"><div class="label-bright">🏦 擔保維持率</div><div class="val-main" style="color:{margin_color}">{margin_display}</div><div class="val-sub">借款: ${fmt_int(default_borrowed)}</div></div>
    <div class="metric-card"><div class="label-bright">💧 預估月現金流</div><div class="val-main" style="color:#ab7df8">${fmt_int(monthly_cf)}</div><div class="val-sub">年化殖利率: {default_yield}%</div></div>
</div>
""", unsafe_allow_html=True)

# --- 7. 🏆 闖關圖與 ⚔️ 大盤對比 ---
with st.sidebar:
    st.header("🎯 戰略目標設定")
    goal_amt = st.number_input("財務自由目標", value=default_goal, step=1000000)
    deviation_band = st.number_input("再平衡容許誤差 ±%", value=default_dev, step=1.0)
    st.divider()
    st.header("🏦 被動收入與質押參數")
    borrowed_input = st.number_input("目前借款/質押餘額", value=default_borrowed, step=100000.0)
    yield_input = st.number_input("預期組合年化殖利率 %", value=default_yield, step=0.5)

st.write("🏆 **財務自由闖關進度**")

m1, m2, m3, m4 = goal_amt * 0.25, goal_amt * 0.50, goal_amt * 0.75, goal_amt
safe_display_mkt = safe_mkt_int if safe_mkt_int > 0 else 0
max_x = max(goal_amt * 1.05, safe_display_mkt * 1.05)

fig_prog = go.Figure()
fig_prog.add_trace(go.Bar(x=[max_x], y=[" "], orientation='h', marker=dict(color='#1c2128', line=dict(width=1, color='#30363d')), hoverinfo='skip'))
fig_prog.add_trace(go.Bar(x=[safe_display_mkt], y=[" "], orientation='h', marker=dict(color='#2f81f7'), text=[f"目前: ${fmt_int(safe_display_mkt)}"], textposition='inside', insidetextanchor='middle', textfont=dict(size=18, color='#ffffff', family='Consolas')))
for val, name in [(m1, "Lv1 啟航"), (m2, "Lv2 半山腰"), (m3, "Lv3 衝刺"), (m4, "👑 財務自由")]:
    color = "#3fb950" if safe_display_mkt >= val else "#8b949e" 
    fig_prog.add_vline(x=val, line_width=2, line_dash="dash", line_color=color)
    fig_prog.add_annotation(x=val, y=1, yref="paper", text=f"{name}<br>{int(val/10000)}萬", showarrow=False, font=dict(color=color, size=12), xanchor="center", yanchor="bottom", yshift=5)
fig_prog.update_layout(barmode='overlay', xaxis=dict(range=[0, max_x], visible=False), yaxis=dict(visible=False), height=150, margin=dict(l=15, r=15, t=60, b=10), paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', showlegend=False)
st.plotly_chart(fig_prog, use_container_width=True)

with st.expander("📊 展開歷史走勢與大盤對比 (Benchmark Alpha)"):
    if not df_snap.empty and len(df_snap) > 1:
        df_snap_sorted = df_snap.sort_values(by="date")
        start_date = df_snap_sorted['date'].iloc[0]
        
        df_snap_sorted['norm_mkt'] = (pd.to_numeric(df_snap_sorted['total_mkt']) / pd.to_numeric(df_snap_sorted['total_mkt']).iloc[0]) * 100
        
        fig_curve = go.Figure()
        fig_curve.add_trace(go.Scatter(x=df_snap_sorted['date'], y=df_snap_sorted['norm_mkt'], name="我的戰情室組合", mode='lines+markers', line=dict(color='#2f81f7', width=3)))
        
        bm_df = get_benchmark_data(start_date)
        if not bm_df.empty:
            bm_df_filtered = bm_df[bm_df['Date'].isin(df_snap_sorted['date'].tolist())].copy()
            if not bm_df_filtered.empty:
                first_bm_price = float(bm_df_filtered.iloc[0]['Close'])
                if first_bm_price > 0:
                    bm_df_filtered['norm_bm'] = (bm_df_filtered['Close'] / first_bm_price) * 100
                    fig_curve.add_trace(go.Scatter(x=bm_df_filtered['Date'], y=bm_df_filtered['norm_bm'], name="基準大盤 (0050.TW)", mode='lines', line=dict(color='#8b949e', width=2, dash='dot')))

        fig_curve.update_layout(title="正規化績效對比 (Base=100)", height=350, margin=dict(l=10, r=10, t=40, b=10), paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', xaxis=dict(showgrid=False, color='#8b949e'), yaxis=dict(showgrid=True, gridcolor='#30363d', color='#8b949e'), legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
        st.plotly_chart(fig_curve, use_container_width=True)
    else:
        st.info("快照資料累積中，明天就會看到您與大盤的對決囉！")

st.divider()

# --- 8. 配置現況、設定儲存 ---
s_p, l_p = round(s_v/total_mkt*100, 1), round(l_v/total_mkt*100, 1) if pd.notna(total_mkt) and total_mkt>0 else (0,0)
c_p = round(100.0 - s_p - l_p, 1)

c1, c2 = st.columns([1, 1])
with c1: st.write("⚖️ **資產配置與再平衡警示**")
with c2: 
    st.markdown(f"""
    <div style='display:flex; justify-content:flex-end; margin-bottom:5px;'>
        <div class='beta-tag'>當前 Portfolio Beta: {curr_beta:.2f}</div>
    </div>
    """, unsafe_allow_html=True)

st.markdown(f"""
<div class="responsive-grid">
    <div class="info-box b-blue"><div class="label-bright">現況 股票</div><div class="box-pct">{s_p}%</div><div style="font-family:'Consolas'; color:#8b949e; font-size:1.05rem;">${fmt_int(s_v)}</div></div>
    <div class="info-box b-purple"><div class="label-bright">現況 槓桿</div><div class="box-pct">{l_p}%</div><div style="font-family:'Consolas'; color:#8b949e; font-size:1.05rem;">${fmt_int(l_v)}</div></div>
    <div class="info-box b-green"><div class="label-bright">現況 類現金</div><div class="box-pct">{c_p}%</div><div style="font-family:'Consolas'; color:#8b949e; font-size:1.05rem;">${fmt_int(c_v)}</div></div>
</div>
""", unsafe_allow_html=True)

t_col1, t_col2, t_col3, t_col4 = st.columns([2, 2, 4, 2])
with t_col1: ts_pct = st.number_input("🎯 股票目標 %", 0, 100, default_ts, step=5)
with t_col2: tl_pct = st.number_input("🎯 槓桿目標 %", 0, 100, default_tl, step=5)
with t_col3: 
    tc_pct = 100 - ts_pct - tl_pct
    target_beta = (ts_pct * 1.0 + tl_pct * 2.0) / 100
    st.markdown(f"""
    <div style="display:flex; flex-wrap:wrap; justify-content:center; align-items:center; gap:15px; background:#161b22; padding:12px 15px; border-radius:8px; border:1px solid #30363d; margin-top:28px; min-height:45px;">
        <div style="color:#8b949e; font-weight:bold; font-size:1.05rem; white-space:nowrap;">類現金: {tc_pct}%</div>
        <div class='beta-tag' style="margin:0;">🎯 目標 Beta: {target_beta:.2f}</div>
    </div>
    """, unsafe_allow_html=True)

with t_col4:
    st.markdown("<div style='margin-top:28px;'></div>", unsafe_allow_html=True)
    if st.button("💾 永久保存設定", use_container_width=True):
        client = get_client()
        if client:
            try:
                ws_settings = client.open_by_key(GS_ID).worksheet("Settings")
                ws_settings.clear()
                ws_settings.append_rows([
                    ["key", "value"],
                    ["target_stock", ts_pct], ["target_leverage", tl_pct],
                    ["goal_amt", goal_amt], ["deviation_band", deviation_band],
                    ["borrowed_amt", borrowed_input], ["expected_yield", yield_input],
                    ["line_channel_token", line_channel_token], ["line_user_id", line_user_id] 
                ])
                st.cache_data.clear(); st.rerun()
            except Exception as e: st.error(f"雲端儲存失敗: {e}")

ts_amt = total_mkt * ts_pct / 100
tl_amt = total_mkt * tl_pct / 100
tc_amt = total_mkt * tc_pct / 100

# 🌟 補回這三個目標金額的視覺方塊！！！
st.markdown(f"""
<div class="responsive-grid">
    <div class="info-box b-blue" style="background:#1c2128; opacity:0.85;"><div class="label-bright">🎯 目標 股票</div><div class="box-pct">{ts_pct}%</div><div style="font-family:'Consolas'; color:#8b949e; font-size:1.05rem;">${fmt_int(ts_amt)}</div></div>
    <div class="info-box b-purple" style="background:#1c2128; opacity:0.85;"><div class="label-bright">🎯 目標 槓桿</div><div class="box-pct">{tl_pct}%</div><div style="font-family:'Consolas'; color:#8b949e; font-size:1.05rem;">${fmt_int(tl_amt)}</div></div>
    <div class="info-box b-green" style="background:#1c2128; opacity:0.85;"><div class="label-bright">🎯 目標 類現金</div><div class="box-pct">{tc_pct}%</div><div style="font-family:'Consolas'; color:#8b949e; font-size:1.05rem;">${fmt_int(tc_amt)}</div></div>
</div>
""", unsafe_allow_html=True)

# --- 9. 資產明細表 ---
st.write("📋 **資產部位明細 (智能警示版)**")
alert_triggered = False 
if active_data:
    html = "<div><table><thead><tr><th>標的</th><th>持股數</th><th>報價</th><th>Beta</th><th>均價</th><th>市值</th><th>報酬</th><th>YTD</th><th>佔比</th><th>建議操作</th></tr></thead><tbody>"
    for sid, d in active_data.items():
        if sid == "CASH" and d['sh'] == 0: continue
        pct = (d['m']/total_mkt*100) if pd.notna(total_mkt) and total_mkt!=0 else 0
        roi = f"{((d['curr']-d['avg'])/d['avg']*100):.1f}%" if pd.notna(d['avg']) and d['avg']>0 else "0%"
        ytd_roi = f"{((d['curr']-d['ytd'])/d['ytd']*100):.1f}%" if pd.notna(d['ytd']) and d['ytd']>0 else "0%"
        
        advice, alert_tag = "-", ""
        
        if sid == "00662":
            sh = int((ts_amt - s_v) / d['curr']) if pd.notna(ts_amt) and pd.notna(s_v) and pd.notna(d['curr']) and d['curr']>0 else 0
            if abs(sh) > 0: advice = f"<span class='{'up' if sh>0 else 'down'}'>{'加碼' if sh>0 else '減碼'} {abs(sh):,} 股</span>"
            if abs(s_p - ts_pct) >= deviation_band: alert_tag = "<span class='alert-tag'>⚠️ 觸發再平衡</span>"; alert_triggered = True
                
        elif "L" in sid or "631" in sid:
            sh = int((tl_amt - l_v) / d['curr']) if pd.notna(tl_amt) and pd.notna(l_v) and pd.notna(d['curr']) and d['curr']>0 else 0
            if abs(sh) > 0: advice = f"<span class='{'up' if sh>0 else 'down'}'>{'加碼' if sh>0 else '減碼'} {abs(sh):,} 股</span>"
            if abs(l_p - tl_pct) >= deviation_band: alert_tag = "<span class='alert-tag'>⚠️ 觸發再平衡</span>"; alert_triggered = True
                
        elif sid == "CASH": 
            diff_cash = tc_amt - c_v if pd.notna(tc_amt) and pd.notna(c_v) else 0
            advice = f"調整 ${fmt_int(diff_cash)}"
            if abs(c_p - tc_pct) >= deviation_band: alert_tag = "<span class='alert-tag'>⚠️ 觸發再平衡</span>"; alert_triggered = True
        
        safe_mkt = int(d['m']) if pd.notna(d['m']) else 0
        html += f"<tr><td><b>{sid}</b></td><td>{fmt_int(d['sh'])}</td><td>{d['curr']:.2f}</td><td>{d['beta']:.1f}</td><td>{d['avg']:.2f}</td><td>${safe_mkt:,}</td><td><span class='{'up' if d['curr']>=d['avg'] else 'down'}'>{roi}</span></td><td><span class='{'up' if d['curr']>=d['ytd'] else 'down'}'>{ytd_roi}</span></td><td>{pct:.1f}%</td><td>{advice} {alert_tag}</td></tr>"
    html += "</tbody></table></div>"
    st.write(html, unsafe_allow_html=True)

# 🌟 LINE Messaging API 推播設定
with st.sidebar:
    st.divider()
    st.header("📱 LINE 官方帳號推播設定")
    st.markdown("<span style='color:#ff7b72; font-size:0.85rem;'>⚠️ LINE Notify 已停用，已全面升級為 Messaging API</span>", unsafe_allow_html=True)
    channel_token_input = st.text_input("Channel Access Token", value=line_channel_token, type="password")
    user_id_input = st.text_input("您的 User ID", value=line_user_id, type="password")
    
    if st.button("📢 發送今日戰報", use_container_width=True):
        if not channel_token_input or not user_id_input:
            st.error("請填寫 Token 與 User ID！並點擊主畫面的『永久保存設定』。")
        else:
            alert_msg = "⚠️ 警示：有資產觸發再平衡水位！" if alert_triggered else "✅ 目前各資產皆在安全誤差範圍內。"
            msg = f"🛡️ 退休戰情室 {today_str} 戰報\n\n💰 總市值: ${fmt_int(total_mkt)}\n📈 今日損益: ${fmt_int(today_delta)}\n📉 距前高跌幅: {drawdown_pct:.1f}%\n🏦 維持率: {margin_display}\n\n{alert_msg}"
            
            headers = {
                "Authorization": f"Bearer {channel_token_input}",
                "Content-Type": "application/json"
            }
            payload = {
                "to": user_id_input,
                "messages": [{"type": "text", "text": msg}]
            }
            res = requests.post("https://api.line.me/v2/bot/message/push", headers=headers, json=payload)
            if res.status_code == 200: st.success("🚀 發送成功！請檢查 LINE。")
            else: st.error(f"❌ 發送失敗，錯誤碼: {res.status_code}，請確認 Token。")

    st.divider()
    st.header("🖊️ 交易錄入")
    op = st.selectbox("類型", ["買入", "賣出", "入金", "出金"])
    raw_sid = st.text_input("代號", value="00662").upper().strip()
    sid_in = raw_sid.zfill(5) if raw_sid.isdigit() and len(raw_sid) <= 3 else raw_sid
    sh_in = st.number_input("數量/金額", min_value=0.0, step=100.0)
    pr_in = st.number_input("單價", min_value=0.0, value=1.0)
    if st.button("💾 同步交易至雲端", use_container_width=True):
        client = get_client()
        ws = client.open_by_key(GS_ID).worksheet("Transactions")
        ws.append_row([datetime.now().strftime("%Y-%m-%d"), op, sid_in, sh_in, pr_in, ""])
        st.cache_data.clear(); st.rerun()
