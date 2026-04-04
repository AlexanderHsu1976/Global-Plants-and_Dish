import streamlit as st
import pandas as pd


def _safe_str(val, default='') -> str:
    """Convert a value to string, treating NaN/None as default."""
    if val is None:
        return default
    s = str(val).strip()
    return default if s in ('', 'nan', 'NaN', 'None') else s


def render_player_card(plant_name: str, plant_db: pd.DataFrame):
    """
    Renders a premium 'Player Card' for the selected plant species.
    Uses st.image() for reliable photo display inside Streamlit.
    """
    if plant_db is None or plant_db.empty:
        st.info(f"💡「{plant_name}」尚無進階資料，請先至資料維護頁面執行 AI 調研。")
        return

    # ── Robust name matching (strip whitespace + case-insensitive) ────────────
    db = plant_db.copy()
    db['_match_name'] = db['名稱'].astype(str).str.strip()
    query = plant_name.strip()
    row = db[db['_match_name'] == query]

    if row.empty:
        # Last-resort: partial match
        row = db[db['_match_name'].str.contains(query, na=False, regex=False)]

    if row.empty:
        st.info(f"💡 資料庫中找不到「{plant_name}」，請確認資料已載入並執行 AI 調研。")
        return

    data = row.iloc[0]

    # ── Safe data extraction ──────────────────────────────────────────────────
    sci_name     = _safe_str(data.get('學名'),       '待查證')
    family_cn    = _safe_str(data.get('科'),          '未知')
    family_en    = _safe_str(data.get('英文科名'),    'Unknown')
    origin       = _safe_str(data.get('起源地'),      '待考證')
    # ── 圖片載入優先權: Drive > Original Wikipedia ────────────────────────────
    import json
    image_url = _safe_str(data.get('代表照片'), '')
    try:
        raw_list = data.get('本地照片清單', '[]')
        if pd.notna(raw_list) and str(raw_list).strip() != "":
            p_list = json.loads(str(raw_list).replace("'", '"'))
            drive_urls = [u for u in p_list if str(u).startswith('http')]
            if drive_urls: image_url = drive_urls[0]
    except:
        pass

    summary      = _safe_str(data.get('調研摘要'),    '尚無摘要，建議執行 AI 深度調研。')
    wiki_url     = _safe_str(data.get('維基連結'),    '')
    special_uses = _safe_str(data.get('特殊用途'),    '')
    taboos       = _safe_str(data.get('使用禁忌'),    '')
    effects      = _safe_str(data.get('特殊效用'),    '')

    # Validate image URL
    has_image = image_url.startswith('http')

    # ── CSS ──────────────────────────────────────────────────────────────────
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&display=swap');
    .pc-wrap {
        background: linear-gradient(160deg, #0f1923 0%, #162032 100%);
        border: 1px solid rgba(0,255,180,.25);
        border-radius: 18px;
        overflow: hidden;
        box-shadow: 0 8px 32px rgba(0,0,0,.55);
        animation: pcIn .5s ease-out;
        margin-bottom: 20px;
        font-family: 'Inter', 'Noto Sans TC', sans-serif;
    }
    @keyframes pcIn { from{opacity:0;transform:translateY(14px)} to{opacity:1;transform:translateY(0)} }
    .pc-img-banner {
        width:100%; height:220px;
        object-fit:cover; display:block;
    }
    .pc-name-row {
        background: linear-gradient(to right, rgba(0,255,180,.12), transparent);
        padding: 14px 22px 10px;
        border-bottom: 1px solid rgba(0,255,180,.12);
    }
    .pc-sci  { color:#7a9ab0; font-style:italic; font-size:.9em; margin:0 0 2px; }
    .pc-name { color:#00ffb8; font-size:1.9em; font-weight:800;
               text-shadow: 0 2px 8px rgba(0,255,180,.4); margin:0; }
    .pc-body { padding: 18px 22px 16px; color:#cdd6e0; }
    .pc-badges { display:flex; flex-wrap:wrap; gap:7px; margin-bottom:16px; }
    .pc-badge {
        background:rgba(0,255,180,.07); border:1px solid rgba(0,255,180,.2);
        color:#00ffb8; padding:3px 12px; border-radius:999px;
        font-size:.8em; font-weight:600;
    }
    .pc-label {
        font-size:.72em; text-transform:uppercase; letter-spacing:1.2px;
        color:#00ffb8; font-weight:700; margin-bottom:5px;
    }
    .pc-value {
        background:rgba(255,255,255,.04); border-radius:9px;
        padding:10px 13px; line-height:1.65; font-size:.9em; margin-bottom:14px;
    }
    .pc-grid { display:grid; grid-template-columns:1fr 1fr; gap:10px; margin-bottom:14px; }
    .pc-box {
        background:rgba(255,255,255,.03); border:1px solid rgba(255,255,255,.07);
        border-radius:10px; padding:11px 13px;
        transition: border-color .2s, background .2s;
    }
    .pc-box:hover { background:rgba(0,255,180,.04); border-color:rgba(0,255,180,.2); }
    .pc-box-text { font-size:.86em; color:#a0b0be; line-height:1.55; }
    .pc-wiki {
        display:block; text-align:center; background:#00ffb8; color:#0d1117;
        padding:9px 0; border-radius:8px; font-weight:700; text-decoration:none;
        font-size:.92em; transition:background .2s;
    }
    .pc-wiki:hover { background:#00e0a8; color:#0d1117; }
    .pc-no-img {
        height:120px; display:flex; align-items:center; justify-content:center;
        background:rgba(255,255,255,.03); color:#4a6070; font-size:3em;
    }
    </style>
    """, unsafe_allow_html=True)

    # ── Card header (name + sci name) ─────────────────────────────────────────
    st.markdown(f"""
    <div class="pc-wrap">
      <div class="pc-name-row">
        <p class="pc-sci">{sci_name}</p>
        <h2 class="pc-name">{plant_name}</h2>
      </div>
    """, unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

    # ── Photo: use st.image() for guaranteed Streamlit rendering ─────────────
    FALLBACK = "https://images.unsplash.com/photo-1591857177580-dc82b9ac4e1e?auto=format&fit=crop&q=80&w=900"
    display_url = image_url if has_image else FALLBACK

    try:
        st.image(display_url, use_container_width=True,
                 caption=f"{'📷 ' + plant_name if has_image else '🖼️ 示意圖（尚未取得代表照片）'}")
    except Exception:
        st.warning("⚠️ 圖片載入失敗，建議重新執行「🖼️ 檢索代表照片」")

    # ── Card body ─────────────────────────────────────────────────────────────
    uses_txt   = special_uses if special_uses else '待更新'
    taboo_txt  = taboos       if taboos       else '無特殊禁忌'
    effect_txt = effects      if effects      else '資料調研中...'
    wiki_href  = wiki_url     if wiki_url     else '#'

    st.markdown(f"""
    <div class="pc-wrap">
      <div class="pc-body">
        <div class="pc-badges">
          <span class="pc-badge">🌿 {family_cn}</span>
          <span class="pc-badge">🔬 {family_en}</span>
          <span class="pc-badge">📍 {origin}</span>
        </div>
        <div class="pc-label">📜 調研摘要</div>
        <div class="pc-value">{summary}</div>
        <div class="pc-grid">
          <div class="pc-box">
            <div class="pc-label">✨ 特殊用途</div>
            <div class="pc-box-text">{uses_txt}</div>
          </div>
          <div class="pc-box">
            <div class="pc-label">⚠️ 使用禁忌</div>
            <div class="pc-box-text">{taboo_txt}</div>
          </div>
        </div>
        <div class="pc-label">💊 特殊效用</div>
        <div class="pc-value" style="border:1px dashed rgba(0,255,180,.2);">{effect_txt}</div>
        <a href="{wiki_href}" target="_blank" class="pc-wiki">📖 查看 Wikipedia 詳細資料</a>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # ── 🔬 實地調研影像畫廊 (Research Gallery) ──────────────────────────────────
    try:
        raw_list = data.get('本地照片清單', '[]')
        if pd.notna(raw_list) and str(raw_list).strip() != "":
            all_imgs = json.loads(str(raw_list).replace("'", '"'))
            # 過濾無效路徑
            valid_imgs = [u for u in all_imgs if str(u).startswith('http') or os.path.exists(str(u))]
            
            if valid_imgs:
                st.markdown("### 🔬 實地調研影像畫廊")
                # 使用 Streamlit columns 製作橫向畫廊
                cols = st.columns(len(valid_imgs) if len(valid_imgs) < 4 else 4)
                for i, img in enumerate(valid_imgs):
                    with cols[i % 4]:
                        label = "☁️ Cloud" if "drive.google" in str(img) else "🌐 Wiki"
                        st.image(img, use_container_width=True, caption=f"[{label}] {plant_name}-{i+1}")
    except:
        pass

    # ── Debug expander (shows stored URL for troubleshooting) ─────────────────
    with st.expander("🔍 調試資訊 (Debug)", expanded=False):
        st.write(f"**照片 URL:** `{image_url or '（空）'}`")
        st.write(f"**植物名稱匹配:** `{plant_name}` → 在 plant_db 中找到 `{len(row)}` 筆")
        st.write(f"**有效 URL:** `{has_image}`")
