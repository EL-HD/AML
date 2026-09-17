import os
import logging
import threading
from fastapi import FastAPI, Depends, Form, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy import desc
from sqlalchemy.orm import Session
from typing import List, Optional
from backend import models, schemas, crud, auditoria, mfa
from backend.rate_limit import LimitadorIntentos, ip_cliente
from backend.database import SessionLocal, engine, get_db
import jwt
import uuid
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
# Token intermedio de MFA (T6): corta vida, un solo uso, sin acceso a ningún recurso.
MFA_TOKEN_EXPIRE_MINUTES = 5
TIPO_TOKEN_ACCESO = "acceso"
TIPO_TOKEN_MFA = "mfa"
MENSAJE_MFA_REQUERIDO = "Se requiere el segundo factor de autenticación (MFA)."
MENSAJE_MFA_INVALIDO = "Código MFA inválido o expirado."
JWT_ISSUER = os.getenv("JWT_ISSUER", "sovereign-aml-auth")
JWT_AUDIENCE = os.getenv("JWT_AUDIENCE", "sovereign-aml-app")

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


def _claves_limite(request: Request, username: str, prefijo: str = "user"):
    ip = ip_cliente(request.client.host if request.client else None,
                    request.headers.get("x-forwarded-for"))
    return f"ip:{ip}", f"{prefijo}:{(username or '').strip().lower()[:100]}"


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

def create_access_token(data: dict, expires_delta: timedelta = None, tipo: str = TIPO_TOKEN_ACCESO):
    """JWT con exp, iat, jti (identificador único), iss, aud (S-15) y typ (acceso | mfa)."""
    to_encode = data.copy()
    ahora = datetime.now(timezone.utc)
    to_encode.update({
        "exp": ahora + (expires_delta or timedelta(minutes=15)),
        "iat": ahora,
        "jti": uuid.uuid4().hex,
        "iss": JWT_ISSUER,
        "aud": JWT_AUDIENCE,
        "typ": tipo,
    })
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def _token_final(licencia) -> str:
    return create_access_token(
        data={"sub": licencia.user, "session_id": licencia.current_session_id},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )


def _token_mfa(licencia) -> str:
    """Token intermedio: solo canjeable en /auth/mfa/verificar, 5 minutos, un solo uso (jti)."""
    return create_access_token(
        data={"sub": licencia.user, "session_id": licencia.current_session_id},
        expires_delta=timedelta(minutes=MFA_TOKEN_EXPIRE_MINUTES), tipo=TIPO_TOKEN_MFA,
    )


def _decodificar(token: str, tipo_esperado: str) -> Optional[dict]:
    """Decodifica y valida firma, emisor, audiencia, vigencia y tipo. None si no es válido."""
    try:
        payload = jwt.decode(
            token, SECRET_KEY, algorithms=[ALGORITHM],
            issuer=JWT_ISSUER, audience=JWT_AUDIENCE,
            options={"require": ["exp", "iat", "jti", "iss", "aud", "sub", "typ"]},
        )
    except jwt.PyJWTError:
        return None
    if payload.get("typ") != tipo_esperado or not payload.get("sub") or not payload.get("session_id"):
        return None
    return payload


# Registro en memoria de tokens MFA ya canjeados (jti -> expiración). Un solo worker,
# como el limitador de intentos; con varios workers migrar a Redis.
_mfa_jti_usados: dict = {}
_mfa_jti_lock = threading.Lock()


def _jti_mfa_canjeado(jti: str) -> bool:
    ahora = datetime.now(timezone.utc).timestamp()
    with _mfa_jti_lock:
        for usado, vence in list(_mfa_jti_usados.items()):
            if vence <= ahora:
                del _mfa_jti_usados[usado]
        return jti in _mfa_jti_usados


def _marcar_jti_mfa(jti: str, exp: float) -> None:
    """Se marca solo al canjearse con éxito: un intento fallido no invalida el token
    (el límite de intentos acota la fuerza bruta), pero un canje exitoso sí (un solo uso)."""
    with _mfa_jti_lock:
        _mfa_jti_usados[jti] = float(exp)


