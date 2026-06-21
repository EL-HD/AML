import os
import logging
from collections import defaultdict
from time import time
from fastapi import FastAPI, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy import desc
from sqlalchemy.orm import Session
from typing import List
from backend import models, schemas, crud
from backend.database import SessionLocal, engine, get_db
import jwt
from datetime import datetime, timedelta, timezone

# Crear tablas si no existen
models.Base.metadata.create_all(bind=engine)

from fastapi.middleware.cors import CORSMiddleware

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Configuración JWT (C2 fix: falla si SECRET_KEY no está configurada) ---
SECRET_KEY = os.getenv("SECRET_KEY", "")
if not SECRET_KEY:
    raise RuntimeError(
        "SECRET_KEY no está configurada. "
        "Genere una clave segura: python -c \"import secrets; print(secrets.token_hex(32))\""
    )
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

app = FastAPI(
    title="Sovereign AML Auth API",
    description="API para la gestión de licencias y autenticación de usuarios.",
    version="1.0.0"
)

# --- CORS (A2 fix: orígenes restringidos, configurable por env var) ---
_raw_origins = os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:8501")
ALLOWED_ORIGINS = [o.strip() for o in _raw_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

# --- Rate limiting en memoria (A3 fix: protección básica contra fuerza bruta) ---
# Nota: para múltiples workers en producción, migrar a Redis.
_rl_store: dict = defaultdict(list)
_RL_MAX_ATTEMPTS = 5
_RL_WINDOW_SECONDS = 300  # 5 minutos

def _check_rate_limit(identifier: str) -> bool:
    now = time()
    window_start = now - _RL_WINDOW_SECONDS
    _rl_store[identifier] = [t for t in _rl_store[identifier] if t > window_start]
    if len(_rl_store[identifier]) >= _RL_MAX_ATTEMPTS:
        return False
    _rl_store[identifier].append(now)
    return True

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    # B1 fix: usar datetime.now(timezone.utc) en lugar del deprecated utcnow()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=15))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

async def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Sesión expirada o activa en otro dispositivo",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        session_id: str = payload.get("session_id")
        if username is None or session_id is None:
            raise credentials_exception
        token_data = schemas.TokenData(username=username, session_id=session_id)
    except jwt.PyJWTError:
        raise credentials_exception
    
    # 1. Buscar el registro de esta sesión específica
    current_session = db.query(models.BitacoraSesions).filter(models.BitacoraSesions.sessionid == token_data.session_id).first()
    if current_session is None:
        raise credentials_exception
    
    # 2. Verificar si es la sesión MÁS RECIENTE para esta licencia
    # Esto permite mantener el historial pero solo autorizar al último que entró
    latest_session = db.query(models.BitacoraSesions)\
        .filter(models.BitacoraSesions.licenciaid == current_session.licenciaid)\
        .order_by(desc(models.BitacoraSesions.last_activity))\
        .first()
    
    if latest_session is None or latest_session.sessionid != current_session.sessionid:
        raise credentials_exception
    
    # 3. Obtener el usuario asociado
    user = db.query(models.Licencia).filter(models.Licencia.licence_id == current_session.licenciaid).first()
    if user is None:
        raise credentials_exception
    return user

@app.middleware("http")
async def log_requests(request, call_next):
    try:
        return await call_next(request)
    except Exception as e:
        logger.error(f"Error procesando solicitud: {e}", exc_info=True)
        raise e

# --- Endpoint para obtener Token ---

@app.post("/token", response_model=schemas.Token)
def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    exists, is_active, message, user = crud.validate_auth(db, username=form_data.username, password=form_data.password)
    if not is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=message,
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.user, "session_id": user.current_session_id}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

# --- Endpoints de Licencias ---

@app.post("/licencias/", response_model=schemas.Licencia, status_code=status.HTTP_201_CREATED)
def create_licencia(licencia: schemas.LicenciaCreate, db: Session = Depends(get_db), current_user: models.Licencia = Depends(get_current_user)):
    db_licencia = crud.get_licencia_by_mail(db, mail=licencia.mail)
    if db_licencia:
        raise HTTPException(status_code=400, detail="El correo ya está registrado con una licencia.")
    return crud.create_licencia(db=db, licencia=licencia)

@app.get("/licencias/", response_model=List[schemas.Licencia])
def read_licencias(skip: int = 0, limit: int = 100, db: Session = Depends(get_db), current_user: models.Licencia = Depends(get_current_user)):
    return crud.get_licencias(db, skip=skip, limit=limit)

@app.get("/licencias/{mail}", response_model=schemas.Licencia)
def read_licencia(mail: str, db: Session = Depends(get_db), current_user: models.Licencia = Depends(get_current_user)):
    db_licencia = crud.get_licencia_by_mail(db, mail=mail)
    if db_licencia is None:
        raise HTTPException(status_code=404, detail="Licencia no encontrada.")
    return db_licencia

@app.put("/licencias/{licencia_id}", response_model=schemas.Licencia)
def update_licencia(licencia_id: int, licencia: schemas.LicenciaUpdate, db: Session = Depends(get_db), current_user: models.Licencia = Depends(get_current_user)):
    db_licencia = crud.update_licencia(db, licencia_id=licencia_id, licencia=licencia)
    if db_licencia is None:
        raise HTTPException(status_code=404, detail="Licencia no encontrada.")
    return db_licencia

@app.delete("/licencias/{licencia_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_licencia(licencia_id: int, db: Session = Depends(get_db), current_user: models.Licencia = Depends(get_current_user)):
    success = crud.delete_licencia(db, licencia_id=licencia_id)
    if not success:
        raise HTTPException(status_code=404, detail="Licencia no encontrada.")
    return None

# --- Endpoints de Usuarios ---

@app.get("/usuarios/", response_model=List[schemas.Licencia])
def search_users(q: str, db: Session = Depends(get_db), current_user: models.Licencia = Depends(get_current_user)):
    return crud.search_users(db, query=q)

# --- Endpoint de Autenticación ---

@app.post("/auth/validate", response_model=schemas.AuthResponse)
def validate_user(auth: schemas.AuthRequest, request: Request, db: Session = Depends(get_db)):
    client_ip = request.client.host if request.client else "unknown"
    if not _check_rate_limit(client_ip):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Demasiados intentos de autenticación. Intente nuevamente en 5 minutos."
        )

    exists, is_active, message, licencia = crud.validate_auth(db, username=auth.username, password=auth.password, mail=auth.mail)

    token = None
    if is_active and licencia:
        access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        token = create_access_token(
            data={"sub": licencia.user, "session_id": licencia.current_session_id}, expires_delta=access_token_expires
        )
    
    return {
        "exists": exists,
        "is_active": is_active,
        "message": message,
        "licencia": licencia,
        "access_token": token
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
