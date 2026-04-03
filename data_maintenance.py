import streamlit as st
import pandas as pd
import re
import os
import io
import json
import requests
import time
import chardet
from PIL import Image
from io import BytesIO
from urllib.parse import quote
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

# --- [Module 0] SDK Compatibility Handling ---
try:
    import google.generativeai as genai
    SDK_VERSION = "legacy" # google-generativeai
except ImportError:
    try:
        from google import genai
        SDK_VERSION = "new" # google-genai
    except ImportError:
        genai = None
        SDK_VERSION = None

# --- [Module 0.1] Infrastructure (GSheets Cloud Connector) ---

def get_gsheet_client():
    """ 
    建立 Google Sheets 連線，優先讀取 Streamlit Secrets (雲端)，
    其次讀取本地 credentials.json。
    """
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    try:
        if "gcp_service_account" in st.secrets:
            info = dict(st.secrets["gcp_service_account"])
            creds = Credentials.from_service_account_info(info, scopes=scopes)
            return gspread.authorize(creds)
        if os.path.exists("credentials.json"):
            creds = Credentials.from_service_account_file("credentials.json", scopes=scopes)
            return gspread.authorize(creds)
    except Exception as e:
        st.error(f"❌ Google Sheets 授權失敗: {e}")
    return None

def get_drive_service():
    """ 建立 Google Drive 服務 """
    try:
        if "gcp_service_account" in st.secrets:
            info = dict(st.secrets["gcp_service_account"])
            creds = Credentials.from_service_account_info(info, scopes=[
                "https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/drive"
            ])
            return build('drive', 'v3', credentials=creds)
        if os.path.exists("credentials.json"):
            creds = Credentials.from_service_account_file("credentials.json", scopes=[
                "https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/drive"
            ])
            return build('drive', 'v3', credentials=creds)
    except Exception as e:
        st.error(f"❌ Google Drive 服務啟動失敗: {e}")
    return None

