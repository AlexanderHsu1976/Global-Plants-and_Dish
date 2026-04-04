import os
import json
import time
import pandas as pd
import sys
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# --- Config ---
# Ensure these scopes match your Google Cloud project settings
SCOPES = [
    'https://www.googleapis.com/auth/drive.file',
    'https://www.googleapis.com/auth/spreadsheets'
]
CLIENT_SECRET_FILE = 'OAuth.json'   # User's credential filename
TOKEN_FILE = 'token.json'
ROOT_FOLDER_ID = "1IvRyZtlRlDZSitoOw6b_HqnVoA4Qj0dw" # Main Folder ID
SPREADSHEET_NAME = "Global_Plants_DB"
PLANT_WS = "plant_master"
MENU_WS = "city_menus"

def get_authorized_services():
    """ Browser-based login to act as the user (using their 5TB quota) """
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CLIENT_SECRET_FILE):
                raise FileNotFoundError(f"❌ Missing {CLIENT_SECRET_FILE} in the project directory.")
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, 'w') as token:
            token.write(creds.to_json())

    drive_service = build('drive', 'v3', credentials=creds)
    return drive_service, creds

def get_or_create_subfolder(service, parent_id, folder_name):
    """ Find or create a subfolder in Google Drive """
    query = f"name = '{folder_name}' and '{parent_id}' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    results = service.files().list(q=query, fields="files(id)").execute()
    files = results.get('files', [])
    if files:
        return files[0]['id']
    
    print(f"  📁 Creating new cloud folder: {folder_name}...")
    file_metadata = {
        'name': folder_name,
        'parents': [parent_id],
        'mimeType': 'application/vnd.google-apps.folder'
    }
    folder = service.files().create(body=file_metadata, fields='id').execute()
    return folder.get('id')

def upload_file_to_drive(service, local_path, filename, target_folder_id, mimetype='image/jpeg'):
    """ Upload local file to Drive and set permission to public view """
    try:
        # Idempotency check: if it's already a URL, skip
        if str(local_path).startswith('http'):
            return local_path
            
        # Check if it exists locally
        if not os.path.exists(local_path):
            return None
            
        file_metadata = {'name': filename, 'parents': [target_folder_id]}
        media = MediaFileUpload(local_path, mimetype=mimetype, resumable=True)
        file = service.files().create(body=file_metadata, media_body=media, fields='id').execute()
        file_id = file.get('id')
        
        # Set permission to anyone with link can view (role MUST be 'reader')
        service.permissions().create(
            fileId=file_id, 
            body={'type': 'anyone', 'role': 'reader'}
        ).execute()
        
        # Return the direct download/view link
        return f"https://drive.google.com/uc?export=view&id={file_id}"
    except Exception as e:
        print(f"❌ Upload failed ({local_path}): {e}")
        return None

def update_google_sheet(creds, sheet_name, worksheet_name, df):
    """ 使用更穩健的方式同步回 Google Sheets """
    try:
        import gspread
        gc = gspread.authorize(creds)
        sh = gc.open(sheet_name)
        worksheet = sh.worksheet(worksheet_name)
        
        # 確保資料格式為純文字與列表
        data = [df.columns.values.tolist()] + df.fillna("").values.tolist()
        
        # 使用更現代的 update 方式，並指定範圍
        worksheet.clear()
        worksheet.update(data) # gspread v6.0+ 預設從 A1 開始
        
        print(f"✅ 雲端資料表 '{worksheet_name}' 已成功同步！")
    except Exception as e:
        # 如果發生錯誤，列印更多資訊
        print(f"❌ 同步 '{worksheet_name}' 時出錯。詳細資訊: {str(e)}")

