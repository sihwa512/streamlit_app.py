def get_client():
    try:
        scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds_info = dict(st.secrets["gcp_service_account"])
        
        # 🌟 自動修正私鑰中的換行符號，防止 InvalidByte 報錯
        if "private_key" in creds_info:
            creds_info["private_key"] = creds_info["private_key"].replace("\\n", "\n")
            
        return gspread.authorize(Credentials.from_service_account_info(creds_info, scopes=scope))
    except Exception as e:
        # 如果失敗，在側邊欄顯示更易讀的提示
        st.sidebar.error("❌ 金鑰格式有誤，請檢查 Secrets 設定")
        st.sidebar.code(str(e)) # 顯示具體報錯供除錯
        return None
