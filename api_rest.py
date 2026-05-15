from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.responses import JSONResponse, RedirectResponse, HTMLResponse
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from base_datos import GestorBaseDatos
from datetime import datetime, timedelta, timezone
from jose import JWTError, jwt
import hashlib
import json

# ==========================================
# CONFIGURACIÓN DE SEGURIDAD JWT
# ==========================================
SECRET_KEY = "mi_secreto_super_seguro_tfg" # En producción usar variable de entorno
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# Credenciales maestras (de app_web.py)
ADMIN_USER = "admin"
ADMIN_PASSWORD_HASH = "6051fc84a7a0d74c225fb18a496b09952da5642e60723ecae543298edd7d82d6"

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

def verificar_password(plain_password: str) -> bool:
    """Verifica la contraseña plana contra el hash SHA-256."""
    hash_input = hashlib.sha256(plain_password.encode()).hexdigest()
    return hash_input == ADMIN_PASSWORD_HASH

def crear_token_acceso(data: dict, expires_delta: timedelta | None = None):
    """Crea un token JWT con tiempo de expiración."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

async def obtener_usuario_actual(token: str = Depends(oauth2_scheme)):
    """Dependencia que valida el JWT y extrae el usuario actual."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="No se pudieron validar las credenciales",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
        
    if username != ADMIN_USER:
        raise credentials_exception
        
    return username

# ==========================================
# DEFINICIÓN DE LA API REST
# ==========================================
app = FastAPI(
    title="API REST TFG Opciones",
    description="Microservicio de monitorización para el sistema algorítmico de opciones.",
    version="3.0.0",
    docs_url=None  # Desactivamos los docs por defecto para personalizarlos
)

db = GestorBaseDatos()

@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui_html():
    """Sobreescribimos la UI de Swagger para inyectar CSS personalizado y cambiar colores del candado."""
    html_response = get_swagger_ui_html(
        openapi_url=app.openapi_url,
        title=app.title + " - Swagger UI",
        oauth2_redirect_url=app.swagger_ui_oauth2_redirect_url,
        swagger_js_url="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js",
        swagger_css_url="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css",
    )
    
    # Extraemos el HTML generado por FastAPI
    html = html_response.body.decode("utf-8")
    
    # Inyectamos nuestro CSS personalizado para colorear el botón "Authorize"
    custom_css = """
    <style>
    /* Candado abierto = Rojo */
    .swagger-ui .btn.authorize.unlocked {
        border-color: #d93a3a !important;
        color: #d93a3a !important;
    }
    .swagger-ui .btn.authorize.unlocked svg {
        fill: #d93a3a !important;
    }
    /* Candado cerrado = Verde */
    .swagger-ui .btn.authorize.locked {
        border-color: #4caf50 !important;
        color: #4caf50 !important;
    }
    .swagger-ui .btn.authorize.locked svg {
        fill: #4caf50 !important;
    }
    </style>
    """
    html = html.replace("</head>", f"{custom_css}</head>")
    return HTMLResponse(html)

@app.post("/token", summary="Obtener JWT para acceso")
def login(form_data: OAuth2PasswordRequestForm = Depends()):
    """Endpoint para autenticarse y obtener un token JWT."""
    if form_data.username != ADMIN_USER or not verificar_password(form_data.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales incorrectas",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = crear_token_acceso(
        data={"sub": form_data.username}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/", include_in_schema=False)
def raiz():
    """Redirige automáticamente la raíz a la página de documentación."""
    return RedirectResponse(url="/docs")

@app.get("/health", summary="Comprobar estado del servidor")
def health_check():
    """Ruta pública para comprobar que la API está viva."""
    return {"status": "ok", "message": "API de monitorización activa y escuchando"}

@app.get("/operaciones", summary="Obtener historial de operaciones")
def obtener_operaciones(limit: int = 50, current_user: str = Depends(obtener_usuario_actual)):
    """Ruta protegida que devuelve el historial de operaciones."""
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
def obtener_auditoria(limit: int = 50, current_user: str = Depends(obtener_usuario_actual)):
    """Ruta protegida que devuelve el historial de auditoría y eventos."""
    try:
        df = db.obtener_logs()
        if df is None or df.empty:
            return JSONResponse(content={"data": []})
        
        records = json.loads(df.tail(limit).to_json(orient="records", date_format="iso"))
        return {"data": records}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/cola-reintentos", summary="Ver órdenes estancadas en el Watchdog")
def obtener_cola(current_user: str = Depends(obtener_usuario_actual)):
    """Ruta protegida que devuelve la cola de reintentos."""
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
