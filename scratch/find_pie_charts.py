with open("../app_web.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if "BBVA" in line or "diversific" in line or "Pie" in line or "px.pie" in line or "go.Pie" in line:
        print(f"Line {i+1}: {line.strip()}")
