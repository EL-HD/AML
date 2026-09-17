"""
Política de contraseñas (OWASP A07, hallazgo S-11).

Reglas: mínimo 12 caracteres, al menos una mayúscula, una minúscula, un dígito
y un símbolo; se rechazan contraseñas comunes (lista local) y las que contienen
el nombre de usuario. MFA (TOTP con pyotp) queda documentado como fase posterior.
"""
import re
from typing import Optional

LONGITUD_MINIMA = 12
LONGITUD_MAXIMA = 128

# Lista local de contraseñas y raíces comunes (comparación sin distinguir mayúsculas).
_COMUNES = {
    "123456789012", "password1234", "contraseña123", "qwertyuiop12", "administrador",
    "admin1234567", "welcome12345", "bienvenido123", "sovereignaml", "sovereign123",
    "guatemala2026", "guatemala123", "password2026", "passw0rd1234", "letmein12345",
    "iloveyou1234", "abc123456789", "111111111111", "000000000000", "aml123456789",
}
_RAICES_COMUNES = ("password", "contraseña", "qwerty", "123456", "admin", "letmein", "welcome")


def validar_password(password: str, username: Optional[str] = None) -> None:
    """Lanza ValueError con un mensaje claro si la contraseña no cumple la política."""
    if not isinstance(password, str):
        raise ValueError("La contraseña debe ser texto.")
    if len(password) < LONGITUD_MINIMA:
        raise ValueError(f"La contraseña debe tener al menos {LONGITUD_MINIMA} caracteres.")
    if len(password) > LONGITUD_MAXIMA:
        raise ValueError(f"La contraseña no puede superar {LONGITUD_MAXIMA} caracteres.")
    if not re.search(r"[A-ZÁÉÍÓÚÑ]", password):
        raise ValueError("La contraseña debe incluir al menos una letra mayúscula.")
    if not re.search(r"[a-záéíóúñ]", password):
        raise ValueError("La contraseña debe incluir al menos una letra minúscula.")
    if not re.search(r"\d", password):
        raise ValueError("La contraseña debe incluir al menos un número.")
    if not re.search(r"[^\w\s]|_", password):
        raise ValueError("La contraseña debe incluir al menos un símbolo (por ejemplo ! # $ % & * ? @).")
    normalizada = password.lower()
    if normalizada in _COMUNES or any(normalizada.startswith(r) for r in _RAICES_COMUNES):
        raise ValueError("La contraseña es demasiado común; elija una más difícil de adivinar.")
    if username and len(username) >= 3 and username.lower() in normalizada:
        raise ValueError("La contraseña no debe contener el nombre de usuario.")
