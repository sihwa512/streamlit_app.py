import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go

# --- 頁面設定 ---
st.set_page_config(page_title="綜合退休戰情室 V70.4", layout="wide")

# --- 🌟 靈魂 CSS：還原單機網頁版質感 ---
st.markdown("""
    <style>
    /* 全域背景色 */
    .stApp { background-color: #0f111a; color: #e0e0e0; }
    
    /* 還原 V70 酷炫指標方塊 */
    [data-testid="stMetric"] {
        background: linear-gradient(145deg, #1b1e2e, #161926);
        border: 1px solid #333;
        border-radius: 15px;
        padding: 15px !important;
        box-shadow: 0 4px 15px rgba(0,0,0,0.4);
    }
    [data-testid="stMetricLabel"] > div { color: #aaa !important; font-weight: bold !important; font-size: 0.95rem !important; }
    [data-testid="stMetricValue"] > div { font-family: 'Consolas', monospace; color: #00d4ff !important; font-size: 1.8rem !important; }

    /* 調整輸入框樣式 */
    .stNumberInput input { background-color: #252836 !important; color: white !important; border: 1px solid #555 !important; border-radius: 8px !important; }
    
    /* 分隔線顏色 */
    hr { border: 0; border-top: 1px dashed #444; }

    /* 隱私模式遮罩 (模擬用) */
    .privacy-blur { filter: blur(10px); }
    
    /* 標題與副標題顏色 */
    h1, h2, h3 { color: #00d4ff !important; font-weight: 700 !important; }
    
    /* 隱藏 Streamlit 預設按鈕 */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    </style>
    """, unsafe_allow_html=True)

# --- 核心邏輯：抓取報價 ---
@st.cache_data(ttl=3600)
def get_price(symbol):
    if symbol == "CASH": return 1.0, "現金部位"
    try:
        s = symbol if "." in symbol else f"{symbol}.TW"
        t = yf.Ticker(s)
        return t.fast_info.last_price, t.info.get('shortName', symbol)
    except: return 0.0, symbol

# --- 初始化資料 (LocalStorage 替代方案) ---
if 'stocks' not in st.session_state:
    st.session_state.stocks = {"CASH": {"sh": 0.0, "co": 1.0}}
if 'principal' not in st.session_state:
    st.session_state.principal = 0.0

# --- 計算核心數據 ---
total_mkt = 0.0
s_val, l_val, b_val, c_val = 0.0, 0.0, 0.0, 0.0
processed_rows = []

for sid, v in st.session_state.stocks.items():
    price, name = get_price(sid)
    mkt = v['sh'] * price
    total_mkt += mkt
    if sid == "CASH": c_val += mkt
    elif "B" in sid: b_val += mkt
    elif "L" in sid: l_val += mkt
    else: s_val += mkt
    processed_rows.append({"標的": sid, "名稱": name, "現價": round(price,2), "股數": v['sh'], "市值": round(mkt,0)})

safe_val = b_val + c_val # 類現金

# --- 🚀 主介面開始 ---
st.title("📊 綜合退休戰情室 V70.4 Cloud")

# --- 頂部指標區 ---
col1, col2, col3 = st.columns(3)
with col1:
    st.metric("資產總市值", f"${total_mkt:,.0f}")

with col2:
    # 這裡稍微改變排版讓它好看一點
    st.markdown("<small style='color:#aaa;'>投入總本金 (點擊右方可修改)</small>", unsafe_allow_html=True)
    st.session_state.principal = st.number_input("Principal_Hidden", value=float(st.session_state.principal), label_visibility="collapsed")

with col3:
    true_pnl = total_mkt - st.session_state.principal
    pnl_pct = (true_pnl / st.session_state.principal * 100) if st.session_state.principal > 0 else 0
    pnl_color = "normal" if true_pnl >= 0 else "inverse"
    st.metric("真實累積總損益", f"${true_pnl:,.0f}", f"{pnl_pct:.2f}%", delta_color=pnl_color)

st.divider()

# --- ⚖️ 目標再平衡區塊 (高度美化) ---
st.subheader("⚖️ 目標再平衡設定")
curr_beta = (s_val/total_mkt * 1.0 + l_val/total_mkt * 2.0) if total_mkt > 0 else 0
st.markdown(f"當前組合 Beta: <b style='color:#bd93f9;'>{curr_beta:.2f}</b>", unsafe_allow_html=True)

# 1. 現況顯示列 (還原原版配色與大小)
st.write("🔍 **當前資產分布對照：**")
cur1, cur2, cur3 = st.columns(3)

