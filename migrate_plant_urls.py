import pandas as pd
import json
import time
import sys
import os
import io

# Load existing environment
sys.path.append(r"d:\SW Develop\Global_Plants")
from data_maintenance import save_image_physically, _MASTER_DB_FILE, load_csv_robust

def run_migration():
    print("啟動【植物圖片本地化轉換腳本】...")
    df = load_csv_robust(_MASTER_DB_FILE)
    changes_made = 0
    total_added = 0
    
    for idx, row in df.iterrows():
        name_zh = str(row['名稱']).strip()
        rep_photo = str(row.get('代表照片', '')).strip()
        raw_local = str(row.get('本地照片清單', '[]')).strip()
        
        # Parse existing list safely
        try:
            if pd.isna(raw_local) or raw_local in ('nan', 'None', ''):
                local_paths = []
            else:
                raw_local = raw_local.replace("'", '"') # Fix single quotes issues occasionally
                local_paths = json.loads(raw_local)
        except Exception:
            local_paths = []
            
        modified = False
        new_local_paths = []
        
        # 1. Check if any existing entry inside local_paths is an HTTP URL!
        for p in local_paths:
            if str(p).startswith('http'):
                print(f"[{name_zh}] 發現舊版 URL 位於歷史陣列中: {p[:30]}...")
                logs = []
                idx_seed = int(time.time() * 1000)
                path = save_image_physically(p, name_zh, idx_seed, logs, folder="assets/plants")
                if path:
                    new_local_paths.append(path)
                    print(f"  -> ✅ 下載成功: {path}")
                    total_added += 1
                else:
                    print(f"  -> ❌ 下載失敗")
                modified = True
            else:
                new_local_paths.append(p)
                
        # 2. Check 代表照片
        if rep_photo.startswith('http') and len(new_local_paths) < 3:
            # Maybe rep_photo has multiple urls? Usually it's just one string
            print(f"[{name_zh}] 發現 代表照片 URL: {rep_photo[:30]}...")
            logs = []
            idx_seed = int(time.time() * 1000)
            path = save_image_physically(rep_photo, name_zh, idx_seed, logs, folder="assets/plants")
            if path:
                new_local_paths.append(path)
                print(f"  -> ✅ 下載成功: {path}")
                total_added += 1
                
                # Clear representative photo as it's been localized now! (Or we can keep it as historical reference)
                # We'll leave the original string for safety but use the local path for the UI.
            else:
                print(f"  -> ❌ 下載失敗")
            modified = True
            
        if modified:
            df.at[idx, '本地照片清單'] = json.dumps(new_local_paths, ensure_ascii=False)
            changes_made += 1
            
    if changes_made > 0:
        print(f"\n✅ 轉換完畢！總共下載了 {total_added} 張圖片。正在強制刷新 {changes_made} 筆資料...")
        df.to_csv(_MASTER_DB_FILE, index=False, encoding='utf-8-sig')
        df.to_csv("食用植物傳遞.csv", index=False, encoding='utf-8-sig')
        print("💾 資料庫已成功覆寫儲存。")
    else:
        print("沒有發現需要轉換的網址，不需覆寫檔案。")

if __name__ == '__main__':
    run_migration()
