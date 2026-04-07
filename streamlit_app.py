import streamlit as st
import pandas as pd
import yfinance as yf
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import re
import time

# --- 1. 基本設定 ---
st.set_page_config(page_title="退休戰情室 V74.4", layout="wide")
GS_ID = "1jgZhEi-nmaXGUa5fJaYwk79xE9-QG4LwhwV89xriGPs"

def get_client():
    try:
        scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        s = st.secrets["gcp_service_account"]
        pk = s["private_key"].replace("\\n", "\n")
        pk = re.sub(r'[^\x20-\x7E\n]', '', pk)
        creds = {
            "type": s["type"], "project_id": s["project_id"], "private_key_id": s["private_key_id"],
            "private_key": pk, "client_email": s["client_email"], "client_id": s["client_id"],
            "auth_uri": s["auth_uri"], "token_uri": s["token_uri"],
            "auth_provider_x509_cert_url": s["auth_provider_x509_cert_url"],
            "client_x509_cert_url": s["client_x509_cert_url"]
        }
        return gspread.authorize(Credentials.from_service_account_info(creds, scopes=scope))
    except: return None

# --- 2. 數據加載與處理 ---
@st.cache_data(ttl=30)
def load_data():
    client = get_client()
    if not client: return pd.DataFrame(), {}, 0.0
    try:
        doc = client.open_by_key(GS_ID)
        ws_t = doc.worksheet("Transactions")
        df_t = pd.DataFrame(ws_t.get_all_records())
        
        stocks = {}
        total_injected = 0.0
        
        if not df_t.empty:
            df_t['sh'] = pd.to_numeric(df_t['sh'], errors='coerce').fillna(0)
            df_t['pr'] = pd.to_numeric(df_t['pr'], errors='coerce').fillna(0)
            
            for _, row in df_t.iterrows():
                t_type = str(row['type']).strip()
                sid = str(row['id']).upper().strip()
                # 🌟 自動補齊 5 位代號 (如 662 -> 00662)
                if sid.isdigit() and len(sid) < 5: sid = sid.zfill(5)
                
                if t_type == "入金": total_injected += row['sh']
                elif t_type == "出金": total_injected -= row['sh']
                elif t_type in ["買入", "賣出"]:
                    if sid not in stocks: stocks[sid] = {"sh": 0.0, "cost": 0.0}
                    if t_type == "買入":
                        stocks[sid]["sh"] += row['sh']
                        stocks[sid]["cost"] += (row['sh'] * row['pr'])
                    elif t_type == "賣出":
                        if stocks[sid]["sh"] > 0:
                            ratio = row['sh'] / stocks[sid]["sh"]
                            stocks[sid]["cost"] -= (stocks[sid]["cost"] * ratio)
                        stocks[sid]["sh"] -= row['sh']

        for sid in stocks:
            if stocks[sid]["sh"] > 0: stocks[sid]["avg"] = stocks[sid]["cost"] / stocks[sid]["sh"]
            else: stocks[sid]["avg"] = 0.0
        return df_t, stocks, total_injected
    except: return pd.DataFrame(), {}, 0.0

@st.cache_data(ttl=600)
def get_stock_info(sid):
    if sid == "CASH": return 1.0, "現金"
    names = {"00662":"富邦NASDAQ", "00670L":"NASDAQ正2", "00865B":"美債1-3Y", "00631L":"50正2", "0050":"元大50", "2330":"台積電"}
    # 🌟 確保台灣代號格式正確
    ticker_sid = f"{sid}.TW" if sid.isdigit() else sid
    try:
        ticker = yf.Ticker(ticker_sid)
        p = ticker.fast_info.last_price
        if p is None or p == 0:
            h = ticker.history(period="1d")
            p = h['Close'].iloc[-1] if not h.empty else 0.0
        return float(p), names.get(sid, sid)
    except: return 0.0, sid

# --- 3. 獲取數據 ---
df_hist, cur_stocks, total_capital = load_data()

# --- 4. 畫面呈現 ---
st.title("📊 退休戰情室 V74.4")

total_mkt = 0.0
display_rows = []
for sid, v in cur_stocks.items():
    if v['sh'] <= 0: continue
    p, name = get_stock_info(sid)
    m = v['sh'] * p
    total_mkt += m
    pnl = (p - v['avg']) * v['sh']
    display_rows.append({"代號": sid, "名稱": name, "現價": p, "股數": v['sh'], "成本": v['avg'], "市值": m, "損益": pnl})

m1, m2, m3 = st.columns(3)
with m1: st.metric("資產總市值", f"${total_mkt:,.0f}")
with m2: st.metric("累計投入本金", f"${total_capital:,.0f}")
with m3:
    gain = total_mkt - total_capital
    pct = (gain / total_capital * 100) if total_capital > 0 else 0
    st.metric("總累積損益", f"${gain:,.0f}", f"{pct:.2f}%")

st.divider()

with st.sidebar:
    st.header("🖊️ 交易紀錄錄入")
    op = st.selectbox("類型", ["買入", "賣出", "入金", "出金"])
    if op in ["買入", "賣出"]:
        sid_raw = st.text_input("代號 (如 00662)").upper().strip()
        # 🌟 自動幫忙補 0
        sid_in = sid_raw.zfill(5) if sid_raw.isdigit() and len(sid_raw) < 5 else sid_raw
        sh_in = st.number_input("股數", min_value=0.0, step=100.0)
        pr_in = st.number_input("單價", min_value=0.0)
    else:
        sid_in = "CASH"
        sh_in = st.number_input("金額 (新台幣)", min_value=0.0, step=10000.0)
        pr_in = 1.0
    
    if st.button("確定寫入並刷新"):
        client = get_client()
        ws_t = client.open_by_key(GS_ID).worksheet("Transactions")
        ws_t.append_row([datetime.now().strftime("%Y-%m-%d %H:%M"), op, sid_in, sh_in, pr_in, "系統更新"])
        st.success("✅ 數據已寫入雲端！")
        st.cache_data.clear() # 🌟 強制清除所有緩存，保證數據立刻更新
        time.sleep(1)
        st.rerun()

t1, t2 = st.tabs(["📈 持股匯總", "📜 歷史流水帳"])
with t1:
    if display_rows:
        df_final = pd.DataFrame(display_rows)
        # 🌟 強制四捨五入解決 .9999 問題
        st.dataframe(df_final.style.format({
            "現價": "{:,.2f}", "股數": "{:,.0f}", "成本": "{:,.2f}", 
            "市值": "${:,.0f}", "損益": "${:,.0f}"
        }), use_container_width=True, hide_index=True)
    else: st.info("尚無數據，請先新增入金或買入紀錄。")
with t2:
    if not df_hist.empty: st.dataframe(df_hist.iloc[::-1], use_container_width=True, hide_index=True)