def card_html(label, color, pct, val):
    return f"""
    <div style='text-align:center; padding:15px; background:rgba(255,255,255,0.03); border-radius:12px; border:1px solid {color}44;'>
        <small style='color:#aaa;'>{label}</small><br>
        <b style='color:{color}; font-size:26px;'>{pct:.1f}%</b><br>
        <b style='color:{color}; font-size:22px;'>${val:,.0f}</b>
    </div>
    """

with cur1:
    st.markdown(card_html("現況 股票", "#00d4ff", (s_val/total_mkt*100 if total_mkt>0 else 0), s_val), unsafe_allow_html=True)
with cur2:
    st.markdown(card_html("現況 槓桿", "#bd93f9", (l_val/total_mkt*100 if total_mkt>0 else 0), l_val), unsafe_allow_html=True)
with cur3:
    st.markdown(card_html("現況 類現金", "#00ff88", (safe_val/total_mkt*100 if total_mkt>0 else 0), safe_val), unsafe_allow_html=True)

st.write("") # 間隔

# 2. 手動調整列
t_col1, t_col2, t_col3 = st.columns(3)
with t_col1:
    ts = st.number_input("目標 股票 %", value=40)
    st.markdown(f"<div style='text-align:center;'><b style='color:#00d4ff; font-size:20px;'>${total_mkt * ts/100:,.0f}</b></div>", unsafe_allow_html=True)
with t_col2:
    tl = st.number_input("目標 槓桿 %", value=30)
    st.markdown(f"<div style='text-align:center;'><b style='color:#bd93f9; font-size:20px;'>${total_mkt * tl/100:,.0f}</b></div>", unsafe_allow_html=True)
with t_col3:
    t_safe_pct = 100 - ts - tl
    st.markdown(f"<p style='text-align:center; color:#aaa; margin-bottom:5px;'>目標 類現金 (自動)</p><div style='text-align:center;'><b style='font-size:26px; color:#00ff88;'>{t_safe_pct}%</b><br><b style='color:#00ff88; font-size:20px;'>${total_mkt * t_safe_pct/100:,.0f}</b></div>", unsafe_allow_html=True)

target_beta = (ts/100 * 1.0 + tl/100 * 2.0)
st.markdown(f"<div style='background:rgba(255, 159, 28, 0.1); padding:10px; border-radius:8px; border-left:5px solid #ff9f1c; margin-top:15px;'>🎯 目標組合 Beta: <b>{target_beta:.2f}</b></div>", unsafe_allow_html=True)

st.divider()

# --- 🍩 圓餅圖 ---
c_pie, c_table = st.columns([1, 1.5])
with c_pie:
    st.subheader("🍩 資產配置佔比")
    fig = go.Figure(data=[go.Pie(
        labels=['股票', '槓桿', '債券', '現金'], 
        values=[s_val, l_val, b_val, c_val],
        marker=dict(colors=['#00d4ff', '#bd93f9', '#ff9f1c', '#00ff88']),
        hole=.5
    )])
    fig.update_layout(template="plotly_dark", margin=dict(t=0, b=0, l=0, r=0), showlegend=True)
    st.plotly_chart(fig, use_container_width=True)

with c_table:
    st.subheader("📋 目前標的庫存")
    if processed_rows:
        st.dataframe(pd.DataFrame(processed_rows), use_container_width=True, hide_index=True)

# --- 側邊欄：進階管理 ---
with st.sidebar:
    st.header("⚙️ 管理中心")
    add_id = st.text_input("新增代號 (如 2330 / CASH)")
    if st.button("➕ 新增入池"):
        if add_id: 
            st.session_state.stocks[add_id.upper()] = {"sh": 0.0, "co": 0.0}
            st.rerun()
    
    st.divider()
    st.write("📊 **快速調整股數**")
    if list(st.session_state.stocks.keys()):
        target_stk = st.selectbox("選取標的", options=list(st.session_state.stocks.keys()))
        new_sh = st.number_input("持有股數/金額", value=float(st.session_state.stocks[target_stk]["sh"]))
        if st.button("✅ 更新庫存"):
            st.session_state.stocks[target_stk]["sh"] = new_sh
            st.rerun()

    st.divider()
    if st.button("🗑️ 系統重置", type="primary"):
        st.session_state.stocks = {"CASH": {"sh": 0.0, "co": 1.0}}
        st.session_state.principal = 0.0
        st.rerun()
