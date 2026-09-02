with open("../app_web.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

keywords = ["datos_cuenta", "posiciones_cartera", "tab3", "patas_opciones", "strike", "prima", "vencimiento", "BlackScholes", "MotorBlackScholes"]
for i, line in enumerate(lines):
    for kw in keywords:
        if kw in line:
            print(f"Line {i+1} ({kw}): {line.strip()}")
