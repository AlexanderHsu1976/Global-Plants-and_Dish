import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
from folium.plugins import AntPath
import os
import json
import math
from data_maintenance import render_page_3, MASTER_COLUMNS, load_master_db, load_menu_db
from ui_components import render_player_card

# --- [Module 0] Infrastructure & Helpers ---

def interpolate_curved_path(p1, p2, segments=20):
    """
    Calculate points for a quadratic Bezier curve between p1 and p2.
    """
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
    """計算兩點間的公里數 (Haversine)"""
    lat1, lon1 = p1
    lat2, lon2 = p2
    R = 6371.0
    dlat, dlon = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

def get_plant_arrival_year(city_coord, plant_name, plant_db):
    """推算特定植物抵達特定座標的最早年份"""
    if plant_db is None or plant_db.empty: return 99999
    match = plant_db[plant_db['名稱'].astype(str).str.strip() == plant_name.strip()]
    if match.empty: return 99999
    try: 
        raw_routes = match.iloc[0].get('多重路徑資料', '[]')
        if pd.isna(raw_routes) or str(raw_routes).strip() == "": routes = []
        else: routes = json.loads(str(raw_routes).replace("'", '"'))
    except: 
        return 99999
    
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
    """讀取歷史邊界地圖 (GeoJSON)，自動掃描現有年份檔案"""
    territory_dir = "data/territories"
    
    # 動態掃描目錄中的年份 (檔名需為 數字.json)
    if not os.path.exists(territory_dir): 
        return None
        
    available_years = []
    for f in os.listdir(territory_dir):
        if f.endswith(".json"):
            try:
                available_years.append(int(f.replace(".json", "")))
            except:
                continue
    available_years.sort()
    
    if not available_years: 
        return None
    
    # 尋找小於等於當前的最接近年份
    target_year = available_years[0]
    for y in available_years:
        if y <= year:
            target_year = y
            
    file_path = os.path.join(territory_dir, f"{target_year}.json")
    if os.path.exists(file_path):
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return None


# --- 🚀 App Initialization ---

st.set_page_config(page_title="Global Plants Path Visualizer", layout="wide")

# Unified Data Loading (Cloud First)
if 'plant_db' not in st.session_state:
    with st.spinner("正在從雲端同步生物與路徑資料庫..."):
        # 1. Load Master Plant DB
        st.session_state.plant_db = load_master_db()
        
        # 2. Load City Menu DB
        if 'menu_db' not in st.session_state:
            st.session_state.menu_db = load_menu_db()
            
        # 3. Synchronize 'df' for Legacy UI compatibility
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
        st.warning("⚠️ 雲端資料庫目前無資料，請至管理頁面維護。")
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
            raw_data = db_row.get('多重路徑資料', '[]')
            if pd.notna(raw_data) and str(raw_data).strip() != "":
                multi_routes_data = json.loads(str(raw_data).replace("'", '"'))
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
                            phase = str(nodes[i+1].get('phase', '')).lower()
                            line_style = [10, 20] if ('modern' in phase or 'trade' in phase) else [1]
                            AntPath(locations=curve_pts, color=color, weight=5, delay=1000, dash_array=line_style).add_to(m)
                    
                    for n in nodes:
                        if n.get('is_waypoint'): continue
                        popup_txt = f"<b>{n.get('name')}</b><br>年份: {n.get('year')}<br>證據: {n.get('evidence')}"
                        folium.Marker(location=n['coord'], popup=folium.Popup(popup_txt, max_width=300), 
                                      icon=folium.Icon(color=color if color in ['red', 'blue', 'purple', 'orange', 'green'] else 'gray', icon="info-sign")).add_to(m)
            
            st_folium(m, width="100%", height=600)
            
        with col2:
            # 優先從「本地照片清單」抓取第一個雲端網址 (Drive)
            img_url = db_row.get('代表照片', "")
            try:
                raw_list = db_row.get('本地照片清單', '[]')
                if pd.notna(raw_list) and str(raw_list).strip() != "":
                    p_list = json.loads(str(raw_list).replace("'", '"'))
                    drive_urls = [u for u in p_list if str(u).startswith('http')]
                    if drive_urls: img_url = drive_urls[0]
            except:
                pass
            
            # 顯示圖片 (Drive 優先)
            st.image(img_url if img_url and str(img_url) != 'nan' else "https://via.placeholder.com/400x300?text=No+Image", use_container_width=True)
            if st.button("📋 顯示物種基本資料", use_container_width=True, type="primary"):
                st.session_state['_show_profile'] = selected_plant

        if st.session_state.get('_show_profile') == selected_plant:
            @st.dialog(f"📋 {selected_plant} 詳細資料")
            def show_detailed(): render_player_card(selected_plant, st.session_state.plant_db)
            show_detailed()
            st.session_state['_show_profile'] = None

