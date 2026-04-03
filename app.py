import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
from folium.plugins import AntPath
import os
from data_maintenance import render_page_3, MASTER_COLUMNS
from ui_components import render_player_card

# --- 🛠️ Help Functions & Logic ---

def interpolate_curved_path(p1, p2, segments=20):
    """
    Calculate points for a quadratic Bezier curve between p1 and p2.
    Adds a control point offset for curvature.
    """
    lat1, lon1 = p1
    lat2, lon2 = p2
    
    # Control point: midpoint + offset perpendicular to the line
    mid_lat = (lat1 + lat2) / 2
    mid_lon = (lon1 + lon2) / 2
    
    # Calculate curvature offset
    # We want the curve to be "upward" or "outward" relative to the center
    dist = ((lat1 - lat2)**2 + (lon1 - lon2)**2)**0.5
    offset = dist * 0.15 # Curvature intensity
    
    # Perpendicular vector for offset
    dx = lat2 - lat1
    dy = lon2 - lon1
    length = (dx**2 + dy**2)**0.5
    if length > 0:
        ctrl_lat = mid_lat + (dy / length) * offset
        ctrl_lon = mid_lon - (dx / length) * offset
    else:
        ctrl_lat, ctrl_lon = mid_lat, mid_lon

    points = []
    for t in [i/segments for i in range(segments + 1)]:
        # Quadratic Bezier formula: (1-t)^2*P0 + 2(1-t)t*P1 + t^2*P2
        b_lat = (1-t)**2 * lat1 + 2*(1-t)*t * ctrl_lat + t**2 * lat2
        b_lon = (1-t)**2 * lon1 + 2*(1-t)*t * ctrl_lon + t**2 * lon2
        points.append((b_lat, b_lon))
    return points

def interpolate_ocean_crossing(coords):
    # This function is kept for backward compatibility or complex ocean logic if needed,
    # but we will now use interpolate_curved_path for the visual.
    new_coords = []
    for i in range(len(coords) - 1):
        p1, p2 = coords[i], coords[i+1]
        # Use our new curve logic
        curve = interpolate_curved_path(p1, p2)
        new_coords.extend(curve[:-1])
    new_coords.append(coords[-1])
    return new_coords

def load_historical_boundary(year):
    """
    Read historical boundary GeoJSON for the closest available year.
    Supported years: 117, 300, 500, 800, 1000, 1300, 1492, 1600, 1914, 1945
    """
    available_years = [117, 300, 500, 800, 1000, 1300, 1492, 1600, 1914, 1945]
    if year < available_years[0]:
        return None
    
    # Find closest previous year
    target_year = available_years[0]
    for y in available_years:
        if y <= year:
            target_year = y
            
    file_path = f"data/territories/{target_year}.json"
    if os.path.exists(file_path):
        import json
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return None

@st.cache_data
def load_data(file_path):
    if os.path.exists(file_path):
        return pd.read_csv(file_path)
    return pd.DataFrame()

# --- 📐 SPATIO-TEMPORAL LOGIC ENGINE (Helper Functions) ---
import math

def haversine(p1, p2):
    """計算兩點間的公里數 (Haversine)"""
    lat1, lon1 = p1
    lat2, lon2 = p2
    R = 6371.0 # 地球半徑
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def point_to_segment_dist_and_year(city, n1, n2, y1, y2):
    """計算點到線段距離與內插年份"""
    p_city = (float(city[0]), float(city[1]))
    p1, p2 = (float(n1[0]), float(n1[1])), (float(n2[0]), float(n2[1]))
    l2 = (p1[0] - p2[0])**2 + (p1[1] - p2[1])**2
    if l2 == 0: return haversine(p_city, p1), y1
    t = ((p_city[0] - p1[0]) * (p2[0] - p1[0]) + (p_city[1] - p1[1]) * (p2[1] - p1[1])) / l2
    t = max(0, min(1, t))
    p_proj = (p1[0] + t * (p2[0] - p1[0]), p1[1] + t * (p2[1] - p1[1]))
    return haversine(p_city, p_proj), y1 + t * (y2 - y1)

