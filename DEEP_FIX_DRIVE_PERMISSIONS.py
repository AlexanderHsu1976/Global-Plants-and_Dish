import streamlit as st
import pandas as pd
import json
import time
from data_maintenance import get_drive_service, get_gsheet_client

# --- [配置區] ---
FOLDER_ID = "1IvRyZtlRlDZSitoOw6b_HqnVoA4Qj0dw"
SPREADSHEET_NAME = "Global_Plants_DB"

def repair_drive_and_sync_sheets():
    """ 
    深度救援工具：
    1. 前往 Google Drive 修正 FOLDER_ID 內所有檔案的公開權限。
    2. 將檔案連結轉換為最高相容性的 CDN 格式 (lh3.googleusercontent.com)。
    3. 如果該檔案對應到 Google Sheets 中的資料，自動更新 Sheets 連結。
    """
    st.title("🛡️ Google Drive 圖片權限深度修復工具")
    st.info("此工具將遍歷您的植物資料夾，確保每一張圖片都是『任何人皆可檢視』，並優化連結格式以解決無法顯示的問題。")

    if st.button("🚀 開始深度修復與同步"):
        service = get_drive_service()
        if not service:
            st.error("❌ 無法啟動 Google Drive 服務，請檢查憑證。")
            return

        # 1. 抓取 Drive 資料夾內的檔案清單
        with st.spinner("正在掃描雲端硬碟檔案..."):
            try:
                results = service.files().list(
                    q=f"'{FOLDER_ID}' in parents and trashed = false",
                    fields="files(id, name, webViewLink)",
                    pageSize=100
                ).execute()
                files = results.get('files', [])
            except Exception as e:
                st.error(f"掃描失敗: {e}")
                return

        if not files:
            st.warning("資料夾內沒有檔案！")
            return

        st.write(f"📂 找到 {len(files)} 個檔案，開始修復...")
        
        # 建立 ID -> CDN 連結的映射表
        id_to_cdn_map = {}

        for f in files:
            f_id = f['id']
            f_name = f['name']
            try:
                # 2. 強制設定權限為 Public Viewer
                # (解決：上傳後權限延遲或消失的問題)
                service.permissions().create(
                    fileId=f_id,
                    body={'type': 'anyone', 'role': 'reader'},
                    sendNotificationEmail=False
                ).execute()
                
                # 3. 生成最高相容性的直連網址 (繞過 Drive 驗證重導向)
                cdn_url = f"https://lh3.googleusercontent.com/d/{f_id}"
                id_to_cdn_map[f_id] = cdn_url
                st.success(f"✅ 修復完成：{f_name}")
            except Exception as e:
                st.error(f"❌ 修復失敗 {f_name}: {e}")

        st.divider()

        # 4. 同步更新 Google Sheets (選擇性，避免重複操作)
        with st.spinner("正在同步至 Google Sheets..."):
            client = get_gsheet_client()
            if client:
                sh = client.open(SPREADSHEET_NAME)
                ws = sh.worksheet("plant_master")
                df = pd.DataFrame(ws.get_all_records())
                
                updated_count = 0
                # 掃描 df 中的「代表照片」欄位，如果含有舊的 uc?id= 連結，轉換為 CDN 連結
                for idx, row in df.iterrows():
                    curr_url = str(row.get('代表照片', ''))
                    # 判斷是否為 Drive 連結
                    if "drive.google.com" in curr_url or "google.com/uc" in curr_url:
                        # 擷取 ID (這是一個簡單的 regex 提取)
                        import re
                        match = re.search(r"id=([\w-]+)", curr_url)
                        if not match: 
                            match = re.search(r"file/d/([\w-]+)", curr_url)
                        
                        if match:
                            target_id = match.group(1)
                            # 使用新的 CDN 格式覆蓋
                            new_url = f"https://lh3.googleusercontent.com/d/{target_id}"
                            df.at[idx, '代表照片'] = new_url
                            updated_count += 1
                
                if updated_count > 0:
                    ws.clear()
                    ws.update([df.columns.values.tolist()] + df.values.tolist())
                    st.success(f"📊 已將 {updated_count} 筆試算表連結更新為高性能 CDN 格式！")
                else:
                    st.info("試算表資料已是最新，無需更新。")

if __name__ == "__main__":
    repair_drive_and_sync_sheets()
