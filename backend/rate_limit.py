"""
Limitación de intentos de autenticación (OWASP A07, hallazgo S-07).

- Contadores por IP real y por nombre de usuario, en memoria (un solo worker).
- Tras max_intentos fallos en la ventana, la clave queda bloqueada durante
  bloqueo_segundos. Un login correcto reinicia el contador del usuario.
- La IP real se toma de X-Forwarded-For solo cuando la petición llega desde
  loopback (Streamlit en el mismo contenedor) y el valor es una IP válida.
"""
import ipaddress
import threading
from collections import defaultdict
from time import time
from typing import Optional

_LOOPBACK = ("127.0.0.1", "::1", "localhost")


class LimitadorIntentos:
    def __init__(self, max_intentos: int = 5, ventana_segundos: int = 300, bloqueo_segundos: int = 900):
        self.max_intentos = max_intentos
        self.ventana = ventana_segundos
        self.bloqueo = bloqueo_segundos
        self._fallos: dict = defaultdict(list)
        self._bloqueado_hasta: dict = {}
        self._lock = threading.Lock()

    def _purgar(self, clave: str, ahora: float) -> None:
        inicio = ahora - self.ventana
        self._fallos[clave] = [t for t in self._fallos[clave] if t > inicio]

    def segundos_bloqueo(self, clave: str, ahora: Optional[float] = None) -> int:
        """0 si la clave puede intentar; si no, segundos restantes de bloqueo."""
        ahora = ahora if ahora is not None else time()
        with self._lock:
            hasta = self._bloqueado_hasta.get(clave, 0)
            if hasta > ahora:
                return int(hasta - ahora) + 1
            if hasta:
                del self._bloqueado_hasta[clave]
                self._fallos.pop(clave, None)
            return 0

    def registrar_fallo(self, clave: str, ahora: Optional[float] = None) -> None:
        ahora = ahora if ahora is not None else time()
        with self._lock:
            self._purgar(clave, ahora)
            self._fallos[clave].append(ahora)
            if len(self._fallos[clave]) >= self.max_intentos:
                self._bloqueado_hasta[clave] = ahora + self.bloqueo

    def registrar_exito(self, clave: str) -> None:
        with self._lock:
            self._fallos.pop(clave, None)
            self._bloqueado_hasta.pop(clave, None)

    def limpiar(self) -> None:
        with self._lock:
            self._fallos.clear()
            self._bloqueado_hasta.clear()


def ip_valida(valor: str) -> Optional[str]:
    try:
        return str(ipaddress.ip_address(valor.strip()))
    except (ValueError, AttributeError):
        return None


def ip_cliente(host_directo: Optional[str], x_forwarded_for: Optional[str]) -> str:
    """Resuelve la IP real: X-Forwarded-For solo se confía desde loopback."""
    host = host_directo or "desconocido"
    if host in _LOOPBACK and x_forwarded_for:
        primera = x_forwarded_for.split(",")[0]
        candidata = ip_valida(primera)
        if candidata:
            return candidata
    return host
