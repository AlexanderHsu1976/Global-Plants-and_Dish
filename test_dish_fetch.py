import sys
import os
sys.path.append(r"d:\SW Develop\Global_Plants")
from data_maintenance import fetch_dish_candidates_tri_track

with open("test_dish.log", "w", encoding='utf-8') as f:
    f.write("=== 測試 1：牛肉麵 ===\n")
    res1, logs1 = fetch_dish_candidates_tri_track("牛肉麵", "Beef Noodle Soup", "牛肉麵", count=3)
    for l in logs1:
        f.write(str(l) + "\n")
    f.write("結果: " + str(res1) + "\n")

    f.write("\n=== 測試 2：地瓜球 ===\n")
    res2, logs2 = fetch_dish_candidates_tri_track("地瓜球", "Fried Sweet Potato Balls", "地瓜球", count=3)
    for l in logs2:
        f.write(str(l) + "\n")
    f.write("結果: " + str(res2) + "\n")
