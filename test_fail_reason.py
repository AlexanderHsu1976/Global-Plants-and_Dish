import pandas as pd
from PIL import Image
import requests
import io
import sys

sys.path.append(r"d:\SW Develop\Global_Plants")

df = pd.read_csv("食用植物傳遞.csv")
failed_count = 0
for idx, row in df.iterrows():
    rep = str(row.get("代表照片", ""))
    if rep.startswith("http"):
        try:
            res = requests.get(rep, timeout=3)
            img = Image.open(io.BytesIO(res.content))
            w, h = img.size
            if w < 250 or h < 250:
                print(f"[FAIL] {row['名稱']} size too small: {w}x{h}")
                failed_count += 1
        except Exception as e:
            print(f"[FAIL] {row['名稱']} error: {e}")
            failed_count += 1
print(f"Total failed: {failed_count}")
