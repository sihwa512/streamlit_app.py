import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
import gspread
from google.oauth2.service_account import Credentials
import re
import traceback

# --- 1. 頁面設定 ---
st.set_page_config(page_title="綜合退休戰情室 V73.3", layout="wide")

# --- 2. 雲端連線設定 ---
GS_ID = "1jgZhEi-nmaXGUa5fJaYwk79xE9-QG4LwhwV89xriGPs"

def get_client():
    try:
        scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        # 這裡從 Secrets 讀取
        if "gcp_service_account" not in st.secrets:
            st.error("❌ Secrets 中找不到 gcp_service_account 設定！")
            return None
        
        creds_info = dict(st.secrets["gcp_service_account"])
        if "private_key" in creds_info:
            # 強制清理金鑰中的換行符號
            creds_info["private_key"] = creds_info["private_key"].replace("\\n", "\n")
            creds_info["private_key"] = re.sub(r'[^\x20-\x7E\n]', '', creds_info["private_key"])
            
        creds = Credentials.from_service_account_info(creds_info, scopes=scope)
        return gspread.authorize(creds)
    except Exception as e:
        st.error(f"❌ 連線初始化嚴重失敗: {e}")
        return None

def load_data():
    client = get_client()
    # 基礎預設值，保證畫面不消失
    def_s = {"CASH": {"sh": 200000.0, "co": 1.0}}
    def_p = 50000.0
    if not client: return def_s, def_p
    try:
        doc = client.open_by_key(GS_ID)
        ws_s = doc.worksheet("Stocks")
        all_v = ws_s.get_all_values()
        stocks = {}
        if len(all_v) > 1:
            for r in all_v[1:]:
                if len(r) >= 3 and r[0]: 
                    stocks[str(r[0]).upper().strip()] = {"sh": float(r[1] or 0), "co": float(r[2] or 0)}
        else: stocks = def_s
        
        try:
            ws_v = doc.worksheet("Settings")
            v_v = ws_v.get_all_values()
            p = float(v_v[1][1]) if len(v_v) > 1 else def_p
        except: p = def_p
        return stocks, p
    except Exception as e:
        st.warning(f"⚠️ 讀取雲端失敗 (將使用預設值): {e}")
        return def_s, def_p

def save_data(stocks, principal):
    client = get_client()
    if not client: 
        st.error("❌ 無法取得 Client，無法存檔。")
        return
    try:
        st.info("🔄 正在嘗試寫入雲端...")
        doc = client.open_by_key(GS_ID)
        
        # 1. 更新持股
        ws_s = doc.worksheet("Stocks")
        data_s = [["id", "sh", "co"]] + [[k, float(v['sh']), float(v['co'])] for k, v in stocks.items()]
        ws_s.update(values=data_s, range_name='A1')
        
        # 2. 更新本金
        ws_v = doc.worksheet("Settings")
        ws_v.update(values=[["key", "value"], ["principal", float(principal)]], range_name='A1')
        
        st.success("✅ 雲端同步成功！數據已存入 Google Sheets。")
        st.cache_data.clear()
    except Exception as e:
        # 🌟 這裡最關鍵：把錯誤的詳細原因全部噴出來
        st.error(f"❌ 同步失敗！請檢查權限或分頁名稱。")
        st.code(traceback.format_exc())

# --- 3. 視覺設定 ---
st.markdown("<style>.stApp{background-color:#0d1117; color:#c9d1d9;} [data-testid='stMetricValue']>div{color:#00d4ff!important; font-weight:800; font-size:2.6rem!important;}</style>", unsafe_allow_html=True)

if 'stocks' not in st.session_state:
    st.session_state.stocks, st.session_state.principal = load_data()

@st.cache_data(ttl=600)
def fetch_price(sid):
    if sid == "CASH": return 1.0, "閒置現金"
    names = {"00662":"富邦NASDAQ", "00670L":"NASDAQ正2", "00865B":"美債1-3Y", "00631L":"50正2", "0050":"元大50", "2330":"台積電"}
    d_name = names.get(sid, sid)
    for suf in [".TW", ".TWO", ""]:
        try:
            t = yf.Ticker(f"{sid}{suf}")
            p = t.fast_info.last_price
            if p > 0: return float(p), d_name
        except: continue
    return 0.0, d_name

# --- 4. 計算數據 ---
total_mkt, s_val, l_val, b_val, c_val = 0.0, 0.0, 0.0, 0.0, 0.0
rows = []
for sid, v in st.session_state.stocks.items():
    p, name = fetch_price(sid)
    m = v['sh'] * p
    total_mkt += m
    if sid == "CASH": c_val += m
    elif "B" in sid: b_val += m
    elif "L" in sid: l_val += m
    else: s_val += m
    pnl = (p - v['co']) * v['sh']
    rows.append({"標的": sid, "名稱": name, "現價": f"{p:,.2f}", "股數": f"{v['sh']:,.0f}", "市值": m, "損益": f"{pnl:,.0f}"})

# --- 5. 主介面 ---
st.title("📊 綜合退休戰情室 V73.3 Debug Mode")

m1, m2, m3 = st.columns(3)
with m1: st.metric("總市值", f"${total_mkt:,.0f}")
with m2: 
    new_p = st.number_input("設定投入本金", value=float(st.session_state.principal))
    if st.button("💾 儲存並同步本金"):
        st.session_state.principal = new_p
        save_data(st.session_state.stocks, new_p)
with m3:
    true_pnl = total_mkt - st.session_state.principal
    pct = (true_pnl / st.session_state.principal * 100) if st.session_state.principal > 0 else 0
    st.metric("總損益", f"${true_pnl:,.0f}", f"{pct:.2f}%")

st.divider()

# 方塊卡片
c1, c2, c3 = st.columns(3)
def draw_card(title, color, val):
    p = (val / total_mkt * 100) if total_mkt > 0 else 0
    st.markdown(f"<div style='text-align:center; padding:20px; background:#161b22; border-radius:12px; border-top:6px solid {color};'><small style='color:#8b949e;'>{title}</small><br><b style='color:{color}; font-size:26px;'>{p:.1f}%</b><br><b style='color:{color}; font-size:24px;'>${val:,.0f}</b></div>", unsafe_allow_html=True)

with c1: draw_card("現況 股票", "#58a6ff", s_val)
with c2: draw_card("現況 槓桿", "#bc8cff", l_val)
with c3: draw_card("現況 類現金", "#3fb950", b_val + c_val)

st.divider()

# 表格與修改
col_t, col_s = st.columns([2, 1])
with col_t:
    st.subheader("📋 目前持股清單")
    df = pd.DataFrame(rows)
    df['市值'] = df['市值'].apply(lambda x: f"${x:,.0f}")
    st.dataframe(df, use_container_width=True, hide_index=True)

with col_s:
    st.subheader("⚙️ 雲端操作")
    target = st.selectbox("選取標的", options=list(st.session_state.stocks.keys()))
    n_sh = st.number_input("持有股數", value=float(st.session_state.stocks[target]["sh"]))
    n_co = st.number_input("買入成本", value=float(st.session_state.stocks[target]["co"]))
    if st.button("💾 儲存修改"):
        st.session_state.stocks[target] = {"sh": n_sh, "co": n_co}
        save_data(st.session_state.stocks, st.session_state.principal)
        st.rerun()
    
    st.divider()
    new_id = st.text_input("➕ 新增標的代號").upper().strip()
    if st.button("確認新增"):
        if new_id:
            st.session_state.stocks[new_id] = {"sh": 0.0, "co": 0.0}
            save_data(st.session_state.stocks, st.session_state.principal)
            st.rerun()
