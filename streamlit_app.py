import streamlit as st
import pandas as pd
import yfinance as yf
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import re

# --- 1. 基本設定 ---
st.set_page_config(page_title="退休戰情室 V74.2", layout="wide")
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
    except Exception as e:
        st.error(f"連線失敗: {e}")
        return None

# --- 2. 數據處理核心 ---
def load_all_data():
    client = get_client()
    if not client: return pd.DataFrame(), {}, 0.0
    try:
        doc = client.open_by_key(GS_ID)
        # 🌟 自動建立缺失的分頁
        try:
            ws_t = doc.worksheet("Transactions")
        except:
            ws_t = doc.add_worksheet(title="Transactions", rows="100", cols="10")
            ws_t.append_row(["date", "type", "id", "sh", "pr", "note"])
            
        t_data = ws_t.get_all_records()
        df_t = pd.DataFrame(t_data)
        
        stocks = {}
        total_injected = 0.0
        
        if not df_t.empty:
            df_t['sh'] = pd.to_numeric(df_t['sh'], errors='coerce').fillna(0)
            df_t['pr'] = pd.to_numeric(df_t['pr'], errors='coerce').fillna(0)
            
            for _, row in df_t.iterrows():
                t_type = str(row['type']).strip()
                sid = str(row['id']).upper().strip()
                
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
            if stocks[sid]["sh"] > 0:
                stocks[sid]["avg"] = stocks[sid]["cost"] / stocks[sid]["sh"]
            else: stocks[sid]["avg"] = 0.0
                
        return df_t, stocks, total_injected
    except Exception as e:
        st.warning(f"系統初始化中... 請嘗試新增第一筆交易。({e})")
        return pd.DataFrame(), {}, 0.0

def add_entry(t_type, sid, sh, pr, note):
    client = get_client()
    if not client: return
    try:
        doc = client.open_by_key(GS_ID)
        ws_t = doc.worksheet("Transactions")
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        ws_t.append_row([now, t_type, sid.upper(), sh, pr, note])
        st.success("✅ 紀錄已成功寫入雲端！")
        st.cache_data.clear()
        st.rerun()
    except Exception as e: st.error(f"新增失敗: {e}")

# --- 3. 獲取報價 ---
@st.cache_data(ttl=600)
def get_price(sid):
    if sid == "CASH": return 1.0
    names = {"00662":"富邦NASDAQ", "00670L":"NASDAQ正2", "00865B":"美債1-3Y", "00631L":"50正2", "0050":"元大50", "2330":"台積電"}
    for suf in [".TW", ".TWO", ""]:
        try:
            t_obj = yf.Ticker(f"{sid}{suf}")
            p = t_obj.fast_info.last_price
            if p > 0: return float(p), names.get(sid, sid)
        except: continue
    return 0.0, sid

# --- 4. 計算與邏輯 ---
df_hist, cur_stocks, total_capital = load_all_data()

total_mkt = 0.0
display_rows = []
for sid, v in cur_stocks.items():
    if v['sh'] <= 0: continue
    p, name = get_price(sid)
    m = v['sh'] * p
    total_mkt += m
    pnl = (p - v['avg']) * v['sh']
    display_rows.append({"代號": sid, "名稱": name, "現價": p, "持有股數": v['sh'], "平均成本": v['avg'], "市值": m, "損益": pnl})

# --- 5. 畫面 ---
st.title("📊 退休戰情室 V74.2")

# 上方指標
m1, m2, m3 = st.columns(3)
with m1: st.metric("資產總市值", f"${total_mkt:,.0f}")
with m2: st.metric("累計投入本金", f"${total_capital:,.0f}")
with m3:
    gain = total_mkt - total_capital
    pct = (gain / total_capital * 100) if total_capital > 0 else 0
    st.metric("總累積損益", f"${gain:,.0f}", f"{pct:.2f}%")

st.divider()

# 側邊欄
with st.sidebar:
    st.header("🖊️ 交易紀錄錄入")
    op = st.selectbox("類型", ["買入", "賣出", "入金", "出金"])
    
    if op in ["買入", "賣出"]:
        sid_in = st.text_input("代號 (如 00662)").upper()
        sh_in = st.number_input("股數", min_value=0.0, step=100.0)
        pr_in = st.number_input("單價", min_value=0.0)
    else:
        sid_in = "CASH"
        sh_in = st.number_input("金額 (NTD)", min_value=0.0, step=10000.0)
        pr_in = 1.0
    
    note_in = st.text_input("備註")
    if st.button("💾 送出並存檔"):
        add_entry(op, sid_in, sh_in, pr_in, note_in)

# 表格與歷史
t1, t2 = st.tabs(["📈 持股匯總", "📜 交易日誌"])
with t1:
    if display_rows:
        df_disp = pd.DataFrame(display_rows)
        st.dataframe(df_disp.style.format({
            "現價": "{:,.2f}", "持有股數": "{:,.0f}", "平均成本": "{:,.2f}", "市值": "${:,.0f}", "損益": "${:,.0f}"
        }), use_container_width=True, hide_index=True)
    else: st.info("目前尚無資料，請先從側邊欄點擊「入金」開始。")

with t2:
    if not df_hist.empty:
        st.dataframe(df_hist.iloc[::-1], use_container_width=True, hide_index=True)