def _usuario_desde_token(token: str, db: Session, exigir_mfa_completo: bool):
    """
    Resuelve el usuario de un JWT de acceso. Siempre exige sesión vigente y que la
    sesión haya superado el MFA cuando el usuario lo tiene activo. Con
    exigir_mfa_completo también rechaza a quien deba enrolar (MFA_ENFORCE).
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Sesión expirada o activa en otro dispositivo",
        headers={"WWW-Authenticate": "Bearer"},
    )
    payload = _decodificar(token, TIPO_TOKEN_ACCESO)
    if payload is None:
        raise credentials_exception
    user = crud.sesion_vigente(db, payload["session_id"])
    if user is None or not mfa.sesion_autorizada(db, user, payload["session_id"]):
        raise credentials_exception
    user.current_session_id = payload["session_id"]
    if exigir_mfa_completo and mfa.enrolamiento_pendiente(db, user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Debe enrolar el segundo factor (MFA) antes de usar el sistema: POST /auth/mfa/enrolar.",
        )
    return user


async def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    return _usuario_desde_token(token, db, exigir_mfa_completo=True)


async def get_usuario_para_mfa(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    """Igual que get_current_user pero admite a quien aún debe enrolar (solo endpoints de MFA)."""
    return _usuario_desde_token(token, db, exigir_mfa_completo=False)

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
def login_for_access_token(request: Request, form_data: OAuth2PasswordRequestForm = Depends(),
                           codigo_mfa: Optional[str] = Form(None, max_length=16),
                           db: Session = Depends(get_db)):
    """Flujo OAuth2 password. Con MFA activo el código TOTP o de recuperación viaja en `codigo_mfa`."""
    is_active, message, user = _autenticar(db, request, form_data.username, form_data.password)
    if not is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=message,
            headers={"WWW-Authenticate": "Bearer"},
        )
    if mfa.esta_activo(db, user.licence_id):
        claves = _claves_limite(request, user.user, prefijo="mfa")
        _exigir_no_bloqueado(*claves)
        if not codigo_mfa or not mfa.verificar(db, user, codigo_mfa, user.current_session_id):
            for clave in claves:
                limitador.registrar_fallo(clave)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=MENSAJE_MFA_REQUERIDO if not codigo_mfa else MENSAJE_MFA_INVALIDO,
                headers={"WWW-Authenticate": "Bearer"},
            )
        for clave in claves:
            limitador.registrar_exito(clave)
    return {"access_token": _token_final(user), "token_type": "bearer"}

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
    if not (is_active and licencia):
        return {"exists": is_active, "is_active": is_active, "message": message}
    if mfa.esta_activo(db, licencia.licence_id):
        # Primer factor correcto: solo se entrega el token intermedio, sin licencia ni sesión.
        return {
            "exists": True, "is_active": False, "message": MENSAJE_MFA_REQUERIDO,
            "mfa_requerido": True, "mfa_token": _token_mfa(licencia),
        }
    return _respuesta_autenticada(db, licencia)


def _respuesta_autenticada(db: Session, licencia) -> dict:
    return {
        "exists": True,
        "is_active": True,
        "message": "Autenticación exitosa",
        "licencia": licencia,
        "access_token": _token_final(licencia),
        "session_id": licencia.current_session_id,
        "mfa_enrolamiento_pendiente": mfa.enrolamiento_pendiente(db, licencia),
    }


# --- MFA TOTP (T6) ---

@app.post("/auth/mfa/verificar", response_model=schemas.AuthResponse)
def mfa_verificar(datos: schemas.MfaVerificarRequest, request: Request, db: Session = Depends(get_db)):
    """Canjea el token intermedio más un código TOTP o de recuperación por el JWT final."""
    payload = _decodificar(datos.mfa_token, TIPO_TOKEN_MFA)
    if payload is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=MENSAJE_MFA_INVALIDO)
    claves = _claves_limite(request, payload["sub"], prefijo="mfa")
    _exigir_no_bloqueado(*claves)
    licencia = crud.sesion_vigente(db, payload["session_id"])
    if licencia is None or licencia.user != payload["sub"] or not mfa.esta_activo(db, licencia.licence_id):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=MENSAJE_MFA_INVALIDO)
    if _jti_mfa_canjeado(payload["jti"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=MENSAJE_MFA_INVALIDO)
    if not mfa.verificar(db, licencia, datos.codigo, payload["session_id"]):
        for clave in claves:
            limitador.registrar_fallo(clave)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=MENSAJE_MFA_INVALIDO)
    _marcar_jti_mfa(payload["jti"], payload["exp"])
    for clave in claves:
        limitador.registrar_exito(clave)
    licencia.current_session_id = payload["session_id"]
    return _respuesta_autenticada(db, licencia)


@app.get("/auth/mfa/estado", response_model=schemas.MfaEstado)
def mfa_estado(db: Session = Depends(get_db), current_user: models.Licencia = Depends(get_usuario_para_mfa)):
    return mfa.estado(db, current_user).como_dict()


@app.post("/auth/mfa/enrolar", response_model=schemas.MfaEnrolamiento)
def mfa_enrolar(db: Session = Depends(get_db), current_user: models.Licencia = Depends(get_usuario_para_mfa)):
    """Genera el secreto (cifrado en BD, inactivo) y devuelve la URI otpauth y la clave manual."""
    try:
        return mfa.iniciar_enrolamiento(db, current_user)
    except mfa.MfaError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))


@app.post("/auth/mfa/confirmar", response_model=schemas.MfaCodigosRecuperacion)
def mfa_confirmar(datos: schemas.MfaCodigoRequest, request: Request, db: Session = Depends(get_db),
                  current_user: models.Licencia = Depends(get_usuario_para_mfa)):
    """Activa el MFA con un código válido del autenticador; devuelve los códigos de recuperación una sola vez."""
    claves = _claves_limite(request, current_user.user, prefijo="mfa")
    _exigir_no_bloqueado(*claves)
    try:
        codigos = mfa.confirmar_enrolamiento(db, current_user, datos.codigo,
                                             session_id=current_user.current_session_id)
    except mfa.MfaError as exc:
        for clave in claves:
            limitador.registrar_fallo(clave)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    for clave in claves:
        limitador.registrar_exito(clave)
    return {
        "codigos_recuperacion": codigos,
        "mensaje": "Guarde estos códigos en un lugar seguro: no volverán a mostrarse y cada uno sirve una sola vez.",
    }


@app.post("/auth/mfa/restablecer", status_code=status.HTTP_204_NO_CONTENT)
def mfa_restablecer_propio(datos: schemas.MfaCodigoRequest, request: Request, db: Session = Depends(get_db),
                           current_user: models.Licencia = Depends(get_current_user)):
    """El propio usuario retira su MFA con un código válido (para cambiar de dispositivo)."""
    claves = _claves_limite(request, current_user.user, prefijo="mfa")
    _exigir_no_bloqueado(*claves)
    try:
        mfa.restablecer_propio(db, current_user, datos.codigo)
    except mfa.MfaError as exc:
        for clave in claves:
            limitador.registrar_fallo(clave)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return None


@app.post("/auth/mfa/restablecer/{licencia_id}", status_code=status.HTTP_204_NO_CONTENT)
def mfa_restablecer_usuario(licencia_id: int, db: Session = Depends(get_db),
                            current_user: models.Licencia = Depends(solo_admin)):
    """Un administrador restablece el MFA de otro usuario (auditado). No permite el propio."""
    objetivo = crud.get_licencia(db, licencia_id)
    if objetivo is None:
        raise HTTPException(status_code=404, detail="Licencia no encontrada.")
    try:
        mfa.restablecer_por_admin(db, current_user, objetivo)
    except mfa.MfaError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return None


@app.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(current_user: models.Licencia = Depends(get_current_user), db: Session = Depends(get_db)):
    auditoria.registrar_evento(db, current_user.licence_id, current_user.user,
                               auditoria.MODULO_AUTENTICACION, auditoria.LOGOUT)
    return None

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