def upload_to_drive(image_url, filename):
    """ 下載圖片並上傳至 Google Drive，回傳直連網址 """
    folder_id = "1IvRyZtlRlDZSitoOw6b_HqnVoA4Qj0dw"
    service = get_drive_service()
    if not service: return None
    try:
        resp = requests.get(image_url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        if resp.status_code != 200: return None
        
        image_data = io.BytesIO(resp.content)
        file_metadata = {'name': filename, 'parents': [folder_id]}
        media = MediaIoBaseUpload(image_data, mimetype='image/jpeg', resumable=True)
        
        file = service.files().create(body=file_metadata, media_body=media, fields='id').execute()
        file_id = file.get('id')
        
        # 設定權限為公開檢視 (Anyone with the link can view)
        service.permissions().create(
            fileId=file_id,
            body={'type': 'anyone', 'role': 'viewer'}
        ).execute()
        
        # 回傳直連連結
        return f"https://drive.google.com/uc?export=view&id={file_id}"
    except Exception as e:
        st.error(f"❌ 上傳 Drive 失敗: {e}")
        return None

def load_gsheet_as_df(sheet_name, worksheet_name):
    """ 雲端化資料讀取接口 """
    try:
        client = get_gsheet_client()
        if not client: return pd.DataFrame()
        sh = client.open(sheet_name)
        worksheet = sh.worksheet(worksheet_name)
        return pd.DataFrame(worksheet.get_all_records())
    except Exception as e:
        st.error(f"❌ 讀取 {worksheet_name} 失敗: {e}")
        return pd.DataFrame()

def update_gsheet_from_df(sheet_name, worksheet_name, df):
    """ 雲端化資料同步接口 """
    try:
        client = get_gsheet_client()
        if not client: return
        sh = client.open(sheet_name)
        worksheet = sh.worksheet(worksheet_name)
        worksheet.clear()
        worksheet.update([df.columns.values.tolist()] + df.values.tolist())
        st.toast(f"✅ {worksheet_name} 已完成同步")
    except Exception as e:
        st.error(f"❌ 同步 {worksheet_name} 失敗: {e}")

# --- [Module 1] Security & API Config ---

def unified_gemini_response(prompt, is_json=False):
    model_name = st.session_state.get('selected_model', "gemini-flash-latest")
    api_key = st.session_state.get('saved_api_key')
    config = {"response_mime_type": "application/json"} if is_json else None
    try:
        if SDK_VERSION == "legacy":
            model = genai.GenerativeModel(model_name)
            resp = model.generate_content(prompt, generation_config=config)
            return resp.text
        elif SDK_VERSION == "new":
            client = genai.Client(api_key=api_key)
            resp = client.models.generate_content(model=model_name, contents=prompt, config={'response_mime_type': 'application/json'} if is_json else None)
            return resp.text
    except Exception as e:
        raise Exception(f"AI 呼叫失敗: {str(e)}")
    return ""

def verify_access_and_init_api():
    if 'authenticated' not in st.session_state: st.session_state.authenticated = False
    if 'api_active' not in st.session_state: st.session_state.api_active = False
    if not st.session_state.authenticated:
        st.title("🔒 系統存取驗證")
        pin = st.text_input("管理員 PIN 碼", type="password")
        if st.button("驗證並進入"):
            if pin in ["admin123", "1234"]: 
                st.session_state.authenticated = True
                st.rerun()
            else: st.error("❌ PIN 碼錯誤")
        st.stop()
    
    st.sidebar.title("🛠️ 系統配置")
    api_key_input = st.sidebar.text_input("Gemini API Key", type="password", value=st.session_state.get('saved_api_key', ""))
    if api_key_input and (api_key_input != st.session_state.get('saved_api_key') or not st.session_state.api_active):
        try:
            clean_key = "".join(api_key_input.split())
            if SDK_VERSION == "legacy": genai.configure(api_key=clean_key)
            st.session_state.api_active = True
            st.session_state.saved_api_key = clean_key
        except: st.session_state.api_active = False

def master_ai_survey_agent(target_plant, df):
    """
    透過 Gemini AI 針對特定植物進行深度考古與地理調研。
    """
    if not st.session_state.get('api_active'):
        st.error("❌ API 未啟動")
        return
    
    prompt = f"""
    你是全球植物傳播考古專家。請針對 '{target_plant}' 進行深度調研。
    輸出應包含以下 JSON 格式：
    {{
        "學名": "...",
        "科": "...",
        "起源地": "...",
        "傳播歷史": "約 150 字的考據內容",
        "特點": "特殊用途或效用"
    }}
    請確保內容學術準確。
    """
    try:
        resp_text = unified_gemini_response(prompt, is_json=True)
        data = json.loads(resp_text)
        
        # 更新 DataFrame
        idx = df[df['名稱'] == target_plant].index
        if not idx.empty:
            i = idx[0]
            df.at[i, '學名'] = data.get('學名', df.at[i, '學名'])
            df.at[i, '科'] = data.get('科', df.at[i, '科'])
            df.at[i, '起源地'] = data.get('起源地', df.at[i, '起源地'])
            df.at[i, '傳播歷史(考據)'] = data.get('傳播歷史', df.at[i, '傳播歷史(考據)'])
            df.at[i, '特殊效用'] = data.get('特點', df.at[i, '特殊效用'])
            st.success(f"✅ {target_plant} 調研完成並寫入暫存")
        else:
            st.warning("找不到該物種，無法更新")
    except Exception as e:
        st.error(f"調研失敗: {e}")

# --- [Module 2] Data Core (Cloud Refactoring) ---

_SPREADSHEET_NAME = "Global_Plants_DB"
_PLANT_WS = "plant_master"
_MENU_WS = "city_menus"

MASTER_COLUMNS = [
    "選擇", "ID", "名稱", "英文名稱", "學名", "科", "英文科名", "起源地", 
    "傳遞路徑", "傳播歷史(考據)", "傳播地理(階段)", "多重路徑資料", 
    "調研摘要", "維基連結", "代表照片", "本地照片清單", "特殊用途", "使用禁忌", 
    "特殊效用", "核實狀態", "建議"
]

def load_master_db():
    df = load_gsheet_as_df(_SPREADSHEET_NAME, _PLANT_WS)
    if df.empty and os.path.exists("plant_master_db.csv"):
        df = pd.read_csv("plant_master_db.csv")
    return map_csv_to_master(df)

def save_master_db(df):
    update_gsheet_from_df(_SPREADSHEET_NAME, _PLANT_WS, df)
    df.to_csv("plant_master_db.csv", index=False, encoding='utf-8-sig')

def load_menu_db():
    df = load_gsheet_as_df(_SPREADSHEET_NAME, _MENU_WS)
    if df.empty or 'City' not in df.columns:
        if os.path.exists("menu_db.json"):
            with open("menu_db.json", 'r', encoding='utf-8') as f: return json.load(f)
        return []
    
    menu_db = []
    # 確保欄位存在，若不存在則補空值避免 groupby 報錯
    for col in ['City', 'Region', 'Coord_Lat', 'Coord_Lon']:
        if col not in df.columns: df[col] = ""
        
    grouped = df.groupby(['City', 'Region'])
    for (city, region), group in grouped:
        city_data = {
            "city": city,
            "region": region,
            "coord": [float(group.iloc[0].get('Coord_Lat', 0)), float(group.iloc[0].get('Coord_Lon', 0))],
            "dishes": []
        }
        for _, row in group.iterrows():
            def parse_nested(val):
                try:
                    if isinstance(val, str) and val.strip().startswith('['): return json.loads(val)
                    if isinstance(val, str): return [s.strip() for s in val.split(',') if s.strip()]
                    return []
                except: return []
            dish = {
                "name": row.get('Dish_Name', ''),
                "name_en": row.get('Dish_EN', ''),
                "local_name": row.get('Local_Name', ''),
                "ingredients": parse_nested(row.get('Ingredients', '[]')),
                "image_urls": parse_nested(row.get('Image_URLs', '[]')),
                "description": row.get('Description', '')
            }
            city_data['dishes'].append(dish)
        menu_db.append(city_data)
    return menu_db

def save_menu_db(menu_db):
    rows = []
    for city_data in menu_db:
        city, region = city_data.get('city', ''), city_data.get('region', '')
        lat, lon = city_data.get('coord', [0, 0])
        for dish in city_data.get('dishes', []):
            rows.append({
                "City": city, "Region": region, "Coord_Lat": lat, "Coord_Lon": lon,
                "Dish_Name": dish.get('name', ''), "Dish_EN": dish.get('name_en', ''),
                "Local_Name": dish.get('local_name', ''),
                "Ingredients": json.dumps(dish.get('ingredients', []), ensure_ascii=False),
                "Image_URLs": json.dumps(dish.get('image_urls', []), ensure_ascii=False),
                "Description": dish.get('description', '')
            })
    df = pd.DataFrame(rows)
    update_gsheet_from_df(_SPREADSHEET_NAME, _MENU_WS, df)
    with open("menu_db.json", 'w', encoding='utf-8') as f:
        json.dump(menu_db, f, ensure_ascii=False, indent=2)

def map_csv_to_master(df):
    for col in MASTER_COLUMNS:
        if col not in df.columns: df[col] = ""
    return df.fillna("")

# --- [Module 3] Ironclad AI Image Engine (Ollama System) ---

def is_valid_image(url):
    url_low = str(url).lower()
    if not url_low.endswith(('.jpg', '.jpeg', '.png', '.webp')): return False
    if any(bad in url_low for bad in ["pdf", "svg", "logo", "icon", "placeholder"]): return False
    return True

def fetch_dish_candidates_tri_track(dish_zh, dish_en, dish_local, count=3):
    import ollama
    log_steps = []
    results = []
    try:
        prompt = f"The dish is '{dish_zh}' ({dish_en}). Generate 3 SEO image search queries. JSON list only."
        res = ollama.chat(model='llama3.2', messages=[{'role': 'user', 'content': prompt}])
        match = re.search(r'\[.*\]', res['message']['content'], re.DOTALL)
        queries = json.loads(match.group()) if match else [f"{dish_en} food photography"]
    except: queries = [f"{dish_en} authentic dish"]
    
    candidates = optimized_image_search(queries, log_steps)
    candidates = [c for c in candidates if is_valid_image(c['url'])][:15]
    
    # Simple top-N for brevity in this refactor, while keeping structure
    for c in candidates:
        if c['url'] not in results:
            results.append(c['url'])
            if len(results) >= count: break
    return results, log_steps

def fetch_plant_representative_image(name_zh, name_en, name_latin):
    """ 
    針對物種搜尋一張最佳照片並存入 Drive 
    """
    log_steps = []
    queries = [f"{name_latin} plant photography", f"{name_zh} 代表照片"]
    candidates = optimized_image_search(queries, log_steps)
    if not candidates: return None, log_steps
    
    # 這裡可以加入 Ollama 篩選邏輯，目前採優先策略
    for cand in candidates[:5]:
        filename = f"plant_{name_latin}_{int(time.time())}.jpg"
        drive_url = upload_to_drive(cand['url'], filename)
        if drive_url: return drive_url, log_steps
    return None, log_steps

def optimized_image_search(keywords, log_steps):
    from duckduckgo_search import DDGS
    all_results = []
    try:
        with DDGS() as ddgs:
            for q in keywords:
                try:
                    res = list(ddgs.images(q, max_results=8))
                    for img in res:
                        u = img.get("image") or img.get("thumbnail")
                        if u and is_valid_image(u):
                            all_results.append({"title": img.get("title", ""), "url": u})
                except: continue
    except: pass
    return all_results

def save_image_physically(url, item_name, index, log_steps, folder="assets/dishes"):
    try:
        resp = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        img = Image.open(BytesIO(resp.content)).convert("RGB")
        if min(img.size) < 200: return None
        os.makedirs(folder, exist_ok=True)
        safe_name = re.sub(r'[^\w\s-]', '', item_name).strip().replace(' ', '_')
        path = f"{folder}/{safe_name}_{index}.jpg"
        img.save(path, "JPEG", quality=85)
        return path
    except: return None

def fetch_dish_image(dish):
    """ 
    【相容性助手】供 app.py 舊版邏輯調用，優先回傳本地資產。
    """
    local_paths = dish.get('image_urls', [])
    if local_paths: return local_paths[0]
    return dish.get('image_url', "")

# --- [Module 4] UI Components ---

def render_dish_image_management(dish, sel_city, city_data, menu_db, dish_idx):
    dish_zh = dish['name']
    u_key = f"{dish_zh}_{dish_idx}"
    local_paths = [p for p in dish.get("image_urls", []) if p and os.path.exists(p)]
    
    with st.container(border=True):
        st.write(f"### 🍽️ {dish_zh}")
        c_i1, c_i2, c_i3 = st.columns(3)
        cols = [c_i1, c_i2, c_i3]
        
        # 顯示最多 3 張圖片
        for i in range(3):
            with cols[i]:
                if i < len(local_paths):
                    st.image(local_paths[i], use_container_width=True)
                    if st.button("🗑️", key=f"del_{u_key}_{i}"):
                        local_paths.pop(i)
                        dish["image_urls"] = local_paths
                        save_menu_db(menu_db)
                        st.rerun()
                else:
                    st.info(f"候選位 {i+1}")
        
        st.divider()
        c_ctrl1, c_ctrl2 = st.columns([2, 1])
        with c_ctrl1:
            dish['name'] = st.text_input("菜名", dish.get('name',''), key=f"nm_{u_key}")
            dish['name_en'] = st.text_input("英文名", dish.get('name_en',''), key=f"en_{u_key}")
            # 食材清單
            ing_str = ", ".join(dish.get('ingredients', []))
            new_ing = st.text_area("食材 (以逗號分隔)", ing_str, key=f"ing_{u_key}")
            dish['ingredients'] = [s.strip() for s in new_ing.split(',') if s.strip()]
        
        with c_ctrl2:
            st.write("🔧 工具")
            if st.button("✨ AI 補位", key=f"ai_{u_key}"):
                with st.spinner("AI 尋圖中..."):
                    cands, logs = fetch_dish_candidates_tri_track(dish_zh, dish.get('name_en',''), dish.get('local_name',''))
                    for u in cands:
                        p = save_image_physically(u, dish_zh, int(time.time()), logs)
                        if p: local_paths.append(p)
                        if len(local_paths) >= 3: break
                    dish["image_urls"] = local_paths[:3]
                    save_menu_db(menu_db)
                    st.rerun()
            
            if st.button("💾 儲存修改", key=f"sv_{u_key}"):
                save_menu_db(menu_db)
                st.success("已即時同步至雲端")
            
            if st.button("❌ 刪除此菜餚", key=f"rm_{u_key}"):
                city_data['dishes'].pop(dish_idx)
                save_menu_db(menu_db)
                st.rerun()

def render_page_3():
    verify_access_and_init_api()
    st.title("🌐 全球植物雲端維護中心")
    if 'plant_db' not in st.session_state: st.session_state.plant_db = load_master_db()
    
    tab1, tab2, tab3 = st.tabs(["📊 植物考古", "🥗 城市菜單", "🧩 UGC 審核"])
    
    with tab1:
        st.subheader("Google Sheet: plant_master")
        edited_df = st.data_editor(st.session_state.plant_db, num_rows="dynamic", use_container_width=True)
        if st.button("💾 同步至雲端"):
            st.session_state.plant_db = edited_df
            save_master_db(edited_df)
            st.success("植物大表同步完成")
            
        st.divider()
        st.subheader("🔬 深度考古工具箱")
        col_t1, col_t2 = st.columns([1, 2])
        with col_t1:
            target = st.selectbox("選擇調研目標", st.session_state.plant_db['名稱'].unique())
            if st.button("🚀 啟動 AI 調研"):
                with st.spinner(f"正在挖掘 {target} 的歷史..."):
                    master_ai_survey_agent(target, st.session_state.plant_db)
        with col_t2:
            st.info("AI 將針對選定物種進行學名、科別、起源地與歷史內容的自動補完。")
            if st.button("🖼️ 補全代表照片 (Drive)"):
                with st.spinner(f"正在為 {target} 尋找並保存照片..."):
                    idx = st.session_state.plant_db[st.session_state.plant_db['名稱'] == target].index[0]
                    row = st.session_state.plant_db.loc[idx]
                    img_url, logs = fetch_plant_representative_image(target, row.get('英文名稱',''), row.get('學名',''))
                    if img_url:
                        st.session_state.plant_db.at[idx, '代表照片'] = img_url
                        st.image(img_url, caption="新上傳的照片 (Google Drive)")
                        st.success("照片已保存至 Drive 並更新暫存")
                    else: st.error("照片補完失敗")
            
    with tab2:
        st.subheader("Google Sheet: city_menus")
        menu_db = load_menu_db()
        
        c_list, c_new = st.columns([2, 1])
        with c_new:
            with st.expander("🏙️ 新增城市", expanded=False):
                nc_name = st.text_input("城市名稱")
                nc_reg = st.text_input("區域/文明")
                nc_lat = st.number_input("緯度", value=0.0)
                nc_lon = st.number_input("經度", value=0.0)
                if st.button("➕ 建立城市"):
                    menu_db.append({"city": nc_name, "region": nc_reg, "coord": [nc_lat, nc_lon], "dishes": []})
                    save_menu_db(menu_db)
                    st.rerun()
        
        with c_list:
            if menu_db:
                cities = [f"{m['city']} ({m['region']})" for m in menu_db]
                sel_idx = st.selectbox("選擇城市", range(len(cities)), format_func=lambda i: cities[i])
                city_data = menu_db[sel_idx]
                
                st.write(f"#### 🚩 當前選中：{city_data['city']}")
                if st.button("🥗 新增菜單項目"):
                    city_data['dishes'].insert(0, {"name": "新菜名", "name_en": "", "ingredients": [], "image_urls": []})
                    save_menu_db(menu_db)
                    st.rerun()

                for i, dish in enumerate(city_data['dishes']):
                    render_dish_image_management(dish, city_data['city'], city_data, menu_db, i)
            else: st.info("尚無菜單資料")

    with tab3:
        st.subheader("🧩 UGC 預留插槽")
        st.write("此處顯示來自 ugc_submissions 的新投稿。")
        ugc_df = load_gsheet_as_df(_SPREADSHEET_NAME, "ugc_submissions")
        if not ugc_df.empty: st.dataframe(ugc_df)
        else: st.info("無待審核投稿")