def get_plant_arrival_year(city_coord, plant_name, plant_db):
    """推算特定植物抵達城市的最早年份"""
    if plant_db is None or plant_db.empty: return 99999
    match = plant_db[plant_db['名稱'].astype(str).str.strip() == plant_name.strip()]
    if match.empty: return 99999
    import json
    try: routes = json.loads(match.iloc[0].get('多重路徑資料', '[]'))
    except: return 99999
    
    earliest = 99999
    BUFFER = 1000 # 1000km 緩衝
    for route in routes:
        nodes = route.get('nodes', [])
        if len(nodes) < 2:
            for n in nodes:
                lat, lon = (n.get('coord', [0,0]))[:2]
                if haversine(city_coord, (lat, lon)) <= BUFFER: earliest = min(earliest, int(n.get('year', 0)))
            continue
        for i in range(len(nodes)-1):
            n1, n2 = nodes[i], nodes[i+1]
            p1, p2 = (n1.get('coord', [0,0]))[:2], (n2.get('coord', [0,0]))[:2]
            y1, y2 = int(n1.get('year', 0)), int(n2.get('year', 0))
            dist, est_y = point_to_segment_dist_and_year(city_coord, p1, p2, y1, y2)
            if dist <= BUFFER: earliest = min(earliest, est_y)
    return earliest

# --- Global Configurations ---

# --- 🚀 App Initialization ---

st.set_page_config(page_title="Global Plants Path Visualizer", layout="wide")

# Session State for Data
if 'df' not in st.session_state:
    st.session_state.df = load_data("cleaned_plant_transmission_v2.csv")

# Load Master DB for Player Cards (GSheet Cloud Version)
if 'plant_db' not in st.session_state:
    from data_maintenance import load_master_db, load_menu_db
    st.session_state.plant_db = load_master_db()
    # Cache menu_db in session state for components relying on it
    if 'menu_db' not in st.session_state:
        st.session_state.menu_db = load_menu_db()

# Sidebar Navigation
st.sidebar.title("🌿 Global Plants")
nav_options = ["Static Mapping", "Timeline Simulation", "Time VS Menu Challenge", "Community Contribution"]
if st.query_params.get("mode") == "admin_access":
    nav_options.append("Data & Menu Administration")

page = st.sidebar.radio("Navigation", nav_options)

# --- 📍 Page 1: Static Mapping ---

