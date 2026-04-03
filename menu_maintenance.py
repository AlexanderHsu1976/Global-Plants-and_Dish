import streamlit as st
import json
import os
import pandas as pd
from data_maintenance import fetch_dish_image, research_dish_info_ai

MENU_FILE = "menu_db.json"

def load_menu_db():
    if os.path.exists(MENU_FILE):
        with open(MENU_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def save_menu_db(data):
    with open(MENU_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def render_menu_maintenance():
    # --- 1. PIN 驗證系統 ---
    if 'data_admin_authenticated' not in st.session_state:
        st.session_state.data_admin_authenticated = False

    if not st.session_state.data_admin_authenticated:
        st.title("🍴 菜單維護中心")
        st.info("🔒 管理員權限驗證")
        pin = st.text_input("PIN 碼", type="password", key="admin_pin")
        if st.button("🔑 登入"):
            if pin in ["admin123", "1234"]:
                st.session_state.data_admin_authenticated = True
                st.rerun()
            else: st.error("❌ PIN 錯誤")
        return

    # --- 2. 側邊欄 AI 配置 ---
    with st.sidebar:
        if st.button("🚪 登出系統"):
            st.session_state.data_admin_authenticated = False
            st.rerun()
        st.divider()
        st.subheader("🔑 AI 搜尋配置")
        
        # 🟢 修正：增加 API Key 碼數顯示 (處理長度問題)
        raw_key = st.session_state.get('gemini_api_key', '')
        api_key = st.text_input("Gemini API Key", value=raw_key, type="password")
        
        if api_key:
            key_len = len(api_key.strip())
            st.caption(f"當前 Key 長度: {key_len} 碼 (預期為 39 碼)")
            from data_maintenance import init_gemini
            if init_gemini(api_key):
                st.success("AI 引擎就緒")
                m_list = st.session_state.get('gemini_model_list', ["gemini-2.0-flash"])
                st.session_state.selected_model = st.selectbox("🎯 AI 模型", m_list)
            else: st.error("API Key 驗證失敗")

    st.title("🍴 菜單與城市維護中心")
    menu_db = load_menu_db()
    plant_names = []
    if 'plant_db' in st.session_state and not st.session_state.plant_db.empty:
        plant_names = sorted(st.session_state.plant_db['名稱'].unique().tolist())

    city_names = [c['city'] for c in menu_db]
    selected_city_name = st.selectbox("選擇城市", ["-- 請選擇 --"] + city_names)

    if selected_city_name == "-- 請選擇 --": return

    city_idx = next(i for i, c in enumerate(menu_db) if c['city'] == selected_city_name)
    city_data = menu_db[city_idx]
    dishes = city_data.get('dishes', [])

    # --- 3. 初始化 SessionState (Stitched) ---
    for i, dish in enumerate(dishes):
        p = f"{selected_city_name}_{i}"
        k_zh, k_en, k_url, k_desc, k_ing = f"zh_{p}", f"en_{p}", f"url_{p}", f"desc_{p}", f"ing_{p}"
        if k_zh not in st.session_state: st.session_state[k_zh] = dish.get('name', '')
        if k_en not in st.session_state: st.session_state[k_en] = dish.get('name_en', '')
        if k_url not in st.session_state: st.session_state[k_url] = dish.get('image_url', '')
        if k_desc not in st.session_state: st.session_state[k_desc] = dish.get('description', '')
        if k_ing not in st.session_state: st.session_state[k_ing] = dish.get('ingredients', [])

    # --- 4. 操作按鈕 ---
    st.divider()
    b1, b2, b3 = st.columns(3)
    
    with b1:
        if st.button("💾 儲存所有變更", use_container_width=True, type="primary"):
            for i in range(len(dishes)):
                p = f"{selected_city_name}_{i}"
                dishes[i].update({
                    "name": st.session_state[f"zh_{p}"],
                    "name_en": st.session_state[f"en_{p}"],
                    "image_url": st.session_state[f"url_{p}"],
                    "description": st.session_state[f"desc_{p}"],
                    "ingredients": st.session_state[f"ing_{p}"]
                })
            save_menu_db(menu_db)
            st.success("✅ 資料庫存檔成功！")

    with b2:
        if st.button("🚀 批次 AI 調研 (全城)", use_container_width=True):
            if not st.session_state.get('gemini_api_key'):
                st.error("❌ 請輸入 API Key")
            else:
                p_bar = st.progress(0.0)
                msg = st.empty()
                for i in range(len(dishes)):
                    p = f"{selected_city_name}_{i}"
                    msg.text(f"分析中: {st.session_state[f'zh_{p}']}")
                    res = research_dish_info_ai(st.session_state[f"zh_{p}"], st.session_state[f"en_{p}"])
                    if res:
                        st.session_state[f"en_{p}"], st.session_state[f"url_{p}"] = res
                        dishes[i]['name_en'], dishes[i]['image_url'] = res
                    p_bar.progress((i+1)/len(dishes))
                msg.success("✅ 調研完成！請按儲存。")
                st.rerun()

    with b3:
        if st.button("➕ 新增菜餚", use_container_width=True):
            city_data['dishes'].append({"name": "新菜餚", "name_en": "", "ingredients": [], "description": "", "image_url": ""})
            save_menu_db(menu_db)
            st.rerun()

    st.divider()

    # --- 5. 菜單各別編輯區 ---
    for i, dish in enumerate(dishes):
        p = f"{selected_city_name}_{i}"
        k_zh, k_en, k_url, k_desc, k_ing = f"zh_{p}", f"en_{p}", f"url_{p}", f"desc_{p}", f"ing_{p}"

        with st.container(border=True):
            col1, col2 = st.columns([1.5, 3])
            with col1:
                img_src = st.session_state[k_url] if st.session_state[k_url] else "https://via.placeholder.com/400x300?text=No+Photo"
                st.image(img_src, use_container_width=True)
                if st.button(f"🔍 單項搜尋", key=f"btn_{p}"):
                    res = research_dish_info_ai(st.session_state[k_zh], st.session_state[k_en])
                    if res:
                        st.session_state[k_en], st.session_state[k_url] = res
                        st.rerun()
                st.text_input("圖片網址", key=k_url)
            with col2:
                c1, c2 = st.columns(2)
                with c1: st.text_input("菜餚中文名", key=k_zh)
                with c2: st.text_input("菜餚英文名", key=k_en)
                st.multiselect("核心食材", options=plant_names, key=k_ing)
                st.text_area("描述內容", key=k_desc)
