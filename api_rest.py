from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from base_datos import GestorBaseDatos

app = FastAPI(
    title="API REST TFG Opciones",
    description="Microservicio de monitorización para el sistema algorítmico de opciones.",
    version="2.0.0"
)

db = GestorBaseDatos()

@app.get("/health", summary="Comprobar estado del servidor")
def health_check():
    return {"status": "ok", "message": "API de monitorización activa y escuchando"}

@app.get("/operaciones", summary="Obtener historial de operaciones")
def obtener_operaciones(limit: int = 50):
    try:
        df = db.obtener_operaciones()
        if df is None or df.empty:
            return JSONResponse(content={"data": []})
        
        # Convertimos el DataFrame a una lista de diccionarios JSON nativa
        records = df.tail(limit).to_dict(orient="records")
        return {"data": records}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/auditoria", summary="Obtener logs de auditoría (Watchdog y motor)")
def obtener_auditoria(limit: int = 50):
    try:
        df = db.obtener_auditoria()
        if df is None or df.empty:
            return JSONResponse(content={"data": []})
        
        records = df.tail(limit).to_dict(orient="records")
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
        
        records = df.to_dict(orient="records")
        return {"data": records}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    # Ejecutamos el microservicio en el puerto 8000 (Streamlit corre en el 8501)
    uvicorn.run(app, host="127.0.0.1", port=8000)
