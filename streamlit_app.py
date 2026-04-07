def save_data_to_gs(stocks):
    client = get_gspread_client()
    if not client: 
        st.error("❌ 無法取得 Google Client，請檢查 Secrets 設定")
        return
    try:
        # 開啟檔案
        sh_file = client.open(GS_FILENAME)
        worksheet = sh_file.worksheet(GS_SHEETNAME)
        
        # 準備資料
        data_to_save = [["id", "sh", "co"]]
        for sid, v in stocks.items():
            data_to_save.append([sid, float(v['sh']), float(v['co'])])
        
        # 執行更新
        worksheet.clear()
        worksheet.update("A1", data_to_save)
        
        # 清除快取並強制重新載入，確保畫面同步
        st.cache_data.clear()
        st.toast("✅ 雲端數據已成功寫入並同步！")
    except Exception as e:
        st.error(f"❌ 寫入失敗，錯誤訊息: {str(e)}")
