import os
import logging
from fastapi import FastAPI, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy import desc
from sqlalchemy.orm import Session
from typing import List
from backend import models, schemas, crud, auditoria
from backend.rate_limit import LimitadorIntentos, ip_cliente
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

# --- Limitación de intentos (S-07): por IP real y por usuario, con bloqueo temporal ---
# Nota: contadores en memoria (un worker). Para varios workers migrar a Redis.
_RL_MAX_ATTEMPTS = 5
_RL_WINDOW_SECONDS = 300
_RL_LOCK_SECONDS = 900
limitador = LimitadorIntentos(_RL_MAX_ATTEMPTS, _RL_WINDOW_SECONDS, _RL_LOCK_SECONDS)
MENSAJE_CREDENCIALES = "Credenciales inválidas"


def _claves_limite(request: Request, username: str):
    ip = ip_cliente(request.client.host if request.client else None,
                    request.headers.get("x-forwarded-for"))
    return f"ip:{ip}", f"user:{(username or '').strip().lower()[:100]}"


def _exigir_no_bloqueado(*claves: str) -> None:
    restante = max(limitador.segundos_bloqueo(c) for c in claves)
    if restante:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Demasiados intentos de autenticación. Intente nuevamente en {max(1, restante // 60)} minuto(s).",
            headers={"Retry-After": str(restante)},
        )


def _autenticar(db: Session, request: Request, username: str, password: str, mail: str = None):
    """Valida credenciales aplicando límite de intentos y auditoría. Devuelve (is_active, message, licencia)."""
    claves = _claves_limite(request, username)
    _exigir_no_bloqueado(*claves)
    exists, is_active, message, licencia = crud.validate_auth(db, username=username, password=password, mail=mail)
    if is_active and licencia:
        for clave in claves:
            limitador.registrar_exito(clave)
        auditoria.registrar_evento(db, licencia.licence_id, licencia.user,
                                   auditoria.MODULO_AUTENTICACION, auditoria.LOGIN_OK)
        return True, message, licencia
    for clave in claves:
        limitador.registrar_fallo(clave)
    if exists:
        registro = crud.get_licencia_by_user(db, username)
        if registro is not None:
            auditoria.registrar_evento(db, registro.licence_id, registro.user,
                                       auditoria.MODULO_AUTENTICACION, auditoria.LOGIN_FALLIDO)
    logger.warning("Intento de autenticación fallido (usuario=%s, origen=%s)", username, claves[0])
    return False, message, None


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
    
    user = crud.sesion_vigente(db, token_data.session_id)
    if user is None:
        raise credentials_exception
    return user

def require_role(*roles: str):
    """Dependencia FastAPI: exige que el usuario autenticado tenga uno de los roles indicados."""
    roles_permitidos = frozenset(roles)

    async def _verificar(current_user: models.Licencia = Depends(get_current_user)) -> models.Licencia:
        if getattr(current_user, "rol", None) not in roles_permitidos:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tiene permisos para realizar esta operación.",
            )
        return current_user

    return _verificar


solo_admin = require_role("admin")


@app.middleware("http")
async def log_requests(request, call_next):
    try:
        return await call_next(request)
    except Exception as e:
        logger.error(f"Error procesando solicitud: {e}", exc_info=True)
        raise e

# --- Endpoint para obtener Token ---

@app.post("/token", response_model=schemas.Token)
def login_for_access_token(request: Request, form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    is_active, message, user = _autenticar(db, request, form_data.username, form_data.password)
    if not is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=message,
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = create_access_token(
        data={"sub": user.user, "session_id": user.current_session_id},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    return {"access_token": access_token, "token_type": "bearer"}

# --- Endpoints de Licencias ---

@app.post("/licencias/", response_model=schemas.Licencia, status_code=status.HTTP_201_CREATED)
def create_licencia(licencia: schemas.LicenciaCreate, db: Session = Depends(get_db), current_user: models.Licencia = Depends(solo_admin)):
    db_licencia = crud.get_licencia_by_mail(db, mail=licencia.mail)
    if db_licencia:
        raise HTTPException(status_code=400, detail="El correo ya está registrado con una licencia.")
    return crud.create_licencia(db=db, licencia=licencia)

@app.get("/licencias/", response_model=List[schemas.Licencia])
def read_licencias(skip: int = 0, limit: int = 100, db: Session = Depends(get_db), current_user: models.Licencia = Depends(solo_admin)):
    return crud.get_licencias(db, skip=skip, limit=limit)

@app.get("/licencias/{mail}", response_model=schemas.Licencia)
def read_licencia(mail: str, db: Session = Depends(get_db), current_user: models.Licencia = Depends(solo_admin)):
    db_licencia = crud.get_licencia_by_mail(db, mail=mail)
    if db_licencia is None:
        raise HTTPException(status_code=404, detail="Licencia no encontrada.")
    return db_licencia

@app.put("/licencias/{licencia_id}", response_model=schemas.Licencia)
def update_licencia(licencia_id: int, licencia: schemas.LicenciaUpdate, db: Session = Depends(get_db), current_user: models.Licencia = Depends(solo_admin)):
    db_licencia = crud.update_licencia(db, licencia_id=licencia_id, licencia=licencia)
    if db_licencia is None:
        raise HTTPException(status_code=404, detail="Licencia no encontrada.")
    return db_licencia

@app.delete("/licencias/{licencia_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_licencia(licencia_id: int, db: Session = Depends(get_db), current_user: models.Licencia = Depends(solo_admin)):
    success = crud.delete_licencia(db, licencia_id=licencia_id)
    if not success:
        raise HTTPException(status_code=404, detail="Licencia no encontrada.")
    return None

# --- Perfil propio (cualquier rol autenticado; campos restringidos) ---

@app.get("/perfil", response_model=schemas.Licencia)
def read_perfil(current_user: models.Licencia = Depends(get_current_user)):
    return current_user

@app.put("/perfil", response_model=schemas.Licencia)
def update_perfil(perfil: schemas.PerfilUpdate, db: Session = Depends(get_db), current_user: models.Licencia = Depends(get_current_user)):
    return crud.update_licencia(db, licencia_id=current_user.id, licencia=perfil)

# --- Endpoints de Usuarios ---

@app.get("/usuarios/", response_model=List[schemas.Licencia])
def search_users(q: str, db: Session = Depends(get_db), current_user: models.Licencia = Depends(solo_admin)):
    return crud.search_users(db, query=q)

# --- Endpoint de Autenticación ---

@app.post("/auth/validate", response_model=schemas.AuthResponse)
def validate_user(auth: schemas.AuthRequest, request: Request, db: Session = Depends(get_db)):
    is_active, message, licencia = _autenticar(db, request, auth.username, auth.password, mail=auth.mail)
    token = None
    if is_active and licencia:
        token = create_access_token(
            data={"sub": licencia.user, "session_id": licencia.current_session_id},
            expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
        )
    return {
        "exists": is_active,
        "is_active": is_active,
        "message": message,
        "licencia": licencia,
        "access_token": token,
        "session_id": licencia.current_session_id if (is_active and licencia) else None,
    }


@app.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(current_user: models.Licencia = Depends(get_current_user), db: Session = Depends(get_db)):
    auditoria.registrar_evento(db, current_user.licence_id, current_user.user,
                               auditoria.MODULO_AUTENTICACION, auditoria.LOGOUT)
    return None

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
