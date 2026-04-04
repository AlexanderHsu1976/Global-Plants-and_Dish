code_content = r'''import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
from folium.plugins import AntPath
import os
import json
import math
import random
from data_maintenance import render_page_3, MASTER_COLUMNS, load_master_db, load_menu_db
from ui_components import render_player_card

# --- [Module 0] Infrastructure & Helpers ---

def interpolate_curved_path(p1, p2, segments=20):
    lat1, lon1 = p1
    lat2, lon2 = p2
    mid_lat, mid_lon = (lat1 + lat2) / 2, (lon1 + lon2) / 2
    dist = ((lat1 - lat2)**2 + (lon1 - lon2)**2)**0.5
    offset = dist * 0.15
    dx, dy = lat2 - lat1, lon2 - lon1
    length = (dx**2 + dy**2)**0.5
    if length > 0:
        ctrl_lat = mid_lat + (dy / length) * offset
        ctrl_lon = mid_lon - (dx / length) * offset
    else:
        ctrl_lat, ctrl_lon = mid_lat, mid_lon
    points = []
    for t in [i/segments for i in range(segments + 1)]:
        b_lat = (1-t)**2 * lat1 + 2*(1-t)*t * ctrl_lat + t**2 * lat2
        b_lon = (1-t)**2 * lon1 + 2*(1-t)*t * ctrl_lon + t**2 * lon2
        points.append((b_lat, b_lon))
    return points

def haversine(p1, p2):
    lat1, lon1 = p1
    lat2, lon2 = p2
    R = 6371.0
    dlat, dlon = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

def get_plant_arrival_year(city_coord, plant_name, plant_db):
    if plant_db is None or plant_db.empty: return 99999
    match = plant_db[plant_db['名稱'].astype(str).str.strip() == plant_name.strip()]
    if match.empty: return 99999
    try: 
        raw_data = match.iloc[0].get('多重路徑資料', '[]')
        routes = json.loads(str(raw_data).replace("'", '"'))
    except: return 99999
    
    earliest = 99999
    BUFFER = 1000 
    for route in routes:
        nodes = route.get('nodes', [])
        for n in nodes:
            lat, lon = (n.get('coord', [0,0]))[:2]
            if haversine(city_coord, (lat, lon)) <= BUFFER:
                earliest = min(earliest, int(n.get('year', 0)))
    return earliest

def load_historical_boundary(year):
    available_years = [117, 300, 500, 800, 1000, 1300, 1492, 1600, 1914, 1945]
    if year < 0: return None
    target_year = 117
    for y in available_years:
        if y <= year: target_year = y
    file_path = f"data/territories/{target_year}.json"
    if os.path.exists(file_path):
        with open(file_path, 'r', encoding='utf-8') as f: return json.load(f)
    return None

def safe_render_image(image_source, default_caption="", use_container_width=True):
    """
    安全選染影像：處理雲端環境中路徑遺失的問題。
    """
    final_source = "https://via.placeholder.com/600x400?text=Syncing+Asset+to+Cloud"
    
    if not image_source or str(image_source) in ["nan", "0", "None", "[]", ""]:
        st.image(final_source, use_container_width=use_container_width, caption="無照片資料")
        return

    clean_url = str(image_source).strip()
    
    if "drive.google.com/uc" in clean_url or "id=" in clean_url:
        import re
        m = re.search(r"id=([\w-]+)", clean_url)
        if m: clean_url = f"https://lh3.googleusercontent.com/d/{m.group(1)}"

    if clean_url.startswith("http"):
        final_source = clean_url
    elif os.path.exists(clean_url):
        final_source = clean_url
    else:
        final_source = "https://via.placeholder.com/600x400?text=Local+Photo+Not+Available+on+Cloud"

    try:
        st.image(final_source, use_container_width=use_container_width, caption=default_caption)
    except:
        st.warning("⚠️ 此影像連結無效")

# --- 🚀 App Initialization ---

st.set_page_config(page_title="Global Plants Path Visualizer", layout="wide")

if 'plant_db' not in st.session_state:
    with st.spinner("🚀 正在同步雲端資料中..."):
        st.session_state.plant_db = load_master_db()
        st.session_state.menu_db = load_menu_db()
        if st.session_state.plant_db is not None and not st.session_state.plant_db.empty:
            df_temp = st.session_state.plant_db.copy()
            if "名稱" in df_temp.columns: df_temp["Name"] = df_temp["名稱"]
            if "科" in df_temp.columns: df_temp["Category"] = df_temp["科"]
            st.session_state.df = df_temp
        else:
            st.session_state.df = pd.DataFrame()

# Sidebar Navigation
st.sidebar.title("🌿 Global Plants")
nav_options = ["Static Mapping", "Timeline Simulation", "Time VS Menu Challenge", "Community Contribution"]
if st.query_params.get("mode") == "admin_access":
    nav_options.append("Data & Menu Administration")

page = st.sidebar.radio("Navigation", nav_options)

# --- 📍 Page 1: Static Mapping ---

if page == "Static Mapping":
    st.title("Static Mapping (Path View)")
    df = st.session_state.get('df', pd.DataFrame())
    
    if df.empty:
        st.warning("⚠️ 雲端資料庫同步中...")
    else:
        st.markdown("### 🌿 物種軌跡檢索 (Species Path Finder)")
        col_c, col_p = st.columns([1, 2])
        categories = ["所有科別"] + sorted(df['Category'].dropna().unique().tolist())
        with col_c: selected_cat = st.selectbox("📌 類別過濾", categories)
        with col_p:
            filtered_df = df if selected_cat == "所有科別" else df[df['Category'] == selected_cat]
            plant_names = sorted(filtered_df['Name'].unique().tolist())
            selected_plant = st.selectbox("🌱 選擇目標物種", plant_names)
        
        st.divider()
        db_row = df[df['Name'] == selected_plant].iloc[0]
        multi_routes_data = []
        try:
            raw_r = db_row.get('多重路徑資料', '[]')
            multi_routes_data = json.loads(str(raw_r).replace("'", '"'))
        except: pass
        
        col1, col2 = st.columns([3, 1])
        with col1:
            year_limit = st.slider("顯示至年份", -8000, 2024, 2024, 100)
            m = folium.Map(location=[20, 0], zoom_start=2, tiles="CartoDB positron")
            
            if multi_routes_data:
                colors = ["red", "blue", "purple", "orange", "darkgreen"]
                for r_idx, route in enumerate(multi_routes_data):
                    color = colors[r_idx % len(colors)]
                    nodes = [n for n in route.get('nodes', []) if int(n.get('year', 0)) <= year_limit]
                    
                    if len(nodes) > 1:
                        for i in range(len(nodes) - 1):
                            p1, p2 = nodes[i]['coord'], nodes[i+1]['coord']
                            curve_pts = interpolate_curved_path(p1, p2)
                            AntPath(locations=curve_pts, color=color, weight=5, delay=1000).add_to(m)
                    
                    for n in nodes:
                        if n.get('is_waypoint'): continue
                        popup_txt = f"<b>{n.get('name')}</b><br>年份: {n.get('year')}<br>證據: {n.get('evidence')}"
                        folium.Marker(location=n['coord'], popup=folium.Popup(popup_txt, max_width=300), 
                                      icon=folium.Icon(color=color if color in ['red', 'blue', 'purple', 'orange', 'green'] else 'gray', icon="info-sign")).add_to(m)
            
            st_folium(m, width="100%", height=600, key=f"species_map_{selected_plant}")
            
        with col2:
            img_url = db_row.get('代表照片', "")
            safe_render_image(img_url, default_caption=selected_plant)
            if st.button("📋 顯示物種基本資料", use_container_width=True, type="primary"):
                st.session_state['_show_profile'] = selected_plant

        if st.session_state.get('_show_profile') == selected_plant:
            @st.dialog(f"📋 {selected_plant} 詳細資料")
            def show_detailed(): render_player_card(selected_plant, st.session_state.plant_db)
            show_detailed()
            st.session_state['_show_profile'] = None

# --- ⏳ Page 2: Timeline Simulation ---
elif page == "Timeline Simulation":
    st.title("Timeline Simulation")
    st.info("此功能已與雲端資料庫介接。")

# --- 🥗 Page 3: Challenge ---
elif page == "Time VS Menu Challenge":
    st.title("時代 V.S. 菜單 🔥 時空美食模擬器")
    menu_db = st.session_state.get('menu_db', [])
    if not menu_db: 
        st.error("正在與雲端伺服器握手中...")
        st.stop()
    
    with st.sidebar:
        target_year = st.slider("歷史年份 (Year)", -3000, 2024, 1800, step=100)
        selected_city = st.selectbox("選取挑戰城市", menu_db, format_func=lambda x: f"{x['city']} ({x['region']})")

    if 'current_dish_idx' not in st.session_state: st.session_state.current_dish_idx = 0
    dish = selected_city['dishes'][st.session_state.current_dish_idx % len(selected_city['dishes'])]

    col1, col2 = st.columns([1, 2])
    with col1:
        img_urls = dish.get('image_urls', [])
        display_img = img_urls[0] if img_urls else ""
        safe_render_image(display_img, default_caption=dish['name'])
        if st.button("🎲 隨機換一道菜"):
            st.session_state.current_dish_idx = random.randint(0, 99)
            st.rerun()

    with col2:
        st.subheader(f"📍 {selected_city['city']} 於 {target_year} 年")
        st.markdown(f"**今日精選大菜：{dish['name']}**")
        ingredients = dish['ingredients']
        rows = []
        all_ok = True
        for ing in ingredients:
            arr_y = get_plant_arrival_year(selected_city['coord'], ing, st.session_state.plant_db)
            available = target_year >= arr_y
            if not available: all_ok = False
            rows.append({"食材": ing, "狀態": "✅ 已抵達" if available else "❌ 尚未抵達", "預計年份": f"{int(arr_y)} 年" if arr_y < 90000 else "未知"})
        st.table(pd.DataFrame(rows))
        if all_ok: st.balloons(); st.success("🎉 大功告成！食材全員到齊！")

# --- 🧩 Community & Admin ---
elif page == "Community Contribution":
    from ugc_submission_page import render_ugc_submission_form
    render_ugc_submission_form()

elif page == "Data & Menu Administration":
    render_page_3()
'''

with open('app.py', 'w', encoding='utf-8-sig') as f:
    f.write(code_content)
print("app.py successfully overwritten with UTF-8-SIG encoding.")
