with open("../app_web.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if "st_dialog" in line or "dialog" in line or "btn_top_cot" in line:
        print(f"Line {i+1}: {line.strip()}")
