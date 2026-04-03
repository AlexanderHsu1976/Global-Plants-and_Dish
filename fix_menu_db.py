import json

PLACEHOLDER_MARKERS = ["placeholder.com", "via.placeholder", "thumb.php?f=", "commons.wikimedia.org/wiki"]

with open('menu_db.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

for city in data:
    for dish in city.get('dishes', []):
        # 過濾掉所有破碎的 URL (empty, placeholder, malformed)
        old_urls = dish.get('image_urls', [])
        clean_urls = []
        for u in old_urls:
            if not u or not isinstance(u, str): continue
            if any(bad in u for bad in PLACEHOLDER_MARKERS): continue
            if not u.startswith('http'): continue
            # 長度合理的 URL 才保留
            if len(u) > 20:
                clean_urls.append(u)
        dish['image_urls'] = clean_urls
        # 移除舊欄位
        dish.pop('image_url', None)

with open('menu_db.json', 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print("=== 清理結果 ===")
for city in data:
    print(f"城市: {city['city']}")
    for dish in city.get('dishes', []):
        print(f"  菜色: {dish['name']} | 有效圖片: {len(dish.get('image_urls', []))}")
