import os
import pandas as pd
import requests
import json
import time
import io
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
import gspread

# --- 配置區 ---
SCOPES = [
    'https://www.googleapis.com/auth/drive.file',
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]
SPREADSHEET_NAME = "Global_Plants_DB"
PLANT_WS = "plant_master"
ROOT_FOLDER_ID = "1IvRyZtlRlDZSitoOw6b_HqnVoA4Qj0dw" # 您的主資料夾 ID

def get_authorized_services():
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('OAuth.json', SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
    
    drive_service = build('drive', 'v3', credentials=creds)
    return drive_service, creds

def get_or_create_subfolder(service, parent_id, folder_name):
    query = f"name = '{folder_name}' and '{parent_id}' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    results = service.files().list(q=query).execute().get('files', [])
    if results:
        return results[0]['id']
    file_metadata = {'name': folder_name, 'mimeType': 'application/vnd.google-apps.folder', 'parents': [parent_id]}
    folder = service.files().create(body=file_metadata, fields='id').execute()
    return folder.get('id')

def download_and_upload(service, image_url, name, folder_id):
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        resp = requests.get(image_url, headers=headers, timeout=15)
        if resp.status_code != 200: return None
        
        image_data = io.BytesIO(resp.content)
        file_metadata = {'name': f"backup_wiki_{name}_{int(time.time())}.jpg", 'parents': [folder_id]}
        media = MediaIoBaseUpload(image_data, mimetype='image/jpeg', resumable=True)
        
        file = service.files().create(body=file_metadata, media_body=media, fields='id').execute()
        file_id = file.get('id')
        
        service.permissions().create(fileId=file_id, body={'type': 'anyone', 'role': 'reader'}).execute()
        return f"https://drive.google.com/uc?export=view&id={file_id}"
    except Exception as e:
        print(f"  ❌ 下載/上傳失敗: {e}")
        return None

def run_migration():
    print("🚀 啟動 Wikipedia 圖片備援遷移計畫...")
    drive_service, creds = get_authorized_services()
    plants_fid = get_or_create_subfolder(drive_service, ROOT_FOLDER_ID, "plants")
    
    if not os.path.exists("plant_master_db.csv"):
        print("找不到 plant_master_db.csv")
        return
    
    df = pd.read_csv("plant_master_db.csv")
    updated_count = 0
    
    for idx, row in df.iterrows():
        name = row.get('名稱', 'Unknown')
        wiki_img_url = row.get('代表照片', '')
        
        # 只處理來自 wikipedia/wikimedia 的連結
        if str(wiki_img_url).startswith('http') and ('wiki' in str(wiki_img_url).lower()):
            # 檢查是否已經備份過 (看清單裡有沒有這個 Drive 網址)
            current_list_str = str(row.get('本地照片清單', '[]')).replace("'", '"')
            try:
                current_list = json.loads(current_list_str) if current_list_str != 'nan' else []
            except: current_list = []
            
            # 如果清單裡還沒有 Drive 網址，或者只有原本的 wiki 網址
            has_backup = any('drive.google.com' in str(u) for u in current_list)
            
            if not has_backup:
                print(f"📦 正在遷移: {name} 的 Wikipedia 圖片...")
                new_drive_url = download_and_upload(drive_service, wiki_img_url, name, plants_fid)
                
                if new_drive_url:
                    # 更新清單：將備份圖放在第一位
                    if wiki_img_url not in current_list:
                        current_list.append(wiki_img_url) # 保留原始來源
                    
                    # 插入 Drive 網址到首位
                    if new_drive_url not in current_list:
                        current_list.insert(0, new_drive_url)
                    
                    df.at[idx, '本地照片清單'] = json.dumps(current_list, ensure_ascii=False)
                    updated_count += 1
                    
                    # 每次更新完存檔一次，預防中斷
                    if updated_count % 5 == 0:
                        df.to_csv("plant_master_db.csv", index=False, encoding='utf-8-sig')
    
    if updated_count > 0:
        df.to_csv("plant_master_db.csv", index=False, encoding='utf-8-sig')
        print(f"✨ 成功遷移 {updated_count} 張圖片至雲端備份！正在同步 Google Sheets...")
        try:
            gc = gspread.authorize(creds)
            sh = gc.open(SPREADSHEET_NAME)
            ws = sh.worksheet(PLANT_WS)
            ws.clear()
            ws.update([df.columns.values.tolist()] + df.fillna("").values.tolist())
            print("✅ Google Sheets 同步完成。")
        except Exception as e:
            print(f"❌ Sheets 同步失敗: {e}")
    else:
        print("✅ 沒有需要遷移的 Wikipedia 圖片。")

if __name__ == "__main__":
    run_migration()
