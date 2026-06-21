from sqlalchemy.orm import Session
from . import models, schemas
from datetime import date, datetime
import bcrypt
import uuid

def get_password_hash(password: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))
    except Exception:
        return False

def get_licencia(db: Session, licencia_id: int):
    return db.query(models.Licencia).filter(models.Licencia.id == licencia_id).first()

def get_licencia_by_mail(db: Session, mail: str):
    return db.query(models.Licencia).filter(models.Licencia.mail == mail).first()

def get_licencias(db: Session, skip: int = 0, limit: int = 100):
    return db.query(models.Licencia).offset(skip).limit(limit).all()

def search_users(db: Session, query: str):
    return db.query(models.Licencia).filter(
        (models.Licencia.user.ilike(f"%{query}%")) | 
        (models.Licencia.name.ilike(f"%{query}%")) |
        (models.Licencia.mail.ilike(f"%{query}%"))
    ).all()

def create_licencia(db: Session, licencia: schemas.LicenciaCreate):
    db_licencia = models.Licencia(
        user=licencia.user,
        name=licencia.name,
        mail=licencia.mail,
        licence_id=licencia.licence_id,
        fecha_compra=licencia.fecha_compra,
        dias_vigencia=licencia.dias_vigencia,
        fecha_expiracion=licencia.fecha_expiracion,
        empresa=licencia.empresa,
        password_hash=get_password_hash(licencia.password)
    )
    db.add(db_licencia)
    db.commit()
    db.refresh(db_licencia)
    return db_licencia

def update_licencia(db: Session, licencia_id: int, licencia: schemas.LicenciaUpdate):
    db_licencia = db.query(models.Licencia).filter(models.Licencia.id == licencia_id).first()
    if db_licencia:
        update_data = licencia.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(db_licencia, key, value)
        db.commit()
        db.refresh(db_licencia)
    return db_licencia

def delete_licencia(db: Session, licencia_id: int):
    db_licencia = db.query(models.Licencia).filter(models.Licencia.id == licencia_id).first()
    if db_licencia:
        db.delete(db_licencia)
        db.commit()
        return True
    return False

def validate_auth(db: Session, username: str, password: str, mail: str = None):
    query = db.query(models.Licencia).filter(models.Licencia.user == username)
    if mail:
        query = query.filter(models.Licencia.mail == mail)
    
    db_licencia = query.first()
    if not db_licencia:
        return False, False, "No cuentas con ninguna licencia activa", None
    
    if not verify_password(password, db_licencia.password_hash):
        return True, False, "Contraseña incorrecta", None
    
    # Verificar fecha de expiración
    if db_licencia.fecha_expiracion < date.today():
        fecha_str = db_licencia.fecha_expiracion.strftime("%d/%m/%Y")
        return True, False, f"Tu licencia expiró el {fecha_str}", None
    
    # Generar nuevo session_id para control de sesión única
    new_session_id = uuid.uuid4()
    
    # IMPORTANTE: Ya no borramos los registros anteriores para mantener la bitácora histórica.
    # El control de sesión única se hará verificando si es la sesión más reciente.
    
    # Registrar la nueva sesión en la bitácora
    nueva_sesion = models.BitacoraSesions(
        sessionid=new_session_id,
        licenciaid=db_licencia.licence_id,
        last_activity=datetime.now()
    )
    db.add(nueva_sesion)
    db.commit()
    
    # Adjuntamos el sessionid al objeto temporalmente como string para el token
    db_licencia.current_session_id = str(new_session_id)
    
    return True, True, "Autenticación exitosa", db_licencia
