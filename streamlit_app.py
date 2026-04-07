import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go

# --- 頁面設定 ---
st.set_page_config(page_title="綜合退休戰情室 V70.3", layout="wide")

# --- 隱藏側邊欄功能區，增加視覺清爽感 ---
st.markdown("""
    <style>
    .stMetric { background-color: rgba(255,255,255,0.05); padding: 15px; border-radius: 10px; border: 1px solid #333; }
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

# --- 初始化資料 ---
if 'stocks' not in st.session_state:
    st.session_state.stocks = {"CASH": {"sh": 0.0, "co": 1.0}}
if 'principal' not in st.session_state:
    st.session_state.principal = 0.0

# --- 計算數據 ---
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
    processed_rows.append({"標的": sid, "名稱": name, "市值": mkt, "股數": v['sh']})

safe_val = b_val + c_val # 類現金

# --- 主介面 ---
st.title("📊 綜合退休戰情室 V70.3 Cloud")

# 指標列
col1, col2, col3 = st.columns(3)
with col1:
    st.metric("資產總市值", f"${total_mkt:,.0f}")
with col2:
    p_input = st.number_input("投入總本金", value=float(st.session_state.principal), step=10000.0)
    st.session_state.principal = p_input
with col3:
    true_pnl = total_mkt - st.session_state.principal
    pnl_pct = (true_pnl / st.session_state.principal * 100) if st.session_state.principal > 0 else 0
    st.metric("真實累積總損益", f"${true_pnl:,.0f}", f"{pnl_pct:.2f}%")

st.divider()

# --- 目標再平衡區塊 (對照優化版) ---
st.subheader("⚖️ 目標再平衡設定")
curr_beta = (s_val/total_mkt * 1.0 + l_val/total_mkt * 2.0) if total_mkt > 0 else 0
st.write(f"當前組合 Beta: **{curr_beta:.2f}**")

# 現況顯示列 (金額大小顏色完全同步)
cur1, cur2, cur3 = st.columns(3)
with cur1:
    st.markdown(f"<div style='text-align:center;'><small style='color:#aaa;'>現況 股票</small><br><b style='color:#00d4ff; font-size:24px;'>{(s_val/total_mkt*100 if total_mkt>0 else 0):.1f}%</b><br><b style='color:#00d4ff; font-size:22px;'>${s_val:,.0f}</b></div>", unsafe_allow_html=True)
with cur2:
    st.markdown(f"<div style='text-align:center;'><small style='color:#aaa;'>現況 槓桿</small><br><b style='color:#bd93f9; font-size:24px;'>{(l_val/total_mkt*100 if total_mkt>0 else 0):.1f}%</b><br><b style='color:#bd93f9; font-size:22px;'>${l_val:,.0f}</b></div>", unsafe_allow_html=True)
with cur3:
    st.markdown(f"<div style='text-align:center;'><small style='color:#aaa;'>現況 類現金</small><br><b style='color:#00ff88; font-size:24px;'>{(safe_val/total_mkt*100 if total_mkt>0 else 0):.1f}%</b><br><b style='color:#00ff88; font-size:22px;'>${safe_val:,.0f}</b></div>", unsafe_allow_html=True)

st.write("") 

# 手動調整與目標金額 (V69.5 & V69.6 合併邏輯)
st.write("🛠️ **手動調整目標佔比：**")
t_col1, t_col2, t_col3 = st.columns(3)
with t_col1:
    ts = st.number_input("股票 %", value=40)
    st.markdown(f"<div style='text-align:center;'><b style='color:#00d4ff; font-size:20px;'>${total_mkt * ts/100:,.0f}</b></div>", unsafe_allow_html=True)
with t_col2:
    tl = st.number_input("槓桿 %", value=30)
    st.markdown(f"<div style='text-align:center;'><b style='color:#bd93f9; font-size:20px;'>${total_mkt * tl/100:,.0f}</b></div>", unsafe_allow_html=True)
with t_col3:
    t_safe_pct = 100 - ts - tl
    st.write("類現金 (自動) %")
    st.markdown(f"<div style='text-align:center;'><b style='font-size:24px; color:#00ff88;'>{t_safe_pct}%</b><br><b style='color:#00ff88; font-size:20px;'>${total_mkt * t_safe_pct/100:,.0f}</b></div>", unsafe_allow_html=True)

target_beta = (ts/100 * 1.0 + tl/100 * 2.0)
st.info(f"🎯 目標組合 Beta: **{target_beta:.2f}**")

st.divider()

# --- 圓餅圖 (保留債券與現金細分) ---
st.subheader("🍩 資產配置佔比 (全分類對照)")
fig = go.Figure(data=[go.Pie(
    labels=['股票', '槓桿', '債券', '現金'], 
    values=[s_val, l_val, b_val, c_val],
    marker=dict(colors=['#00d4ff', '#bd93f9', '#ff9f1c', '#00ff88']),
    hole=.4
)])
fig.update_layout(template="plotly_dark", margin=dict(t=30, b=0, l=0, r=0))
st.plotly_chart(fig)

# --- 庫存清單 ---
st.subheader("📋 當前標的清單")
st.dataframe(pd.DataFrame(processed_rows), use_container_width=True, hide_index=True)

# --- 側邊欄：管理功能 ---
with st.sidebar:
    st.header("⚙️ 標的管理")
    add_id = st.text_input("新增標的代號 (例如 2330)")
    if st.button("新增入池"):
        if add_id: 
            st.session_state.stocks[add_id.upper()] = {"sh": 0.0, "co": 0.0}
            st.rerun()
    
    st.divider()
    st.write("📊 **快速記帳測試**")
    target_stk = st.selectbox("選擇要改的標的", options=list(st.session_state.stocks.keys()))
    new_sh = st.number_input("修改持有股數", value=float(st.session_state.stocks[target_stk]["sh"]))
    if st.button("更新股數"):
        st.session_state.stocks[target_stk]["sh"] = new_sh
        st.rerun()

    st.divider()
    if st.button("🗑️ 系統重置", type="primary"):
        st.session_state.stocks = {"CASH": {"sh": 0.0, "co": 1.0}}
        st.session_state.principal = 0.0
        st.rerun()
