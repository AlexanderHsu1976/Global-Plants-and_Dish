import pandas as pd
import os

def fix_csv():
    target = 'plant_master_db.csv'
    if not os.path.exists(target):
        print(f"File {target} not found.")
        return
        
    print(f"Reading {target}...")
    df = pd.read_csv(target, encoding='utf-8-sig')
    
    # 1. Sanitize column names
    old_cols = df.columns.tolist()
    # Remove all whitespace inside column names (split + join)
    new_cols = ["".join(c.split()) for c in old_cols]
    
    # Map any recognizable corrupted column to standard
    mapping = {}
    for old, new in zip(old_cols, new_cols):
        if old != new:
            print(f"  Fixing column: [{old}] -> [{new}]")
        mapping[old] = new
    
    df = df.rename(columns=mapping)
    
    # 2. Reorder or filter based on MASTER_COLUMNS if needed
    MASTER_COLUMNS = [
        "選擇", "ID", "名稱", "英文名稱", "學名", "科", "英文科名", "起源地", 
        "傳遞路徑", "傳播歷史(考據)", "傳播地理(階段)", "多重路徑資料", 
        "調研摘要", "維基連結", "代表照片", "本地照片清單", "特殊用途", "使用禁忌", 
        "特殊效用", "核實狀態", "建議"
    ]
    
    # Check if we have multiple versions of same column due to corruption
    # (e.g. '名稱' and '  名稱  ')
    # Actually, df.rename handles this if we map both to '名稱'. 
    # But let's be careful.
    
    # 3. Save it back clean
    df.to_csv(target, index=False, encoding='utf-8-sig')
    print(f"Saved cleaned {target}")

if __name__ == '__main__':
    fix_csv()
