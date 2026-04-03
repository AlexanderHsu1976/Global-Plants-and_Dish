import pandas as pd
import sys
import os

sys.path.append(r"d:\SW Develop\Global_Plants")
from data_maintenance import save_image_physically

df = pd.read_csv("食用植物傳遞.csv")
fail_count = 0
for idx, row in df.iterrows():
    rep = str(row.get("代表照片", ""))
    if rep.startswith("http"):
        logs = []
        path = save_image_physically(rep, row['名稱'], 999, logs, folder="assets/plants")
        if not path:
            print(f"[{row['名稱']}] Failed. Logs:")
            for l in logs: print("  ", l)
            fail_count += 1
            if fail_count > 5: break
