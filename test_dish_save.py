import sys
sys.path.append(r"d:\SW Develop\Global_Plants")
from data_maintenance import save_image_physically
logs = []
url = "https://upload.wikimedia.org/wikipedia/commons/7/7f/Food_%E7%B4%85%E7%87%92%E7%89%9B%E8%82%89%E9%BA%B5%2C_%E8%80%81%E5%A4%96%E4%B8%80%E5%93%81%E7%89%9B%E8%82%89%E9%BA%B5%2C_%E5%8F%B0%E5%8C%97_%2815177945972%29.jpg"
res = save_image_physically(url, "牛肉麵", 999, logs)
print("SAVE RES:", res)
for l in logs:
    print("LOG:", l)
