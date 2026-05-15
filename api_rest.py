from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, RedirectResponse
from base_datos import GestorBaseDatos
import json

app = FastAPI(
    title="API REST TFG Opciones",
    description="Microservicio de monitorización para el sistema algorítmico de opciones.",
    version="2.0.0"
)

db = GestorBaseDatos()

@app.get("/", include_in_schema=False)
def raiz():
    """Redirige automáticamente la raíz a la página de documentación."""
    return RedirectResponse(url="/docs")

@app.get("/health", summary="Comprobar estado del servidor")
def health_check():
    return {"status": "ok", "message": "API de monitorización activa y escuchando"}

@app.get("/operaciones", summary="Obtener historial de operaciones")
def obtener_operaciones(limit: int = 50):
    try:
        df = db.obtener_operaciones()
        if df is None or df.empty:
            return JSONResponse(content={"data": []})
        
        # Convertimos el DataFrame a JSON y luego a dict para que Pandas maneje los NaNs (los convierte a null)
        records = json.loads(df.tail(limit).to_json(orient="records"))
        return {"data": records}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/auditoria", summary="Obtener logs de auditoría (Watchdog y motor)")
def obtener_auditoria(limit: int = 50):
    try:
        df = db.obtener_logs()
        if df is None or df.empty:
            return JSONResponse(content={"data": []})
        
        records = json.loads(df.tail(limit).to_json(orient="records", date_format="iso"))
        return {"data": records}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/cola-reintentos", summary="Ver órdenes estancadas en el Watchdog")
def obtener_cola():
    try:
        # Importante: obtener_reintentos_pendientes solo devuelve las QUEUED.
        df = db.obtener_reintentos_pendientes()
        if df is None or df.empty:
            return JSONResponse(content={"data": []})
        
        records = json.loads(df.to_json(orient="records", date_format="iso"))
        return {"data": records}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    # Ejecutamos el microservicio en el puerto 8000 (Streamlit corre en el 8501)
    uvicorn.run(app, host="127.0.0.1", port=8000)
