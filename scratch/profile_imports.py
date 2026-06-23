import time

def time_import(module_name):
    t0 = time.time()
    exec(f"import {module_name}")
    print(f"Import {module_name}: {time.time() - t0:.4f}s")

time_import("conexion_ibkr")
time_import("motor_logica")
time_import("base_datos")
time_import("motor_bs")
time_import("notificaciones")
time_import("watchdogs")
