with open("../app_web.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if "session_state" in line and "=" in line and ("not in" in line or "get(" in line):
        print(f"Line {i+1}: {line.strip()}")
