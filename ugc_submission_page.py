import streamlit as st
from datetime import datetime
import gspread
from data_maintenance import get_gsheet_client

# --- [設定區] ---
SPREADSHEET_NAME = "Global_Plants_DB"  # 你的試算表名稱
WORKSHEET_UGC = "ugc_submissions"      # 使用者貢獻分頁名稱

def submit_to_gsheet(data_list):
    """ 將資料清單寫入 Google Sheets 的末端 """
    client = get_gsheet_client()
    if not client: return False
    
    try:
        sh = client.open(SPREADSHEET_NAME)
        worksheet = sh.worksheet(WORKSHEET_UGC)
        worksheet.append_row(data_list)
        return True
    except Exception as e:
        st.error(f"寫入資料失敗: {e}")
        return False

def render_ugc_submission_form():
    """ 渲染使用者上傳表單 UI """
    st.title("🍜 城市美食貢獻中心")
    st.markdown("""
    發現了地圖上沒有的在地美食嗎？歡迎分享你的私藏菜單！  
    管理員審核通過後，你的貢獻將會出現在全球美食地圖上。
    """)

    # 使用 st.form 確保資料完整性
    with st.form("ugc_form", clear_on_submit=True):
        st.subheader("📝 填寫菜單資訊")
        
        col1, col2 = st.columns(2)
        with col1:
            user_name = st.text_input("你的暱稱", placeholder="例如：美食愛好者小明")
            city = st.text_input("推薦城市", placeholder="例如：台北、東京...")
        
        with col2:
            dish_name = st.text_input("菜餚名稱", placeholder="例如：滷肉飯")
            image_url = st.text_input("圖片網址 (JPG/PNG)", placeholder="https://example.com/photo.jpg")
            st.caption("💡 提示：目前請提供圖片的公開網址，或可使用 Google Drive 公開連結。")

        user_comment = st.text_area("推薦理由或推薦餐廳", placeholder="這道菜在那裡很有名，因為...", height=150)
        
        submitted = st.form_submit_button("🚀 提交我的貢獻")
        
        if submitted:
            if not user_name or not city or not dish_name:
                st.warning("⚠️ 請至少填寫姓名、城市與菜名。")
            else:
                # 準備寫入的資料列 (對應規劃書的分頁 C 欄位)
                # Timestamp, User_Name, City, Dish_Name, User_Comment, Upload_Image, Status
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                status = "Pending" # 預設為待審核
                
                payload = [
                    timestamp, 
                    user_name, 
                    city, 
                    dish_name, 
                    user_comment, 
                    image_url, 
                    status
                ]
                
                with st.spinner("正在將你的美味記憶送往雲端..."):
                    if submit_to_gsheet(payload):
                        st.balloons()
                        st.success("🎉 提交成功！感謝你的貢獻。管理員審核後就會上架囉！")
                    else:
                        st.error("❌ 提交失敗，請檢查網路連線或稍後再試。")
