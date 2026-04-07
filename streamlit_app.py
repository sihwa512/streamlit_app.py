import streamlit as st
import pandas as pd
import yfinance as yf
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import re

# --- 1. 基本設定 ---
st.set_page_config(page_title="退休戰情室 V74.1", layout="wide")
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

# --- 2. 數據處理：流水帳計算庫存 ---
def load_all_data():
    client = get_client()
    if not client: return pd.DataFrame(), {}, 0.0
    try:
        doc = client.open_by_key(GS_ID)
        ws_t = doc.worksheet("Transactions")
        t_data = ws_t.get_all_records()
        df_t = pd.DataFrame(t_data)
        
        stocks = {}
        total_injected = 0.0
        
        if not df_t.empty:
            # 數據清潔
            df_t['sh'] = pd.to_numeric(df_t['sh'], errors='coerce').fillna(0)
            df_t['pr'] = pd.to_numeric(df_t['pr'], errors='coerce').fillna(0)
            
            for _, row in df_t.iterrows():
                t_type = str(row['type']).strip()
                sid = str(row['id']).upper().strip()
                
                # A. 處理本金變動
                if t_type == "入金": total_injected += row['sh']
                elif t_type == "出金": total_injected -= row['sh']
                
                # B. 處理股票交易
                elif t_type in ["買入", "賣出"]:
                    if sid not in stocks: stocks[sid] = {"sh": 0.0, "cost": 0.0}
                    if t_type == "買入":
                        stocks[sid]["sh"] += row['sh']
                        stocks[sid]["cost"] += (row['sh'] * row['pr'])
                    elif t_type == "賣出":
                        # 賣出時依比例減去成本
                        if (stocks[sid]["sh"]) > 0:
                            ratio = row['sh'] / stocks[sid]["sh"]
                            stocks[sid]["cost"] -= (stocks[sid]["cost"] * ratio)
                        stocks[sid]["sh"] -= row['sh']

        # 計算平均成本
        for sid in stocks:
            if stocks[sid]["sh"] > 0:
                stocks[sid]["avg"] = stocks[sid]["cost"] / stocks[sid]["sh"]
            else: stocks[sid]["avg"] = 0.0
                
        return df_t, stocks, total_injected
    except Exception as e:
        st.warning(f"⚠️ 尚未在雲端找到 'Transactions' 分頁或數據格式錯誤。")
        return pd.DataFrame(), {}, 0.0

def add_entry(t_type, sid, sh, pr, note):
    client = get_client()
    if not client: return
    try:
        doc = client.open_by_key(GS_ID)
        ws_t = doc.worksheet("Transactions")
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        ws_t.append_row([now, t_type, sid.upper(), sh, pr, note])
        st.success("✅ 紀錄已同步！")
        st.cache_data.clear()
        st.rerun()
    except Exception as e: st.error(f"新增失敗: {e}")

# --- 3. 獲取數據與運算 ---
df_hist, cur_stocks, total_capital = load_all_data()

@st.cache_data(ttl=600)
def get_price(sid):
    if sid == "CASH": return 1.0
    for suf in [".TW", ".TWO", ""]:
        try:
            p = yf.Ticker(f"{sid}{suf}").fast_info.last_price
            if p > 0: return float(p)
        except: continue
    return 0.0

# 建立顯示列表
total_mkt = 0.0
display_rows = []
for sid, v in cur_stocks.items():
    if v['sh'] <= 0: continue
    p = get_price(sid)
    m = v['sh'] * p
    total_mkt += m
    pnl = (p - v['avg']) * v['sh']
    display_rows.append({"標的": sid, "現價": p, "股數": v['sh'], "平均成本": v['avg'], "市值": m, "損益": pnl})

# --- 4. 畫面呈現 ---
st.title("📊 退休戰情室 V74.1 - 流水帳版")

c1, c2, c3 = st.columns(3)
with c1: st.metric("資產總市值", f"${total_mkt:,.0f}")
with c2: st.metric("累計投入本金", f"${total_capital:,.0f}")
with c3:
    gain = total_mkt - total_capital
    pct = (gain / total_capital * 100) if total_capital > 0 else 0
    st.metric("總累積損益", f"${gain:,.0f}", f"{pct:.2f}%")

st.divider()

# 側邊欄：新增交易
with st.sidebar:
    st.header("🖊️ 新增交易紀錄")
    op = st.selectbox("類型", ["買入", "賣出", "入金", "出金"])
    
    if op in ["買入", "賣出"]:
        sid_in = st.text_input("代號 (如 00662)").upper()
        sh_in = st.number_input("股數", min_value=0.0)
        pr_in = st.number_input("成交單價", min_value=0.0)
    else:
        sid_in = "CASH"
        sh_in = st.number_input("金額 (新台幣)", min_value=0.0, step=1000.0)
        pr_in = 1.0
    
    note_in = st.text_input("備註")
    if st.button("💾 送出紀錄"):
        add_entry(op, sid_in, sh_in, pr_in, note_in)

# 分頁顯示
t_stock, t_hist = st.tabs(["📈 目前庫存", "📜 歷史紀錄"])
with t_stock:
    if display_rows:
        st.dataframe(pd.DataFrame(display_rows), use_container_width=True, hide_index=True)
    else:
        st.info("尚未有持股數據，請從側邊欄新增「入金」或「買入」紀錄。")

with t_hist:
    if not df_hist.empty:
        st.dataframe(df_hist.sort_index(ascending=False), use_container_width=True, hide_index=True)