def run_user_sync():
    print("🌟 啟動強化版同步程序 (Deep Sync 2.0)...")
    try:
        drive_service, creds = get_authorized_services()
    except Exception as e:
        print(f"登入失敗: {e}")
        return

    # --- 0. 初始化核心目錄 ---
    plants_fid = get_or_create_subfolder(drive_service, ROOT_FOLDER_ID, "plants")
    dishes_fid = get_or_create_subfolder(drive_service, ROOT_FOLDER_ID, "dishes")
    territories_fid = get_or_create_subfolder(drive_service, ROOT_FOLDER_ID, "territories")

    # --- 1. 同步地圖圖層 ---
    print("\n🌍 掃描地圖資料 ...")
    territory_dir = "data/territories"
    if os.path.exists(territory_dir):
        t_count = 0
        for f in os.listdir(territory_dir):
            if f.endswith(".json"):
                q = f"name = 'geo_{f}' and '{territories_fid}' in parents and trashed = false"
                if not drive_service.files().list(q=q).execute().get('files'):
                    print(f"  ⬆️ 補傳地圖: {f}")
                    upload_file_to_drive(drive_service, os.path.join(territory_dir,f), f"geo_{f}", territories_fid, 'application/json')
                    t_count += 1
        print(f"✅ 地圖同步檢查完畢 (新增 {t_count} 份)。")

    # --- 2. 同步植物考古 ---
    print("\n🌿 掃描植物考古資料 ...")
    plant_assets_dir = "assets/plants"
    if os.path.exists("plant_master_db.csv"):
        df = pd.read_csv("plant_master_db.csv")
        p_updated_count = 0
        all_plant_files = os.listdir(plant_assets_dir) if os.path.exists(plant_assets_dir) else []

        for idx, row in df.iterrows():
            name = row.get('名稱')
            if not name: continue
            
            try:
                raw_local = row.get('本地照片清單', '[]')
                if pd.isna(raw_local) or str(raw_local).strip() in ["", "[]"]: 
                    # 💡 重點：如果欄位是空的，主動從 assets/plants 找對應圖片
                    local_list = [os.path.join(plant_assets_dir, f) for f in all_plant_files if f.startswith(str(name))]
                else: 
                    processed_raw = str(raw_local).replace("'", '"')
                    local_list = json.loads(processed_raw)
            except: 
                local_list = []
            
            new_urls = []
            modified = False
            for p in local_list:
                if p and not str(p).startswith('http') and os.path.exists(p):
                    print(f"  ⬆️ 補傳植物圖片: {name} ({os.path.basename(p)})...")
                    url = upload_file_to_drive(drive_service, p, f"plant_{name}_{int(time.time()*1000)}.jpg", plants_fid)
                    if url: 
                        new_urls.append(url)
                        modified = True
                    else: new_urls.append(p)
                else: new_urls.append(p)
            
            if modified:
                df.at[idx, '本地照片清單'] = json.dumps(new_urls, ensure_ascii=False)
                if not str(row.get('代表照片', '')).startswith('http') and new_urls:
                    df.at[idx, '代表照片'] = new_urls[0]
                p_updated_count += 1
        
        if p_updated_count > 0:
            print(f"✨ 植物資料庫更新 {p_updated_count} 筆，同步至雲段中...")
            df.to_csv("plant_master_db.csv", index=False, encoding='utf-8-sig')
            update_google_sheet(creds, SPREADSHEET_NAME, PLANT_WS, df)
        else:
            print("✅ 所有植物圖片皆已是雲端網址，跳過上傳。")

    # --- 3. 同步菜標 ---
    print("\n🍽️ 掃描城市菜單資料 ...")
    dish_assets_dir = "assets/dishes"
    if os.path.exists("menu_db.json"):
        with open("menu_db.json", 'r', encoding='utf-8') as f:
            menu_db = json.load(f)
        m_updated_count = 0
        all_dish_files = os.listdir(dish_assets_dir) if os.path.exists(dish_assets_dir) else []

        for city_data in menu_db:
            city = city_data.get('city', 'Unknown')
            for dish in city_data.get('dishes', []):
                dish_name = dish.get('name')
                old_urls = dish.get('image_urls', [])
                
                # 💡 重點：如果欄位是空的或沒有網址，主動找 assets/dishes
                if not any(str(u).startswith('http') for u in old_urls):
                    # 優先從 assets 補齊
                    matched_files = [os.path.join(dish_assets_dir, f) for f in all_dish_files if f.startswith(str(dish_name))]
                    for mf in matched_files:
                        if mf not in old_urls: old_urls.append(mf)

                new_urls = []
                modified = False
                for u in old_urls:
                    if u and not str(u).startswith('http') and os.path.exists(str(u)):
                        print(f"  ⬆️ 補傳菜餚圖片: {city}-{dish_name}...")
                        url = upload_file_to_drive(drive_service, str(u), f"dish_{city}_{dish_name}_{int(time.time()*1000)}.jpg", dishes_fid)
                        if url:
                            new_urls.append(url)
                            modified = True
                        else: new_urls.append(u)
                    else: new_urls.append(u)
                
                if modified:
                    dish['image_urls'] = new_urls
                    m_updated_count += 1
        
        if m_updated_count > 0:
            print(f"✨ 菜單資料庫更新 {m_updated_count} 筆，同步至雲段中...")
            with open("menu_db.json", 'w', encoding='utf-8') as f:
                json.dump(menu_db, f, ensure_ascii=False, indent=2)
            # 轉換為 DF
            rows = []
            for city_data in menu_db:
                city, reg, cur_coord = city_data.get('city'), city_data.get('region'), city_data.get('coord', [0, 0])
                lat, lon = cur_coord[0], cur_coord[1]
                for d in city_data.get('dishes', []):
                    rows.append({
                        "City": city, "Region": reg, "Coord_Lat": lat, "Coord_Lon": lon,
                        "Dish_Name": d.get('name',''), "Dish_EN": d.get('name_en',''),
                        "Local_Name": d.get('local_name',''),
                        "Ingredients": json.dumps(d.get('ingredients',[]), ensure_ascii=False),
                        "Image_URLs": json.dumps(d.get('image_urls',[]), ensure_ascii=False),
                        "Description": d.get('description','')
                    })
            update_google_sheet(creds, SPREADSHEET_NAME, MENU_WS, pd.DataFrame(rows))
        else:
            print("✅ 所有菜餚圖片皆已是雲端網址，跳過上傳。")


    print("\n✨ 同步任務完整結束！")

if __name__ == "__main__":
    run_user_sync()

