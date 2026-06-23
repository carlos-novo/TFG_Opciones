import sqlite3
import json

conn = sqlite3.connect("tfg_trading.db")
conn.row_factory = sqlite3.Row

# 1. Estrategia 219
print("=== DETALLES ESTRATEGIA 219 ===")
row = conn.execute("SELECT * FROM estrategias WHERE id=219").fetchone()
if row:
    d = dict(row)
    # Parse JSON fields for readable output
    for key in ['patas_json', 'condiciones_entrada_json', 'condiciones_salida_json']:
        if d.get(key):
            try:
                d[key] = json.loads(d[key])
            except Exception:
                pass
    print(json.dumps(d, indent=2))
else:
    print("Estrategia 219 no encontrada.")

# 2. Auditoría
print("\n=== LOGS DE AUDITORÍA ALREDEDOR DEL 2026-06-16 ===")
logs = conn.execute("SELECT * FROM auditoria WHERE detalles LIKE '%219%' OR evento LIKE '%219%' OR fecha LIKE '2026-06-16%' ORDER BY id DESC LIMIT 30").fetchall()
for log in logs:
    print(f"[{log['fecha']}] {log['evento']}: {log['detalles']}")

conn.close()