# --- ⏳ Page 2: Timeline Simulation ---
elif page == "Timeline Simulation":
    st.title("Timeline Simulation (Spatiotemporal View)")
    df = st.session_state.get('df', pd.DataFrame())
    
    col_ctrl1, col_ctrl2 = st.columns([1, 2])
    with col_ctrl1:
        current_year = st.slider("選擇年份 (Selected Year)", -4000, 2024, 0, step=100)
        selected_plants = st.multiselect("選取物種 (Max 3)", sorted(df['Name'].unique()) if not df.empty else [], max_selections=3)
    
    with col_ctrl2:
        st.write(f"### 🌍 公元 {current_year} 年的世界格局")
        st.info("背景陰影區域代表當代主要的政治版圖（GeoJSON 歷史模組）。")

    m = folium.Map(location=[20, 0], zoom_start=2, tiles="CartoDB positron")
    
    # Historical Boundary
    geojson_data = load_historical_boundary(current_year)
    if geojson_data:
        folium.GeoJson(geojson_data, style_function=lambda x: {'fillColor': '#888888', 'color': '#555555', 'weight': 1, 'fillOpacity': 0.15}).add_to(m)

    # Plants Active in this Year
    colors = ["green", "blue", "orange"]
    for idx, plant in enumerate(selected_plants):
        p_color = colors[idx % len(colors)]
        db_row = df[df['Name'] == plant].iloc[0]
        try: 
            raw_r = db_row.get('多重路徑資料', '[]')
            r_data = []
            if pd.notna(raw_r) and str(raw_r).strip() != "":
                r_data = json.loads(str(raw_r).replace("'", '"'))
            
            for route in r_data:
                nodes = [n for n in route.get('nodes', []) if int(n.get('year', 0)) <= current_year]
                if len(nodes) > 1:
                    for i in range(len(nodes)-1):
                        p1, p2 = nodes[i]['coord'], nodes[i+1]['coord']
                        AntPath(locations=interpolate_curved_path(p1, p2), color=p_color, weight=4, delay=1200).add_to(m)
                for n in nodes:
                    if n.get('is_waypoint'): continue
                    folium.CircleMarker(location=n['coord'], radius=6, color=p_color, fill=True, 
                                        tooltip=f"{plant}: {n.get('name')}").add_to(m)
        except: pass

    st_folium(m, width="100%", height=600)

# --- 🥗 Page 3: Challenge ---
elif page == "Time VS Menu Challenge":
    st.title("時代 V.S. 菜單 🔥 時空美食模擬器")
    menu_db = st.session_state.get('menu_db', [])
    if not menu_db: 
        st.error("找不到雲端菜單資料庫！")
        st.stop()
    
    with st.sidebar:
        target_year = st.slider("歷史年份 (Year)", -3000, 2024, 1800, step=100)
        selected_city = st.selectbox("選取挑戰城市", menu_db, format_func=lambda x: f"{x['city']} ({x['region']})")

    if 'current_dish_idx' not in st.session_state: st.session_state.current_dish_idx = 0
    dish = selected_city['dishes'][st.session_state.current_dish_idx % len(selected_city['dishes'])]

    col1, col2 = st.columns([1, 2])
    with col1:
        from data_maintenance import fetch_dish_image
        display_img = fetch_dish_image(dish)
        if not display_img or str(display_img).strip() == "":
            display_img = "https://via.placeholder.com/600x400?text=No+Photo"
        st.image(display_img, use_container_width=True, caption=dish['name'])
        if st.button("🎲 隨機換一道菜"):
            import random
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
