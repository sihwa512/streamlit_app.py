import streamlit as st
import pandas as pd
import yfinance as yf
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime

# --- 1. 頁面與連線設定 ---
st.set_page_config(page_title="退休戰情室 V74.0 - 交易紀錄版", layout="wide")
GS_ID = "1jgZhEi-nmaXGUa5fJaYwk79xE9-QG4LwhwV89xriGPs"

def get_client():
    try:
        scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        s = st.secrets["gcp_service_account"]
        pk = s["private_key"].replace("\\n", "\n")
        creds_dict = {
            "type": s["type"], "project_id": s["project_id"], "private_key_id": s["private_key_id"],
            "private_key": pk, "client_email": s["client_email"], "client_id": s["client_id"],
            "auth_uri": s["auth_uri"], "token_uri": s["token_uri"],
            "auth_provider_x509_cert_url": s["auth_provider_x509_cert_url"],
            "client_x509_cert_url": s["client_x509_cert_url"]
        }
        return gspread.authorize(Credentials.from_service_account_info(creds_dict, scopes=scope))
    except Exception as e:
        st.error(f"連線失敗: {e}")
        return None

# --- 2. 核心邏輯：從明細計算庫存 ---
def load_all_data():
    client = get_client()
    if not client: return pd.DataFrame(), {}, 0.0
    try:
        doc = client.open_by_key(GS_ID)
        
        # A. 讀取所有交易明細
        ws_t = doc.worksheet("Transactions")
        t_data = ws_t.get_all_records()
        df_t = pd.DataFrame(t_data)
        
        stocks = {}
        total_injected_cash = 0.0
        
        if not df_t.empty:
            # 確保數字型態正確
            df_t['sh'] = pd.to_numeric(df_t['sh'], errors='coerce').fillna(0)
            df_t['pr'] = pd.to_numeric(df_t['pr'], errors='coerce').fillna(0)
            
            for _, row in df_t.iterrows():
                t_type = str(row['type']).strip()
                sid = str(row['id']).upper().strip()
                
                # 1. 計算投入本金 (入金/出金)
                if t_type == "入金": total_injected_cash += row['sh']
                elif t_type == "出金": total_injected_cash -= row['sh']
                
                # 2. 計算股票庫存與成本 (買入/賣出)
                elif t_type in ["買入", "賣出"]:
                    if sid not in stocks: stocks[sid] = {"sh": 0.0, "total_cost": 0.0}
                    
                    if t_type == "買入":
                        stocks[sid]["sh"] += row['sh']
                        stocks[sid]["total_cost"] += (row['sh'] * row['pr'])
                    elif t_type == "賣出":
                        stocks[sid]["sh"] -= row['sh']
                        # 賣出時按比例減少成本庫存
                        if (stocks[sid]["sh"] + row['sh']) > 0:
                            cost_ratio = row['sh'] / (stocks[sid]["sh"] + row['sh'])
                            stocks[sid]["total_cost"] -= (stocks[sid]["total_cost"] * cost_ratio)

            # 計算各標的平均成本
            for sid in stocks:
                if stocks[sid]["sh"] > 0:
                    stocks[sid]["avg_co"] = stocks[sid]["total_cost"] / stocks[sid]["sh"]
                else: stocks[sid]["avg_co"] = 0.0
                
        return df_t, stocks, total_injected_cash
    except Exception as e:
        st.warning(f"讀取失敗: {e}")
        return pd.DataFrame(), {}, 0.0

def add_transaction(t_type, sid, sh, pr, note):
    client = get_client()
    if not client: return
    try:
        doc = client.open_by_key(GS_ID)
        ws_t = doc.worksheet("Transactions")
        new_row = [datetime.now().strftime("%Y-%m-%d %H:%M"), t_type, sid.upper(), sh, pr, note]
        ws_t.append_row(new_row)
        st.success(f"✅ {t_type} 紀錄已新增！")
        st.cache_data.clear()
        st.rerun()
    except Exception as e: st.error(f"新增失敗: {e}")

# --- 3. 畫面呈現 ---
df_history, current_stocks, total_cash_input = load_all_data()

st.title("📊 退休戰情室 V74.0 - 自動累計版")

# 指標列
total_mkt = 0.0
rows = []
for sid, v in current_stocks.items():
    if v['sh'] <= 0: continue
    # 抓取現價
    try:
        t = yf.Ticker(f"{sid}.TW" if sid.isdigit() else sid)
        p = t.fast_info.last_price
    except: p = 0.0
    
    mkt_val = v['sh'] * p
    total_mkt += mkt_val
    pnl = (p - v['avg_co']) * v['sh']
    rows.append({"標的": sid, "現價": p, "股數": v['sh'], "平均成本": v['avg_co'], "市值": mkt_val, "損益": pnl})

m1, m2, m3 = st.columns(3)
with m1: st.metric("總市值", f"${total_mkt:,.0f}")
with m2: st.metric("累計投入本金", f"${total_cash_input:,.0f}")
with m3:
    pnl_total = total_mkt - total_cash_input
    pct = (pnl_total / total_cash_input * 100) if total_cash_input > 0 else 0
    st.metric("總實現+未實現損益", f"${pnl_total:,.0f}", f"{pct:.2f}%")

st.divider()

# --- 4. 側邊欄：新增交易明細 ---
with st.sidebar:
    st.header("🖊️ 新增交易紀錄")
    act_type = st.selectbox("動作類型", ["買入", "賣出", "入金", "出金"])
    
    if act_type in ["買入", "賣出"]:
        t_id = st.text_input("股票代號 (如 00662)")
        t_sh = st.number_input("成交股數", min_value=0.0, step=1.0)
        t_pr = st.number_input("成交單價", min_value=0.0)
    else:
        t_id = "CASH"
        t_sh = st.number_input("金額", min_value=0.0, step=1000.0)
        t_pr = 1.0
        
    t_note = st.text_input("備註")
    if st.button("送出交易明細"):
        add_transaction(act_type, t_id, t_sh, t_pr, t_note)

# --- 5. 顯示表格 ---
tab1, tab2 = st.tabs(["📈 目前持股匯總", "📜 歷史交易明細"])

with tab1:
    if rows:
        df_display = pd.DataFrame(rows)
        st.dataframe(df_display.style.format({
            "現價": "{:,.2f}", "股數": "{:,.0f}", "平均成本": "{:,.2f}", 
            "市值": "${:,.0f}", "損益": "${:,.0f}"
        }), use_container_width=True, hide_index=True)
    else:
        st.info("目前尚無持股紀錄。")

with tab2:
    if not df_history.empty:
        st.dataframe(df_history.sort_index(ascending=False), use_container_width=True, hide_index=True)
    else:
        st.info("尚無交易明細。")