if page == "Static Mapping":
    st.title("Static Mapping (Path View)")
    st.write("Browse the historical migration paths of global edible plants.")
    
    df = st.session_state.df
    if df.empty:
        st.warning("No data found. Please upload a CSV in Data Management.")
    else:
        # Top-level Search & Filter UI
        st.markdown("### 🌿 物種軌跡檢索 (Species Path Finder)")
        cats = df['Category'].dropna().unique().tolist()
        categories = sorted([str(c) for c in cats if str(c).strip() != ''])
        
        # Layout columns for selection
        col_c, col_p = st.columns([1, 2])
        with col_c:
            selected_cat = st.selectbox("📌 類別過濾 (Filter by Category)", ["所有科別 (All Categories)"] + categories)
            
        with col_p:
            if selected_cat == "所有科別 (All Categories)":
                filtered_df = df
            else:
                filtered_df = df[df['Category'] == selected_cat]
            plant_names = sorted(filtered_df['Name'].unique().tolist())
            
            # Text-searchable big selectbox
            selected_plant = st.selectbox("🌱 選擇目標物種 (Select Plant)", plant_names)
        
        st.divider()
        
        # Plant Data
        plant_data = df[df['Name'] == selected_plant].sort_values("Step_Order")
        
        # Check for multiple routes in plant_db session state or database
        import json
        has_multiple_routes = False
        multi_routes_data = []
        if 'plant_db' in st.session_state:
            db_row = st.session_state.plant_db[st.session_state.plant_db['名稱'] == selected_plant]
            if not db_row.empty:
                raw_json = db_row.iloc[0].get('多重路徑資料', '[]')
                if isinstance(raw_json, str) and raw_json.strip() and raw_json != '[]':
                    try:
                        multi_routes_data = json.loads(raw_json)
                        if multi_routes_data and isinstance(multi_routes_data, list):
                            # Ensure at least one route has nodes with lat/lon
                            if any('nodes' in r and len(r['nodes']) > 0 for r in multi_routes_data):
                                has_multiple_routes = True
                    except:
                        pass
        
        # Map Display
        col1, col2 = st.columns([3, 1])
        
        with col1:
            # Add Time Slider Control
            st.subheader("Time Filter (時空過濾器)")
            time_slider_year = st.slider("顯示至年份 (Display up to year)", min_value=-8000, max_value=2024, value=2024, step=100)
            
            m = folium.Map(location=[20, 0], zoom_start=2, tiles="CartoDB positron")
            
            if has_multiple_routes:
                # Plot multi-routes
                colors = ["red", "blue", "purple", "orange", "darkgreen"]
                for r_idx, route in enumerate(multi_routes_data):
                    color = colors[r_idx % len(colors)]
                    nodes = route.get('nodes', [])
                    
                    # Unified parsing for both 'coord' array (new spec) and 'lat'/'lon' (old spec)
                    valid_nodes = []
                    for n in nodes:
                        n_lat, n_lon = None, None
                        if 'coord' in n and isinstance(n['coord'], list) and len(n['coord']) >= 2:
                            n_lat, n_lon = n['coord'][0], n['coord'][1]
                        elif 'lat' in n and 'lon' in n:
                            n_lat, n_lon = n['lat'], n['lon']
                            
                        # Parse Year
                        try:
                            n_year = int(n.get('year', 0))
                        except:
                            n_year = 0
                            
                        if n_lat is not None and n_lon is not None and n_year <= time_slider_year:
                            try:
                                n['_computed_coord'] = (float(n_lat), float(n_lon))
                                n['_year'] = n_year
                                valid_nodes.append(n)
                            except: pass

                    if len(valid_nodes) > 1:
                        # Interpolate
                        for i in range(len(valid_nodes) - 1):
                            n1, n2 = valid_nodes[i], valid_nodes[i+1]
                            p1, p2 = n1['_computed_coord'], n2['_computed_coord']
                            curve_coords = interpolate_curved_path(p1, p2)
                            
                            # Styling based on phase
                            phase = str(n2.get('phase', '')).lower()
                            if 'modern' in phase or 'trade' in phase or '推論' in n2.get('evidence', ''):
                                line_style = '5, 10' # Dashed for long jumps
                                opacity = 0.6
                            else:
                                line_style = '1' # Solid
                                opacity = 0.8
                                
                            r_name = route.get('path_group') or route.get('name') or route.get('route_name') or 'Route'
                            tooltip_text = f"Route: {r_name}"
                            if n2.get('evidence'): tooltip_text += f" ({n2.get('evidence')})"
                            if route.get('corridor'): tooltip_text += f" [Corridor: {route.get('corridor')}]"
                                
                            AntPath(
                                locations=curve_coords,
                                color=color,             # 兩條路徑不同顏色區隔
                                pulse_color='white' if opacity > 0.7 else 'rgba(255,255,255,0.5)',
                                weight=5,                # 路徑加寬
                                opacity=opacity,
                                dash_array=[15, 30] if line_style == '1' else [10, 20],
                                delay=1000,              # 動態流動的速度
                                tooltip=tooltip_text
                            ).add_to(m)
                            
                    # Add markers
                    for step, n in enumerate(valid_nodes):
                        # Filter out waypoints from creating popups/markers
                        if n.get('is_waypoint') is True or str(n.get('phase', '')).lower() == 'waypoint':
                            continue
                            
                        loc_name = n.get('name') or n.get('site') or n.get('region') or '未命名遺址'
                        note_text = n.get('description') or n.get('note') or n.get('academic_note') or ''
                        r_name = route.get('path_group') or route.get('name') or route.get('route_name') or 'Route'
                        phase_str = n.get('phase', 'Unknown')
                        evidence_str = n.get('evidence') or route.get('evidence_type', '')
                        
                        popup_html = f"<b>{r_name} - #{step+1}</b><br>地點: {loc_name}<br>年份: {n.get('_year', '')}<br>階段: {phase_str}<br>證據: {evidence_str}"
                        if note_text: popup_html += f"<br>備註: {note_text}"
                        if route.get('corridor'): popup_html += f"<br>廊道: {route.get('corridor')}"
                        
                        if 'archaeological' in phase_str.lower():
                            folium.CircleMarker(
                                location=[n['_computed_coord'][0], n['_computed_coord'][1]],
                                radius=7,
                                color='black',
                                weight=2,
                                fill_color='white',
                                fill_opacity=1,
                                popup=folium.Popup(popup_html, max_width=300),
                                tooltip=f"考古遺址: {loc_name} ({n.get('_year', '')})"
                            ).add_to(m)
                        else:
                            folium.Marker(
                                location=[n['_computed_coord'][0], n['_computed_coord'][1]],
                                popup=folium.Popup(popup_html, max_width=300),
                                tooltip=f"{loc_name} ({n.get('_year', '')})",
                                icon=folium.Icon(color=color if color in ['red', 'blue', 'purple', 'orange', 'darkgreen', 'green'] else 'gray', icon="info-sign")
                            ).add_to(m)
            else:
                # Original linear fallback mapping
                coords = list(zip(plant_data['Lat'], plant_data['Lon']))
                if len(coords) > 1:
                    # Interpolate for better curved visual
                    for i in range(len(coords) - 1):
                        p1, p2 = coords[i], coords[i+1]
                        curve_coords = interpolate_curved_path(p1, p2)
                        
                        AntPath(
                            locations=curve_coords,
                            color="green",
                            pulse_color='white',
                            weight=5,
                            opacity=0.7,
                            dash_array=[15, 30],
                            delay=1000
                        ).add_to(m)
                    
                # Add markers for nodes
                for _, row in plant_data.iterrows():
                    popup_text = f"<b>階段 {row['Step_Order']}</b><br>年份: {row['Year']}<br>區域: {row['Region']}<br>{row['Description']}"
                    folium.Marker(
                        location=[row['Lat'], row['Lon']],
                        popup=folium.Popup(popup_text, max_width=300),
                        tooltip=f"階段 {row['Step_Order']}: {row['Region']}",
                        icon=folium.Icon(color="green", icon="leaf")
                    ).add_to(m)
            
            st_folium(m, width="100%", height=600)
            
        with col2:
            # ── 縮圖 ─────────────────────────────────────────────────────────
            db_row_img = pd.DataFrame()
            image_url_side = ""
            if 'plant_db' in st.session_state and not st.session_state.plant_db.empty:
                _match = st.session_state.plant_db[
                    st.session_state.plant_db['名稱'].astype(str).str.strip() == selected_plant.strip()
                ]
                if not _match.empty:
                    db_row_img = _match
                    _raw_url = str(_match.iloc[0].get('代表照片', '') or '')
                    if _raw_url not in ('', 'nan', 'NaN', 'None') and _raw_url.startswith('http'):
                        image_url_side = _raw_url

            FALLBACK_IMG = "https://images.unsplash.com/photo-1591857177580-dc82b9ac4e1e?auto=format&fit=crop&q=80&w=400"
            try:
                st.image(image_url_side or FALLBACK_IMG, use_container_width=True,
                         caption=selected_plant if image_url_side else f"{selected_plant}（示意圖）")
            except:
                st.image(FALLBACK_IMG, use_container_width=True)

            # ── 基本資料彈出按鈕 ──────────────────────────────────────────────
            if st.button("📋 顯示物種基本資料", use_container_width=True, type="primary"):
                st.session_state['_show_profile_plant'] = selected_plant

            st.divider()

            # ── 路徑資料表 ────────────────────────────────────────────────────
            st.markdown(f"**📜 傳播路徑：{selected_plant}**")
            if has_multiple_routes:
                history_rows = []
                for route in multi_routes_data:
                    group_name = route.get('path_group') or route.get('name') or route.get('route_name') or 'Route'
                    for step, n in enumerate(route.get('nodes', [])):
                        if n.get('is_waypoint') is True or str(n.get('phase', '')).lower() == 'waypoint': continue
                        year_val = n.get('year', '')
                        try: year_num = int(year_val)
                        except: year_num = 99999
                        if year_num <= time_slider_year:
                            history_rows.append({
                                '路徑': group_name,
                                '年份': year_val,
                                '地點': n.get('name') or n.get('site') or n.get('region') or '',
                                '階段': n.get('phase', ''),
                            })
                if history_rows:
                    display_df = pd.DataFrame(history_rows)
                    display_df['SortYear'] = pd.to_numeric(display_df['年份'], errors='coerce').fillna(99999)
                    display_df = display_df.sort_values(by=['SortYear', '路徑']).drop(columns=['SortYear'])
                    st.dataframe(display_df, hide_index=True, use_container_width=True)
                else:
                    st.info("此年份條件下無歷史紀錄。")
            else:
                display_df = plant_data[['Step_Order', 'Year', 'Region', 'Description']].copy()
                display_df.rename(columns={'Step_Order': '階段'}, inplace=True)
                display_df['SortYear'] = pd.to_numeric(display_df['Year'], errors='coerce').fillna(99999)
                display_df = display_df[display_df['SortYear'] <= time_slider_year].drop(columns=['SortYear'])
                if not display_df.empty:
                    st.dataframe(display_df, hide_index=True, use_container_width=True)
                else:
                    st.info("此年份條件下無歷史紀錄。")

        # ── 基本資料 Dialog (Modal) ───────────────────────────────────────────
        @st.dialog(f"📋 物種基本資料 — {selected_plant}", width="large")
        def _show_species_profile():
            render_player_card(selected_plant, st.session_state.get('plant_db', pd.DataFrame()))

        if st.session_state.get('_show_profile_plant') == selected_plant:
            st.session_state['_show_profile_plant'] = None
            _show_species_profile()

