import sys
import os
import io
import json
import re
import pandas as pd
import folium
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QSlider, QLabel, QComboBox, 
                             QListWidget, QAbstractItemView, QTextBrowser, 
                             QCheckBox, QTabWidget, QPushButton, QFileDialog, 
                             QLineEdit, QFormLayout, QMessageBox)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtCore import Qt, QTimer
from folium.plugins import AntPath

# 起源座標中心資料庫
REGION_COORDS = {
    "東亞中心": [35, 105], "肥沃月彎": [33, 44], "中美洲中心": [19, -99],
    "安地斯中心": [-15, -75], "亞馬遜中心": [-3, -60], "南亞中心": [20, 78],
    "南亞/東南亞": [15, 100], "東南亞中心": [5, 115], "地中海中心": [38, 15],
    "西非中心": [10, -5], "衣索比亞中心": [9, 40], "中亞中心": [42, 65],
    "大洋洲中心": [-25, 135], "北美中心": [40, -100]
}

HUBS = {"歐洲": [50, 10], "北美": [40, -100], "東亞": [35, 115], "南美": [-15, -60]}

class GlobalPlantsGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Global Plants Explorer v1.2 - 專業資料管理版")
        self.resize(1400, 900)
        
        # 載入初始資料
        self.load_local_data()
        
        # [優化] 防抖計時器
        self.update_timer = QTimer()
        self.update_timer.setSingleShot(True)
        self.update_timer.timeout.connect(self.update_map)
        
        self.init_ui()

    def load_local_data(self):
        try:
            self.ingredients_df = pd.read_csv("data/ingredients.csv")
            self.recipes_df = pd.read_csv("data/recipes.csv")
        except Exception as e:
            print(f"Error loading data: {e}")
            sys.exit(1)

    def init_ui(self):
        self.setStyleSheet("""
            QMainWindow { background-color: #0f1116; }
            QLabel { color: #e0e0e0; font-family: 'Microsoft JhengHei'; }
            QListWidget { background-color: #1a1d23; color: #fff; border: none; border-radius: 8px; padding: 5px; }
            QComboBox { background-color: #252932; color: #fff; border-radius: 5px; padding: 5px; }
            QLineEdit { background-color: #1a1d23; color: #fff; border: 1px solid #333; padding: 5px; border-radius: 4px; }
            QTextBrowser { background-color: #1a1d23; color: #00ffcc; border-radius: 8px; border: 1px solid #333; font-size: 13px; }
            QPushButton { background-color: #00ffcc; color: #000; font-weight: bold; border-radius: 5px; padding: 8px; }
            QPushButton:hover { background-color: #00cca3; }
            QCheckBox { color: #00ffcc; font-weight: bold; margin-top: 10px; }
            QTabBar::tab { background: #252932; color: #888; padding: 10px 20px; border-top-left-radius: 8px; border-top-right-radius: 8px; margin-right: 2px; }
            QTabBar::tab:selected { background: #1a1d23; color: #00ffcc; border-bottom: 2px solid #00ffcc; }
        """)

        # 主分頁機制
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        # --- 分頁 1 : 地圖分析 ---
        self.map_tab = QWidget()
        self.setup_map_tab()
        self.tabs.addTab(self.map_tab, "🌍 互動時空地圖")

        # --- 分頁 2 : 資訊擷取/管理 ---
        self.data_tab = QWidget()
        self.setup_data_tab()
        self.tabs.addTab(self.data_tab, "📥 資訊擷取與新增")

        # 初始刷新
        self.update_map()
        self.update_recipe_analysis()

    def setup_map_tab(self):
        layout = QHBoxLayout(self.map_tab)
        
        # 左側側欄
        sidebar = QVBoxLayout()
        sidebar.setContentsMargins(10, 10, 10, 10)
        
        sidebar.addWidget(QLabel("📅 時間軸控制"))
        self.year_label = QLabel("當前年份: 2024 CE")
        sidebar.addWidget(self.year_label)
        self.year_slider = QSlider(Qt.Orientation.Horizontal)
        self.year_slider.setRange(-4000, 2024)
        self.year_slider.setValue(2024)
        self.year_slider.valueChanged.connect(self.on_year_change)
        sidebar.addWidget(self.year_slider)

        sidebar.addWidget(QLabel("\n選擇追蹤植物:"))
        self.ing_list = QListWidget()
        self.ing_list.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
        self.ing_list.addItems(self.ingredients_df['name'].tolist())
        # 預選
        for i in ["番茄", "水稻"]:
            it = self.ing_list.findItems(i, Qt.MatchFlag.MatchExactly)
            if it: it[0].setSelected(True)
        self.ing_list.itemSelectionChanged.connect(self.request_update)
        sidebar.addWidget(self.ing_list)

        sidebar.addWidget(QLabel("\n食譜歷史判定:"))
        self.recipe_box = QComboBox()
        self.recipe_box.addItems(self.recipes_df['recipe_name'].tolist())
        self.recipe_box.currentIndexChanged.connect(self.update_recipe_analysis)
        sidebar.addWidget(self.recipe_box)

        sidebar.addWidget(QLabel("\n圖層控制:"))
        self.show_territories_cb = QCheckBox("顯示歷史疆域 (GeoJSON)")
        self.show_territories_cb.setChecked(True)
        self.show_territories_cb.toggled.connect(self.request_update)
        sidebar.addWidget(self.show_territories_cb)

        self.analysis_box = QTextBrowser()
        sidebar.addWidget(self.analysis_box)
        layout.addLayout(sidebar, 1)

        # 右側 WebView
        self.web_view = QWebEngineView()
        layout.addWidget(self.web_view, 3)

    def setup_data_tab(self):
        main_layout = QVBoxLayout(self.data_tab)
        main_layout.setContentsMargins(50, 50, 50, 50)
        main_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # --- 批量匯入區 ---
        import_group = QVBoxLayout()
        import_title = QLabel("📁 批量 Excel 匯入 (XLSX)")
        import_title.setStyleSheet("font-size: 20px; color: #00ffcc; font-weight: bold;")
        import_group.addWidget(import_title)
        
        btn_import = QPushButton(" 選擇 XLSX 檔案並匯入資料庫 ")
        btn_import.clicked.connect(self.handle_excel_import)
        import_group.addWidget(btn_import)
        
        import_hint = QLabel("提示：格式需符合《食用植物傳遞.xlsx》欄位編排（ID, 分類, 名稱, 起源, 傳遞路徑...）")
        import_hint.setStyleSheet("color: #666; font-size: 12px;")
        import_group.addWidget(import_hint)
        main_layout.addLayout(import_group)

        main_layout.addWidget(QLabel("\n" + "—" * 50 + "\n"))

        # --- 手動輸入區 ---
        manual_title = QLabel("✍️ 手動新增食材資訊")
        manual_title.setStyleSheet("font-size: 20px; color: #00ffcc; font-weight: bold;")
        main_layout.addWidget(manual_title)

        form = QFormLayout()
        form.setSpacing(15)
        self.input_name = QLineEdit()
        self.input_cat = QComboBox()
        self.input_cat.addItems(["主食類", "蔬菜類", "水果類", "豆類", "香料/飲料類", "其他"])
        self.input_origin = QLineEdit()
        self.input_year = QLineEdit("-2000")
        self.input_bio = QLineEdit()
        self.input_wiki = QLineEdit()

        form.addRow("🌱 食材名稱:", self.input_name)
        form.addRow("📂 食材分類:", self.input_cat)
        form.addRow("📍 起源中心:", self.input_origin)
        form.addRow("📅 傳遞年份 (數字):", self.input_year)
        form.addRow("🧬 生物特性:", self.input_bio)
        form.addRow("🔗 維基連結:", self.input_wiki)
        main_layout.addLayout(form)

        btn_save = QPushButton(" 確認新增至資料庫 ")
        btn_save.clicked.connect(self.handle_manual_save)
        main_layout.addWidget(btn_save)

    # --- 邏輯處理 ---
    def handle_excel_import(self):
        path, _ = QFileDialog.getOpenFileName(self, "選取匯入檔案", "", "Excel Files (*.xlsx)")
        if not path: return

        try:
            df = pd.read_excel(path, header=None)
            new_data = []
            for _, row in df.iterrows():
                name = str(row[2]).strip()
                if name == "nan" or name == "名稱": continue
                
                # 簡易解析年份
                chain = str(row[4])
                year_match = re.search(r'(-?\d+)', chain)
                year = int(year_match.group(1)) if year_match else 2024
                
                new_data.append({
                    'name': name,
                    'origin_region': str(row[3]),
                    'propagation_year': year,
                    'characteristics': str(row[7]) if str(row[7]) != "nan" else chain,
                    'wiki_link': f"https://zh.wikipedia.org/wiki/{name}"
                })
            
            new_df = pd.DataFrame(new_data)
            # 與現有資料合併或覆蓋
            new_df.to_csv("data/ingredients.csv", index=False, encoding='utf-8-sig')
            
            QMessageBox.information(self, "成功", f"已成功匯入 {len(new_df)} 筆植物資料！地圖與名單已更新。")
            self.refresh_app_data()
        except Exception as e:
            QMessageBox.critical(self, "錯誤", f"匯入失敗：{e}")

    def handle_manual_save(self):
        name = self.input_name.text().strip()
        if not name: return

        new_row = {
            'name': name,
            'origin_region': self.input_origin.text().strip(),
            'propagation_year': int(self.input_year.text() or 2024),
            'characteristics': self.input_bio.text().strip(),
            'wiki_link': self.input_wiki.text().strip()
        }
        
        # 寫入 CSV
        df = pd.read_csv("data/ingredients.csv")
        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
        df.to_csv("data/ingredients.csv", index=False, encoding='utf-8-sig')
        
        QMessageBox.information(self, "成功", f"食材「{name}」已成功加入資料庫！")
        self.refresh_app_data()
        self.input_name.clear()

    def refresh_app_data(self):
        self.load_local_data()
        self.ing_list.clear()
        self.ing_list.addItems(self.ingredients_df['name'].tolist())
        self.update_map()

    # --- 地圖更新邏輯 (與 V1.1 一致) ---
    def on_year_change(self, val):
        suffix = "CE" if val >= 0 else "BCE"
        self.year_label.setText(f"當前年份: {abs(val)} {suffix}")
        self.request_update()
        self.update_recipe_analysis()

    def request_update(self):
        self.update_timer.start(250)

    def update_map(self):
        year = self.year_slider.value()
        selected = [i.text() for i in self.ing_list.selectedItems()]
        
        # [動態底圖切換] 啟動歷史層時，移除現代國界與標籤 (No Labels)
        tile_style = "CartoDB dark_matter_nolabels" if self.show_territories_cb.isChecked() else "CartoDB dark_matter"
        m = folium.Map(location=[20, 10], zoom_start=2.5, tiles=tile_style)
        
        # [1] 繪製歷史文明疆域 (如果勾選)
        if self.show_territories_cb.isChecked():
            territory_dir = "data/territories"
            if os.path.exists(territory_dir):
                territory_files = [f for f in os.listdir(territory_dir) if f.endswith(".json")]
                closest = None
                min_diff = 500
                for f in territory_files:
                    try:
                        f_year = int(f.replace(".json", ""))
                        if abs(year - f_year) < min_diff:
                            min_diff = abs(year - f_year)
                            closest = f
                    except: pass
                if closest:
                    with open(os.path.join(territory_dir, closest), "r", encoding="utf-8") as fd:
                        folium.GeoJson(json.load(fd), style_function=lambda x: {'fillColor': '#00ffcc', 'color': '#00ffcc', 'weight': 1, 'fillOpacity': 0.15}).add_to(m)

        for name in selected:
            res = self.ingredients_df[self.ingredients_df['name'] == name]
            if res.empty: continue
            row = res.iloc[0]
            origin = str(row['origin_region'])
            try: pyear = int(row['propagation_year'])
            except: pyear = 2024
            if year >= pyear and origin in REGION_COORDS:
                coord = REGION_COORDS[origin]
                folium.CircleMarker(location=coord, radius=8, color="#00ffcc", fill=True, popup=f"<b>{name}</b>").add_to(m)
                if year >= 1500:
                    target = HUBS["歐洲"] if "中美洲" in origin or "安地斯" in origin else ([50, 15] if "東亞" in origin or "南亞" in origin else None)
                    if target: AntPath(locations=[coord, target], delay=1000, color="#00ffcc", weight=3).add_to(m)

        html_data = io.BytesIO()
        m.save(html_data, close_file=False)
        self.web_view.setHtml(html_data.getvalue().decode())

    def update_recipe_analysis(self):
        if self.recipe_box.count() == 0: return
        year, recipe_name = self.year_slider.value(), self.recipe_box.currentText()
        row = self.recipes_df[self.recipes_df['recipe_name'] == recipe_name].iloc[0]
        ings = [i.strip() for i in str(row['ingredients']).split(',')]
        result = [f"<b>分析對象：</b>{recipe_name}<br>"]
        all_ok = True
        for ing in ings:
            data = self.ingredients_df[self.ingredients_df['name'] == ing]
            if not data.empty:
                py = int(data.iloc[0]['propagation_year'])
                if year >= py: result.append(f"✅ {ing}")
                else:
                    result.append(f"❌ <font color='#ff4b4b'>{ing} ({py})</font>")
                    all_ok = False
            else:
                result.append(f"❓ {ing}")
                all_ok = False
        result.append("<br>" + ("💡 此料理可行！" if all_ok else "⚠️ 食材不足。"))
        self.analysis_box.setHtml("<br>".join(result))

if __name__ == "__main__":
    app = QApplication(sys.argv)
    ex = GlobalPlantsGUI()
    ex.show()
    sys.exit(app.exec())
