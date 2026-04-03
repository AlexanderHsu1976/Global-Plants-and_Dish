import streamlit as st
import json
import time
import pandas as pd
from data_maintenance import apply_editor_changes, run_deep_ai_investigation, search_plant_image_with_ai, research_cultural_data_with_ai

def render_ai_grid(api_key, selected_model):
    st.write("---")
    st.markdown("#### 🧠 AI 智慧擴充功能 (AI-Powered Extensions)")
    b_col1, b_col2, b_col3, b_col4 = st.columns(4)
    
    with b_col1:
        btn_verify = st.button("🚀 批次科學核實", help="核實學名、科別、俗名與維基連結", use_container_width=True)
    with b_col2:
        btn_deep = st.button("🧬 深度路徑調研", help="重建時空全軌跡 (多向性傳播 JSON)", use_container_width=True)
    with b_col3:
        btn_photo = st.button("🖼️ 檢索代表照片", help="自動搜尋植物代表性影像網址", use_container_width=True)
    with b_col4:
        btn_cultural = st.button("🏮 文化特質調研", help="搜尋特殊用途、禁忌與特殊效用", use_container_width=True)

    if btn_verify or btn_deep or btn_photo or btn_cultural:
        if not api_key:
            st.error("請先在側邊欄輸入 Gemini API Key！")
        else:
            apply_editor_changes("main_editor_v12")
            s_idx = st.session_state.plant_db[st.session_state.plant_db["選擇"] == True].index.tolist()
            if not s_idx:
                st.warning("請先勾選物種！")
            else:
                nb = st.session_state.plant_db.copy()
                total = len(s_idx)
                p_bar = st.progress(0)
                
                for j, idx in enumerate(s_idx):
                    row = nb.loc[idx]
                    p_name = row['名稱']
                    s_name = row['學名']
                    
                    with st.status(f"正在各維度調研 {p_name} ({j+1}/{total})...") as status:
                        if btn_verify:
                            prompt_v = f"針對植物「{p_name}」(學名: {s_name})，回傳嚴謹的學術 JSON: {{\"scientific_name\": \"...\", \"common_name_en\": \"...\", \"family_cn\": \"...\", \"family_en\": \"...\", \"wiki_url\": \"...\"}}。只回傳 JSON 字串。"
                            try:
                                response = st.session_state.gemini_client.models.generate_content(model=selected_model, contents=prompt_v)
                                res = json.loads(response.text.replace("```json", "").replace("```", "").strip())
                                nb.at[idx, '學名'] = res.get('scientific_name', s_name)
                                nb.at[idx, '英文名稱'] = res.get('common_name_en', row['英文名稱'])
                                nb.at[idx, '科'] = res.get('family_cn', row['科'])
                                nb.at[idx, '英文科名'] = res.get('family_en', row['英文科名'])
                                nb.at[idx, '維基連結'] = res.get('wiki_url', row['維基連結'])
                                nb.at[idx, '核實狀態'] = "已核實"
                                status.update(label=f"✅ {p_name} 科學核實完成", state="complete")
                            except: status.update(label=f"❌ {p_name} 核實失敗", state="error")
                        
                        elif btn_deep:
                            res = run_deep_ai_investigation(p_name, row['起源地'], row['傳遞路徑'], model_name=selected_model)
                            if "error" not in res:
                                nb.at[idx, '多重路徑資料'] = json.dumps(res.get('dispersal_trajectory', []), ensure_ascii=False)
                                nb.at[idx, '調研摘要'] = res.get('investigation_summary', '')
                                nb.at[idx, '核實狀態'] = "已核實"
                                status.update(label=f"✅ {p_name} 軌跡重建完成", state="complete")
                            else: status.update(label=f"❌ {p_name} 調研失敗", state="error")
                            
                        elif btn_photo:
                            url = search_plant_image_with_ai(p_name, s_name)
                            if url:
                                nb.at[idx, '代表照片'] = url
                                status.update(label=f"✅ {p_name} 照片已尋獲", state="complete")
                            else: status.update(label=f"⚠️ {p_name} 找不到合適照片", state="error")
                            
                        elif btn_cultural:
                            c_data = research_cultural_data_with_ai(p_name, s_name)
                            if c_data:
                                nb.at[idx, '特殊用途'] = c_data.get('special_uses', '')
                                nb.at[idx, '使用禁忌'] = c_data.get('taboos', '')
                                nb.at[idx, '特殊效用'] = c_data.get('special_effects', '')
                                status.update(label=f"✅ {p_name} 文化特質調研完成", state="complete")
                            else: status.update(label=f"❌ {p_name} 文化調研失敗", state="error")
                    
                    p_bar.progress((j + 1) / total)
                    time.sleep(1)
                
                st.session_state.plant_db = nb
                st.success("📂 批量 AI 調研任務執行完畢！")
                st.rerun()