# --- ⏳ Page 2: Timeline Simulation ---

elif page == "Timeline Simulation":
    st.title("Timeline Simulation")
    st.write("Visualize the global distribution of plants at specific historical moments.")
    
    df = st.session_state.df
    if df.empty:
        st.warning("No data found.")
    else:
        # Control Panel
        col_ctrl1, col_ctrl2 = st.columns([1, 2])
        with col_ctrl1:
            year = st.slider("Historical Year (年份)", -4000, 2024, 0, step=100)
            selected_plants = st.multiselect("Select Plants (Max 3)", sorted(df['Name'].unique()), max_selections=3)
        
        with col_ctrl2:
            st.write(f"### World in {year}")
            plant_str = ", ".join(selected_plants) if selected_plants else "None selected"
            st.write(f"Active Plants: **{plant_str}**")

        # Map logic
        m = folium.Map(location=[20, 0], zoom_start=2, tiles="CartoDB positron")
        
        # 1. Load historical boundary
        geojson_data = load_historical_boundary(year)
        if geojson_data:
            folium.GeoJson(
                geojson_data,
                style_function=lambda x: {'fillColor': '#cccccc', 'color': '#888888', 'weight': 1, 'fillOpacity': 0.2},
                name="Historical Territories"
            ).add_to(m)

        # 2. Add enabled regions for each plant
        colors = ["green", "blue", "orange"]
        import json
        for idx, plant in enumerate(selected_plants):
            plant_color = colors[idx % len(colors)]
            origin_marked = False
            
            # Check for multi-routes in db
            has_multiple_routes = False
            multi_routes_data = []
            if 'plant_db' in st.session_state:
                db_row = st.session_state.plant_db[st.session_state.plant_db['名稱'] == plant]
                if not db_row.empty:
                    raw_json = db_row.iloc[0].get('多重路徑資料', '[]')
                    if isinstance(raw_json, str) and raw_json.strip() and raw_json != '[]':
                        try:
                            multi_routes_data = json.loads(raw_json)
                            if multi_routes_data and isinstance(multi_routes_data, list):
                                if any('nodes' in r and len(r['nodes']) > 0 for r in multi_routes_data):
                                    has_multiple_routes = True
                        except: pass
            
            if has_multiple_routes:
                for route in multi_routes_data:
                    nodes = route.get('nodes', [])
                    valid_nodes = []
                    for n in nodes:
                        n_lat, n_lon = None, None
                        if 'coord' in n and isinstance(n['coord'], list) and len(n['coord']) >= 2:
                            n_lat, n_lon = n['coord'][0], n['coord'][1]
                        elif 'lat' in n and 'lon' in n:
                            n_lat, n_lon = n['lat'], n['lon']
                            
                        try: n_year = int(n.get('year', 0))
                        except: n_year = 0
                            
                        if n_lat is not None and n_lon is not None and n_year <= year:
                            try:
                                n['_computed_coord'] = (float(n_lat), float(n_lon))
                                n['_year'] = n_year
                                valid_nodes.append(n)
                            except: pass

                    if len(valid_nodes) > 1:
                        for i in range(len(valid_nodes) - 1):
                            n1, n2 = valid_nodes[i], valid_nodes[i+1]
                            p1, p2 = n1['_computed_coord'], n2['_computed_coord']
                            curve_coords = interpolate_curved_path(p1, p2)
                            
                            phase = str(n2.get('phase', '')).lower()
                            line_style = '5, 10' if ('modern' in phase or 'trade' in phase or '推論' in n2.get('evidence', '')) else '1'
                            
                            # Check if the route has a group name to assign specific color logic within the plant
                            # In Page 2, we try to use a slightly varying hue based on route index if multiple routes exist
                            # but plant_color is the base identity. We will just pass the plant_color for consistency.
                            AntPath(
                                locations=curve_coords,
                                color=plant_color,
                                pulse_color='white',
                                weight=5, # 加寬
                                opacity=0.8,
                                dash_array=[15, 30] if line_style == '1' else [10, 20],
                                delay=1000,
                                tooltip=f"{plant} (Route: {route.get('path_group') or route.get('name') or 'Route'})"
                            ).add_to(m)
                            
                    if not origin_marked and len(valid_nodes) > 0:
                        first_node = valid_nodes[0]
                        folium.Marker(
                            location=[first_node['_computed_coord'][0], first_node['_computed_coord'][1]],
                            icon=folium.DivIcon(
                                icon_anchor=(0, 0),
                                html=f'<div style="font-family: sans-serif; font-size: 13px; font-weight: bold; color: white; background-color: {plant_color}; padding: 4px 10px; border-radius: 20px; border: 2px solid white; white-space: nowrap; box-shadow: 0 2px 8px rgba(0,0,0,0.5); margin-top: -12px; margin-left: 10px;">★ 起源: {plant}</div>'
                            ),
                            z_index_offset=1000
                        ).add_to(m)
                        origin_marked = True
                        
                    for step, n in enumerate(valid_nodes):
                        if n.get('is_waypoint') is True or str(n.get('phase', '')).lower() == 'waypoint': continue
                        loc_name = n.get('name') or n.get('site') or n.get('region') or '未命名遺址'
                        folium.CircleMarker(
                            location=[n['_computed_coord'][0], n['_computed_coord'][1]],
                            radius=8, color=plant_color, fill=True, fill_opacity=0.7,
                            popup=f"<b>{plant}</b><br>{loc_name} ({n.get('_year', '')})<br>相鄰階段: {n.get('phase', '')}",
                            tooltip=f"{plant}: {loc_name}"
                        ).add_to(m)
            else:
                enabled_df = df[(df['Name'] == plant) & (df['Year'] <= year)].sort_values("Step_Order")
                if not enabled_df.empty:
                    # Add path for the plant up to that year
                    coords = list(zip(enabled_df['Lat'], enabled_df['Lon']))
                    if len(coords) > 1:
                        for i in range(len(coords) - 1):
                            p1, p2 = coords[i], coords[i+1]
                            curve_coords = interpolate_curved_path(p1, p2)
                            
                            AntPath(
                                locations=curve_coords,
                                color=plant_color,
                                pulse_color='white',
                                weight=5, # 加寬
                                opacity=0.8,
                                dash_array=[15, 30],
                                delay=1000,
                                tooltip=f"{plant} propagation path"
                            ).add_to(m)
                            
                    if not origin_marked and not enabled_df.empty:
                        first_row = enabled_df.iloc[0]
                        folium.Marker(
                            location=[first_row['Lat'], first_row['Lon']],
                            icon=folium.DivIcon(
                                icon_anchor=(0, 0),
                                html=f'<div style="font-family: sans-serif; font-size: 13px; font-weight: bold; color: white; background-color: {plant_color}; padding: 4px 10px; border-radius: 20px; border: 2px solid white; white-space: nowrap; box-shadow: 0 2px 8px rgba(0,0,0,0.5); margin-top: -12px; margin-left: 10px;">★ 起源: {plant}</div>'
                            ),
                            z_index_offset=1000
                        ).add_to(m)
                        origin_marked = True
                    
                    # Add markers for active regions
                    for _, row in enabled_df.iterrows():
                        folium.CircleMarker(
                            location=[row['Lat'], row['Lon']],
                            radius=8,
                            color=plant_color,
                            fill=True,
                            fill_opacity=0.7,
                            popup=f"{plant} reached {row['Region']} in {row['Year']}",
                            tooltip=f"{plant}: {row['Region']}"
                        ).add_to(m)

        st_folium(m, width="100%", height=600)
    
# --- ⏳ Page: Time VS Menu Challenge ---
elif page == "Time VS Menu Challenge":
    st.title("時代 V.S. 菜單 🔥 時空美食模擬器")
    st.markdown("當代名菜遇到古代時空會發生什麼？設定年份，看看當時的城市是否能湊齊食材！")
    
    # 優先從 session_state 讀取雲端菜單，若無則重新載入 (GSheet Cloud Version)
    if 'menu_db' not in st.session_state or not st.session_state.menu_db:
        from data_maintenance import load_menu_db
        st.session_state.menu_db = load_menu_db()
    
    menu_db = st.session_state.menu_db
    if not menu_db:
        st.error("找不到雲端菜單資料庫！")
        st.stop()
    
    db = st.session_state.get('plant_db', pd.DataFrame())
    
    with st.sidebar:
        st.subheader("🏁 挑戰參數設定")
        target_year = st.slider("歷史年份 (Year)", -3000, 2024, 1800, step=100)
        selected_city = st.selectbox("選取挑戰城市", menu_db, format_func=lambda x: f"{x['city']} ({x['region']})")

    if 'current_dish_idx' not in st.session_state: st.session_state.current_dish_idx = 0
    dish = selected_city['dishes'][st.session_state.current_dish_idx % len(selected_city['dishes'])]

    col1, col2 = st.columns([1, 2])
    with col1:
        from data_maintenance import fetch_dish_image
        import random, os
        
        # 🎯 優先使用影像資產池 (本地路徑 或 遠端 URL)
        urls = dish.get('image_urls', [])
        if not urls and dish.get('image_url'):
            urls = [dish['image_url']]
            
        if urls:
            chosen = random.choice(urls)
            # 智慧判斷：本地路徑 vs 遠端 URL
            if chosen.startswith('assets') or chosen.startswith('\\') or (len(chosen) < 300 and not chosen.startswith('http')):
                if os.path.exists(chosen):
                    st.image(chosen, use_container_width=True, caption=f"🍽️ {dish['name']}")
                else:
                    st.image("https://via.placeholder.com/800x600?text=Photo+Missing", use_container_width=True)
            else:
                st.image(chosen, use_container_width=True, caption=f"🍽️ {dish['name']}")
        else:
            st.image("https://via.placeholder.com/800x600?text=No+Photo+Yet", use_container_width=True, caption=dish['name'])
        
        if st.button("🎲 隨機換一道菜"):
            st.session_state.current_dish_idx = random.randint(0, 100)
            st.rerun()

    with col2:
        st.subheader(f"📍 {selected_city['city']} 於 {target_year} 年")
        st.markdown(f"**今日精選大菜：{dish['name']}**")
        
        ingredients = dish['ingredients']
        rows = []
        all_ready = True
        for ing in ingredients:
            arr_y = get_plant_arrival_year(selected_city['coord'], ing, db)
            available = target_year >= arr_y
            if not available: all_ready = False
            rows.append({
                "食材": ing,
                "狀態": "✅ 已抵達" if available else "❌ 尚未抵達",
                "預計年份": f"{int(arr_y)} 年" if arr_y < 90000 else "未知",
                "等待時光": f"再等 {int((arr_y - target_year)/100)} 個世紀" if not available and arr_y < 90000 else "-"
            })
        st.table(pd.DataFrame(rows))
        
        if all_ready:
            st.success("🎉 大功告成！食材全員到齊，這道菜在此時此地可以製作！")
            st.balloons()
        else:
            missing = [r['食材'] for r in rows if "❌" in r['狀態']]
            st.error(f"殘念... 目前還吃不到，缺席：{', '.join(missing)}")
            if any(x in missing for x in ["辣椒", "番薯", "玉米", "馬鈴薯"]):
                st.warning("🏮 歷史補充：美洲作物此時還沒傳播過來喔！")

elif page == "Community Contribution":
    from ugc_submission_page import render_ugc_submission_form
    render_ugc_submission_form()

# --- ⚙️ Unified Administration ---
elif page == "Data & Menu Administration":
    from data_maintenance import render_page_3
    render_page_3()
