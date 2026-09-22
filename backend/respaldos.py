"""
Respaldos cifrados de la base de datos (T7).

Módulo compartido por `scripts/respaldo_bd.py` y `scripts/restaurar_bd.py`.
Depende únicamente de la biblioteca estándar, de `cryptography` y de las
herramientas de cliente de PostgreSQL (`pg_dump`, `pg_restore`, `psql`); no
requiere driver Python (psycopg2) para poder ejecutarse en un servicio cron
mínimo.

Diseño:
- Conexión: la contraseña nunca viaja en la línea de comandos ni en los
  registros. Se entrega a los procesos hijo mediante variables `PG*` en su
  entorno (no en el del proceso padre) y toda URL que se imprima pasa por
  `url_sin_credenciales`.
- Cifrado: AES-256-GCM por bloques (4 MiB) con clave derivada por HKDF de
  `BACKUP_ENCRYPTION_KEY` (clave en formato Fernet: 32 bytes en base64 url
  safe). Se eligió cifrado en streaming en lugar de Fernet porque Fernet exige
  cargar el archivo completo en memoria y lo expande un 33 % (base64); un
  volcado de producción puede pesar cientos de MB y el cron corre con memoria
  limitada. Cada bloque lleva su etiqueta de autenticidad; el contador de
  bloque y la marca de "último bloque" forman parte de los datos autenticados,
  de modo que un bloque reordenado, repetido o un archivo truncado se detecta.
- Manifiesto: JSON con fecha UTC, tamaños, SHA-256 (del volcado en claro y del
  archivo cifrado), migraciones aplicadas (`schema_migrations`) y el último
  eslabón de la cadena de auditoría por licencia (T4) como ancla externa. El
  manifiesto se firma con HMAC-SHA256 (clave derivada de la misma clave
  maestra) para detectar su alteración.
- Retención: esquema abuelo-padre-hijo (diaria, semanal, mensual) sin borrar
  nunca el respaldo válido más reciente.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import shutil
import struct
import subprocess  # nosec B404: se invocan binarios fijos sin shell
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional
from urllib.parse import parse_qs, unquote, urlsplit

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

MAGIA = b"SAMLBK01"
TAMANO_BLOQUE = 4 * 1024 * 1024
INFO_CIFRADO = b"sovereign-aml-respaldo-aes256gcm-v1"
INFO_FIRMA = b"sovereign-aml-manifiesto-hmac-v1"
VERSION_MANIFIESTO = 1
ALGORITMO_CIFRADO = "aes-256-gcm-bloques-4MiB"
SUFIJO_CIFRADO = ".dump.enc"
SUFIJO_MANIFIESTO = ".manifest.json"
PREFIJO_RESPALDO = "respaldo_"
PATRON_NOMBRE = re.compile(r"^respaldo_(\d{8}T\d{6}Z)$")
_MARCA_CREDENCIAL = re.compile(r"://([^/@:]+):([^/@]+)@")
LONGITUD_MINIMA_SECRETO = 6
HOSTS_PRODUCCION_DEFECTO = (".railway.internal", ".rlwy.net", ".railway.app")

logger = logging.getLogger("sovereign_aml.respaldos")


# ---------------------------------------------------------------------------
# Errores
# ---------------------------------------------------------------------------
class RespaldoError(Exception):
    """Error controlado del proceso de respaldo o restauración."""


class ClaveInvalidaError(RespaldoError):
    """La clave de cifrado falta o no tiene el formato esperado."""


class IntegridadError(RespaldoError):
    """El archivo cifrado, el hash o el manifiesto no superan la verificación."""


class ProduccionProtegidaError(RespaldoError):
    """Se intentó restaurar sobre la base de producción sin la doble confirmación."""


# ---------------------------------------------------------------------------
# Conexión y ocultamiento de credenciales
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Conexion:
    host: str
    puerto: str
    usuario: str
    password: str = field(repr=False)
    base: str
    sslmode: Optional[str] = None

    def entorno_pg(self) -> dict:
        """Variables PG* para procesos hijo. Nunca se exporta al proceso padre."""
        env = {
            "PGHOST": self.host,
            "PGPORT": self.puerto,
            "PGUSER": self.usuario,
            "PGDATABASE": self.base,
            "PGCONNECT_TIMEOUT": "30",
        }
        if self.password:
            env["PGPASSWORD"] = self.password
        if self.sslmode:
            env["PGSSLMODE"] = self.sslmode
        return env

    def con_base(self, base: str) -> "Conexion":
        return Conexion(self.host, self.puerto, self.usuario, self.password, base, self.sslmode)

    def descripcion(self) -> str:
        return f"{self.usuario}@{self.host}:{self.puerto}/{self.base}"

    def __str__(self) -> str:  # pragma: no cover - defensa contra impresiones accidentales
        return self.descripcion()


def url_sin_credenciales(url: str) -> str:
    """Devuelve la URL con usuario y contraseña sustituidos por '***'."""
    return _MARCA_CREDENCIAL.sub("://***:***@", url or "")


def parsear_database_url(url: str) -> Conexion:
    """Descompone una URL postgresql:// en sus partes sin exponerlas."""
    if not url or not isinstance(url, str):
        raise RespaldoError("DATABASE_URL vacía: no se puede conectar.")
    partes = urlsplit(url.strip())
    if partes.scheme not in ("postgresql", "postgres", "postgresql+psycopg2"):
        raise RespaldoError(
            f"Esquema de conexión no soportado: '{partes.scheme}'. Se espera postgresql://."
        )
    base = partes.path.lstrip("/")
    if not base:
        raise RespaldoError("La URL de conexión no indica el nombre de la base de datos.")
    _validar_identificador_base(base)
    consulta = parse_qs(partes.query)
    sslmode = consulta.get("sslmode", [None])[0]
    return Conexion(
        host=partes.hostname or "localhost",
        puerto=str(partes.port or 5432),
        usuario=unquote(partes.username or "postgres"),
        password=unquote(partes.password or ""),
        base=base,
        sslmode=sslmode,
    )


def conexion_desde_entorno(env: Optional[dict] = None) -> Conexion:
    """DATABASE_URL o, en su defecto, DB_HOST/DB_PORT/DB_USER/DB_PASS/DB_NAME (como backend/database.py)."""
    env = os.environ if env is None else env
    url = env.get("DATABASE_URL", "").strip()
    if url:
        return parsear_database_url(url)
    base = env.get("DB_NAME", "AML")
    _validar_identificador_base(base)
    return Conexion(
        host=env.get("DB_HOST", "localhost"),
        puerto=str(env.get("DB_PORT", "5432")),
        usuario=env.get("DB_USER", "postgres"),
        password=env.get("DB_PASS", ""),
        base=base,
        sslmode=env.get("DB_SSLMODE") or None,
    )


def _validar_identificador_base(nombre: str) -> None:
    if not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_\-]{0,62}", nombre or ""):
        raise RespaldoError(f"Nombre de base de datos inválido: '{nombre}'.")


class FiltroSinSecretos(logging.Filter):
    """Filtro de logging que oculta credenciales embebidas en URLs y valores marcados."""

    def __init__(self, secretos: Iterable[str] = ()):
        super().__init__()
        # Solo secretos de 6+ caracteres: uno más corto degradaría cualquier texto que lo contenga
        # (las URL completas ya se enmascaran siempre con url_sin_credenciales).
        self._secretos = [s for s in secretos if s and len(s) >= LONGITUD_MINIMA_SECRETO]

    def filter(self, record: logging.LogRecord) -> bool:
        mensaje = record.getMessage()
        limpio = url_sin_credenciales(mensaje)
        for secreto in self._secretos:
            limpio = limpio.replace(secreto, "***")
        record.msg = limpio
        record.args = ()
        return True


# ---------------------------------------------------------------------------
# Saneamiento de entradas externas (rutas, registros y argumentos de proceso)
# ---------------------------------------------------------------------------
# Este módulo lo usan herramientas de línea de comandos que reciben rutas del
# operador y leen manifiestos JSON de origen externo. Aunque quien ejecuta los
# scripts ya posee acceso al sistema, las tres funciones siguientes aplican
# defensa en profundidad y dejan la validación explícita y auditable:
#   - ruta_segura: normaliza y confina rutas (Path Traversal, pythonsecurity:S2083)
#   - texto_para_log: neutraliza saltos de línea y control (Log Injection, S5145)
#   - _validar_argv: confina el ejecutable y los argumentos (Command Argument
#     Injection, S6350)
# Un manifiesto manipulado no debe poder falsificar líneas en la bitácora de
# una restauración: en un expediente de cumplimiento el registro es evidencia.

EJECUTABLES_PERMITIDOS = ("pg_dump", "pg_restore", "psql")
VARIABLE_RUTAS_PERMITIDAS = "BACKUP_RUTAS_PERMITIDAS"
LIMITE_TEXTO_LOG = 200


def bases_permitidas() -> list:
    """Directorios bajo los cuales se aceptan rutas de respaldo.

    Por defecto: el directorio de trabajo, el temporal del sistema y el
    directorio `backups` del proyecto. Se amplía con la variable de entorno
    BACKUP_RUTAS_PERMITIDAS (rutas absolutas separadas por comas) para
    despliegues que guardan los respaldos en un volumen propio.
    """
    crudo = os.environ.get(VARIABLE_RUTAS_PERMITIDAS, "")
    extra = [Path(x.strip()) for x in crudo.split(",") if x.strip()]
    base_proyecto = Path(__file__).resolve().parent.parent
    candidatas = [Path.cwd(), Path(tempfile.gettempdir()), base_proyecto / "backups", *extra]
    resueltas = []
    for c in candidatas:
        try:
            resueltas.append(c.resolve())
        except OSError:
            continue
    return resueltas


def ruta_segura(ruta, *, debe_existir: bool = False, para_escritura: bool = False) -> Path:
    """Normaliza una ruta recibida del exterior y verifica que no escape.

    Rechaza cadenas vacías, caracteres nulos o de control, y toda ruta que tras
    resolver enlaces simbólicos y componentes ".." quede fuera de los
    directorios de bases_permitidas(). Devuelve siempre la ruta ya resuelta,
    que es la que debe usarse para abrir el archivo: validar una ruta y abrir
    otra distinta anularía la comprobación.
    """
    if ruta is None:
        raise RespaldoError("Ruta de archivo no proporcionada.")
    texto = str(ruta)
    if not texto.strip():
        raise RespaldoError("Ruta de archivo vacía.")
    if "\x00" in texto or any(ord(c) < 32 for c in texto):
        raise RespaldoError("La ruta contiene caracteres no permitidos.")
    try:
        resuelta = Path(texto).expanduser().resolve()
    except (OSError, RuntimeError) as exc:
        raise RespaldoError(f"Ruta de archivo inválida: {texto!r}.") from exc
    permitidas = bases_permitidas()
    dentro = False
    for base in permitidas:
        try:
            resuelta.relative_to(base)
            dentro = True
            break
        except ValueError:
            continue
    if not dentro:
        raise RespaldoError(
            f"La ruta {resuelta} queda fuera de los directorios permitidos. "
            f"Amplíelos con {VARIABLE_RUTAS_PERMITIDAS} si es intencional."
        )
    if debe_existir and not resuelta.is_file():
        raise RespaldoError(f"No existe el archivo {resuelta}.")
    if para_escritura and not resuelta.parent.is_dir():
        raise RespaldoError(f"El directorio destino {resuelta.parent} no existe.")
    return resuelta


def texto_para_log(valor, limite: int = LIMITE_TEXTO_LOG) -> str:
    """Devuelve el valor apto para una línea de registro.

    Sustituye saltos de línea, retornos de carro, tabuladores y cualquier
    carácter de control por espacio, y trunca. Así un dato de origen externo
    (por ejemplo un campo del manifiesto) no puede insertar líneas falsas en la
    bitácora ni secuencias de escape de terminal.
    """
    texto = "" if valor is None else str(valor)
    limpio = "".join(c if (c.isprintable() and c != "\x7f") else " " for c in texto)
    limpio = " ".join(limpio.split())
    if len(limpio) > limite:
        limpio = limpio[: limite - 3] + "..."
    return limpio


def _validar_argv(argv: list) -> None:
    """Confina la invocación de procesos hijo a los binarios esperados."""
    if not argv or not isinstance(argv, list):
        raise RespaldoError("Invocación de proceso sin argumentos.")
    if argv[0] not in EJECUTABLES_PERMITIDOS:
        raise RespaldoError(
            f"Ejecutable no permitido: {argv[0]!r}. Permitidos: {', '.join(EJECUTABLES_PERMITIDOS)}."
        )
    for elemento in argv:
        if not isinstance(elemento, str):
            raise RespaldoError("Todos los argumentos del proceso deben ser cadenas.")
        if "\x00" in elemento:
            raise RespaldoError("Un argumento del proceso contiene un carácter nulo.")


_manejador_propio: Optional[logging.Handler] = None


def configurar_logging(secretos: Iterable[str] = (), nivel: int = logging.INFO) -> logging.Logger:
    """Instala (o reemplaza) el manejador propio con el filtro de secretos. El filtro se
    aplica en el propio logger, de modo que cualquier otro manejador (por ejemplo, el de
    una prueba) también recibe el mensaje ya enmascarado."""
    global _manejador_propio
    if _manejador_propio is not None:
        logger.removeHandler(_manejador_propio)
    for filtro in list(logger.filters):
        logger.removeFilter(filtro)
    logger.addFilter(FiltroSinSecretos(secretos))
    manejador = logging.StreamHandler()
    manejador.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(manejador)
    _manejador_propio = manejador
    logger.setLevel(nivel)
    logger.propagate = False
    return logger


# ---------------------------------------------------------------------------
# Claves y cifrado por bloques
# ---------------------------------------------------------------------------
def clave_maestra_desde_texto(texto: Optional[str]) -> bytes:
    """Acepta una clave en formato Fernet (32 bytes en base64 url safe)."""
    if not texto or not texto.strip():
        raise ClaveInvalidaError(
            "BACKUP_ENCRYPTION_KEY no está definida. Genérela con "
            "python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        )
    try:
        crudo = base64.urlsafe_b64decode(texto.strip().encode("ascii"))
    except (ValueError, UnicodeEncodeError) as exc:
        raise ClaveInvalidaError("BACKUP_ENCRYPTION_KEY no es base64 url safe válido.") from exc
    if len(crudo) != 32:
        raise ClaveInvalidaError("BACKUP_ENCRYPTION_KEY debe decodificar a exactamente 32 bytes.")
    return crudo


def generar_clave_texto() -> str:
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("ascii")


def _derivar(clave_maestra: bytes, info: bytes) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=info).derive(clave_maestra)


def clave_cifrado(clave_maestra: bytes) -> bytes:
    return _derivar(clave_maestra, INFO_CIFRADO)


def clave_firma(clave_maestra: bytes) -> bytes:
    return _derivar(clave_maestra, INFO_FIRMA)


def _nonce(prefijo: bytes, contador: int) -> bytes:
    return prefijo + struct.pack(">I", contador)


def _aad(contador: int, ultimo: bool) -> bytes:
    return MAGIA + struct.pack(">IB", contador, 1 if ultimo else 0)


def cifrar_archivo(origen: Path, destino: Path, clave_maestra: bytes) -> tuple[str, int, str, int]:
    """Cifra `origen` en `destino`. Devuelve (sha256_plano, bytes_plano, sha256_cifrado, bytes_cifrado)."""
    aes = AESGCM(clave_cifrado(clave_maestra))
    prefijo = secrets.token_bytes(8)
    h_plano = hashlib.sha256()
    h_cifrado = hashlib.sha256()
    bytes_plano = 0
    bytes_cifrado = 0
    with open(origen, "rb") as fin, open(destino, "wb") as fout:
        cabecera = MAGIA + prefijo
        fout.write(cabecera)
        h_cifrado.update(cabecera)
        bytes_cifrado += len(cabecera)
        contador = 0
        bloque = fin.read(TAMANO_BLOQUE)
        while True:
            siguiente = fin.read(TAMANO_BLOQUE)
            ultimo = not siguiente
            h_plano.update(bloque)
            bytes_plano += len(bloque)
            cifrado = aes.encrypt(_nonce(prefijo, contador), bloque, _aad(contador, ultimo))
            trozo = struct.pack(">IB", len(cifrado), 1 if ultimo else 0) + cifrado
            fout.write(trozo)
            h_cifrado.update(trozo)
            bytes_cifrado += len(trozo)
            if ultimo:
                break
            contador += 1
            if contador >= 2**32 - 1:
                raise RespaldoError("El archivo excede el número máximo de bloques cifrables.")
            bloque = siguiente
    return h_plano.hexdigest(), bytes_plano, h_cifrado.hexdigest(), bytes_cifrado


def descifrar_archivo(origen: Path, destino: Path, clave_maestra: bytes) -> tuple[str, int]:
    """Descifra y autentica bloque a bloque. Devuelve (sha256_plano, bytes_plano)."""
    origen = ruta_segura(origen, debe_existir=True)
    destino = ruta_segura(destino, para_escritura=True)
    aes = AESGCM(clave_cifrado(clave_maestra))
    h_plano = hashlib.sha256()
    total = 0
    with open(origen, "rb") as fin, open(destino, "wb") as fout:
        cabecera = fin.read(len(MAGIA) + 8)
        if len(cabecera) != len(MAGIA) + 8 or cabecera[: len(MAGIA)] != MAGIA:
            raise IntegridadError("El archivo no es un respaldo cifrado de Sovereign AML (cabecera inválida).")
        prefijo = cabecera[len(MAGIA):]
        contador = 0
        while True:
            encabezado = fin.read(5)
            if len(encabezado) != 5:
                raise IntegridadError("Respaldo truncado: falta el encabezado de un bloque.")
            longitud, marca = struct.unpack(">IB", encabezado)
            if marca not in (0, 1) or longitud < 16:
                raise IntegridadError("Respaldo corrupto: encabezado de bloque inválido.")
            cifrado = fin.read(longitud)
            if len(cifrado) != longitud:
                raise IntegridadError("Respaldo truncado: bloque incompleto.")
            ultimo = marca == 1
            try:
                claro = aes.decrypt(_nonce(prefijo, contador), cifrado, _aad(contador, ultimo))
            except InvalidTag as exc:
                raise IntegridadError(
                    f"No se pudo autenticar el bloque {contador}: clave incorrecta o archivo alterado."
                ) from exc
            fout.write(claro)
            h_plano.update(claro)
            total += len(claro)
            if ultimo:
                if fin.read(1):
                    raise IntegridadError("Respaldo corrupto: datos adicionales tras el último bloque.")
                break
            contador += 1
    return h_plano.hexdigest(), total


def sha256_archivo(ruta: Path) -> str:
    ruta = ruta_segura(ruta, debe_existir=True)
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for trozo in iter(lambda: f.read(1024 * 1024), b""):
            h.update(trozo)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Manifiesto
# ---------------------------------------------------------------------------
def _canonico(manifiesto: dict) -> bytes:
    cuerpo = {k: v for k, v in manifiesto.items() if k != "firma_hmac"}
    return json.dumps(cuerpo, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def firmar_manifiesto(manifiesto: dict, clave_maestra: bytes) -> dict:
    firmado = dict(manifiesto)
    firmado["firma_hmac"] = hmac.new(clave_firma(clave_maestra), _canonico(manifiesto), hashlib.sha256).hexdigest()
    return firmado


def verificar_firma_manifiesto(manifiesto: dict, clave_maestra: bytes) -> None:
    firma = manifiesto.get("firma_hmac")
    if not isinstance(firma, str):
        raise IntegridadError("El manifiesto no tiene firma HMAC.")
    esperada = hmac.new(clave_firma(clave_maestra), _canonico(manifiesto), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(firma, esperada):
        raise IntegridadError("La firma del manifiesto no es válida (manifiesto alterado o clave distinta).")


CAMPOS_MANIFIESTO = (
    "version", "nombre", "fecha_utc", "archivo_cifrado", "bytes_cifrado", "sha256_cifrado",
    "bytes_plano", "sha256_plano", "cifrado", "base", "migraciones", "anclas_auditoria",
)


def construir_manifiesto(nombre: str, fecha: datetime, conexion: Conexion, sha_plano: str, bytes_plano: int,
                         sha_cifrado: str, bytes_cifrado: int, migraciones: list, anclas: list,
                         version_pg_dump: str, formato: str = "custom") -> dict:
    if fecha.tzinfo is None:
        fecha = fecha.replace(tzinfo=timezone.utc)
    return {
        "version": VERSION_MANIFIESTO,
        "nombre": nombre,
        "fecha_utc": fecha.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "archivo_cifrado": nombre + SUFIJO_CIFRADO,
        "bytes_cifrado": bytes_cifrado,
        "sha256_cifrado": sha_cifrado,
        "bytes_plano": bytes_plano,
        "sha256_plano": sha_plano,
        "cifrado": ALGORITMO_CIFRADO,
        "formato_pg_dump": formato,
        "version_pg_dump": version_pg_dump,
        "base": {"host": conexion.host, "puerto": conexion.puerto, "nombre": conexion.base},
        "migraciones": sorted(migraciones),
        "ultima_migracion": max(migraciones) if migraciones else None,
        "anclas_auditoria": anclas,
    }


def validar_estructura_manifiesto(manifiesto: dict) -> None:
    if not isinstance(manifiesto, dict):
        raise IntegridadError("El manifiesto no es un objeto JSON.")
    faltantes = [c for c in CAMPOS_MANIFIESTO if c not in manifiesto]
    if faltantes:
        raise IntegridadError(f"Manifiesto incompleto, faltan campos: {', '.join(faltantes)}.")
    if manifiesto["version"] != VERSION_MANIFIESTO:
        raise IntegridadError(f"Versión de manifiesto no soportada: {manifiesto['version']!r}.")
    for campo in ("sha256_cifrado", "sha256_plano"):
        if not re.fullmatch(r"[0-9a-f]{64}", str(manifiesto[campo])):
            raise IntegridadError(f"El campo {campo} del manifiesto no es un SHA-256 hexadecimal.")
    if not PATRON_NOMBRE.match(str(manifiesto["nombre"])):
        raise IntegridadError("El nombre del respaldo en el manifiesto no tiene el formato esperado.")


def cargar_manifiesto(texto: str) -> dict:
    try:
        manifiesto = json.loads(texto)
    except json.JSONDecodeError as exc:
        raise IntegridadError("El manifiesto no es JSON válido.") from exc
    validar_estructura_manifiesto(manifiesto)
    return manifiesto


# ---------------------------------------------------------------------------
# Consultas auxiliares con psql (sin driver Python)
# ---------------------------------------------------------------------------
def _ejecutar(argv: list, env_pg: dict, entrada: Optional[str] = None, timeout: int = 3600) -> subprocess.CompletedProcess:
    _validar_argv(argv)
    entorno = {k: v for k, v in os.environ.items() if not k.startswith("PG")}
    entorno.update(env_pg)
    try:
        return subprocess.run(  # nosec B603: argv fijo, sin shell
            argv, input=entrada, env=entorno, capture_output=True, text=True, timeout=timeout, check=False,
        )
    except FileNotFoundError as exc:
        raise RespaldoError(f"No se encontró el ejecutable '{argv[0]}'. Instale el cliente de PostgreSQL.") from exc
    except subprocess.TimeoutExpired as exc:
        raise RespaldoError(f"'{argv[0]}' excedió el tiempo máximo ({timeout} s).") from exc


def _salida_segura(texto: str, secretos: Iterable[str]) -> str:
    limpio = url_sin_credenciales(texto or "")
    for s in secretos:
        if s and len(s) >= LONGITUD_MINIMA_SECRETO:
            limpio = limpio.replace(s, "***")
    return limpio.strip()[:2000]


def consultar(conexion: Conexion, sql: str, variables: Optional[dict] = None, timeout: int = 120) -> list[list[str]]:
    """Ejecuta una consulta con psql y devuelve filas separadas por tabulador.
    Los valores se pasan como variables de psql (:'nombre'), nunca interpolados en el SQL."""
    argv = ["psql", "--no-psqlrc", "--tuples-only", "--no-align", "--field-separator=\t",
            "--quiet", "-v", "ON_ERROR_STOP=1"]
    for clave, valor in (variables or {}).items():
        if not re.fullmatch(r"[a-z_][a-z0-9_]*", clave):
            raise RespaldoError(f"Nombre de variable psql inválido: {clave}")
        argv += ["-v", f"{clave}={valor}"]
    # El SQL entra por stdin (-f -): a diferencia de -c, así psql sí interpola las variables.
    argv += ["-f", "-"]
    resultado = _ejecutar(argv, conexion.entorno_pg(), entrada=sql + "\n", timeout=timeout)
    if resultado.returncode != 0:
        raise RespaldoError(f"psql falló: {_salida_segura(resultado.stderr, [conexion.password])}")
    return [linea.split("\t") for linea in resultado.stdout.splitlines() if linea.strip()]


def _tabla_existe(conexion: Conexion, tabla: str) -> bool:
    filas = consultar(conexion, "SELECT to_regclass(:'tabla') IS NOT NULL", {"tabla": f'public."{tabla}"'})
    return bool(filas) and filas[0][0] == "t"


def leer_migraciones(conexion: Conexion) -> list[str]:
    if not _tabla_existe(conexion, "schema_migrations"):
        return []
    return [f[0] for f in consultar(conexion, "SELECT filename FROM public.schema_migrations ORDER BY filename")]


def leer_anclas_auditoria(conexion: Conexion) -> list[dict]:
    """Último eslabón (seq, hash) de la cadena de auditoría de cada licencia (T4)."""
    if not _tabla_existe(conexion, "BitacoraAuditoria"):
        return []
    filas = consultar(conexion, (
        'SELECT DISTINCT ON (licenciaid) licenciaid::text, seq::text, hash, hash_alg '
        'FROM public."BitacoraAuditoria" WHERE seq IS NOT NULL '
        'ORDER BY licenciaid, seq DESC'
    ))
    anclas = []
    for fila in filas:
        if len(fila) < 4:
            continue
        anclas.append({"licenciaid": fila[0], "ultimo_seq": int(fila[1]), "ultimo_hash": fila[2], "hash_alg": fila[3]})
    return anclas


def version_herramienta(nombre: str) -> str:
    resultado = _ejecutar([nombre, "--version"], {}, timeout=30)
    return (resultado.stdout or resultado.stderr).strip()


def ejecutar_pg_dump(conexion: Conexion, destino: Path, timeout: int = 3600) -> None:
    resultado = _ejecutar(
        ["pg_dump", "--format=custom", "--no-owner", "--no-privileges", "--compress=6", "--file", str(destino)],
        conexion.entorno_pg(), timeout=timeout,
    )
    if resultado.returncode != 0:
        raise RespaldoError(f"pg_dump falló: {_salida_segura(resultado.stderr, [conexion.password])}")
    if not destino.exists() or destino.stat().st_size == 0:
        raise RespaldoError("pg_dump terminó sin producir un archivo de volcado.")


def ejecutar_pg_restore(conexion: Conexion, volcado: Path, limpiar: bool, timeout: int = 7200) -> str:
    argv = ["pg_restore", "--no-owner", "--no-privileges", "--exit-on-error", "--dbname", conexion.base]
    if limpiar:
        argv += ["--clean", "--if-exists"]
    # "--" cierra la lista de opciones: una ruta que comenzara por "-" no puede
    # interpretarse como bandera de pg_restore (Command Argument Injection).
    argv += ["--", str(ruta_segura(volcado, debe_existir=True))]
    resultado = _ejecutar(argv, conexion.entorno_pg(), timeout=timeout)
    if resultado.returncode != 0:
        raise RespaldoError(f"pg_restore falló: {_salida_segura(resultado.stderr, [conexion.password])}")
    return _salida_segura(resultado.stderr, [conexion.password])


def crear_base_si_no_existe(conexion: Conexion) -> bool:
    """Crea la base destino conectándose a 'postgres'. Devuelve True si la creó."""
    _validar_identificador_base(conexion.base)
    admin = conexion.con_base("postgres")
    existe = consultar(admin, "SELECT 1 FROM pg_database WHERE datname = :'base'", {"base": conexion.base})
    if existe:
        return False
    resultado = _ejecutar(
        ["psql", "--no-psqlrc", "--quiet", "-v", "ON_ERROR_STOP=1", "-c", f'CREATE DATABASE "{conexion.base}"'],
        admin.entorno_pg(), timeout=120,
    )
    if resultado.returncode != 0:
        raise RespaldoError(f"No se pudo crear la base destino: {_salida_segura(resultado.stderr, [conexion.password])}")
    return True


# ---------------------------------------------------------------------------
# Protección de producción
# ---------------------------------------------------------------------------
def es_produccion(destino: Conexion, produccion: Optional[Conexion], hosts_extra: Iterable[str] = ()) -> bool:
    """Un destino se considera producción si coincide con DATABASE_URL (host, puerto y base)
    o si su host pertenece a los dominios de Railway o a BACKUP_HOSTS_PRODUCCION."""
    host = (destino.host or "").lower()
    if produccion is not None and (
        host == produccion.host.lower() and destino.puerto == produccion.puerto and destino.base == produccion.base
    ):
        return True
    patrones = list(HOSTS_PRODUCCION_DEFECTO) + [h.strip().lower() for h in hosts_extra if h.strip()]
    return any(host == p.lstrip(".") or host.endswith(p) for p in patrones)


def autorizar_destino(destino: Conexion, produccion: Optional[Conexion], bandera_cli: bool, variable_env: str,
                      hosts_extra: Iterable[str] = ()) -> bool:
    """Devuelve True si el destino es producción y quedó autorizado por la doble confirmación.
    Lanza ProduccionProtegidaError si es producción sin ambas confirmaciones."""
    if not es_produccion(destino, produccion, hosts_extra):
        return False
    if bandera_cli and variable_env.strip().lower() in ("si", "sí", "yes", "true", "1"):
        return True
    raise ProduccionProtegidaError(
        f"El destino {destino.descripcion()} corresponde a la base de PRODUCCION. "
        "Para restaurar sobre ella se exige la bandera --confirmar-produccion y la variable "
        "BACKUP_PERMITIR_RESTAURAR_PRODUCCION=si. Operación cancelada."
    )


# ---------------------------------------------------------------------------
# Almacenamiento (local o S3 compatible)
# ---------------------------------------------------------------------------
class AlmacenLocal:
    """Directorio local: cada respaldo son dos archivos, <nombre>.dump.enc y <nombre>.manifest.json."""

    def __init__(self, directorio: Path):
        self.directorio = Path(directorio)
        self.directorio.mkdir(parents=True, exist_ok=True)

    def descripcion(self) -> str:
        return f"directorio {self.directorio}"

    def listar(self) -> list[str]:
        return sorted(p.name for p in self.directorio.iterdir() if p.is_file())

    def subir(self, origen: Path, nombre: str) -> None:
        destino = self.directorio / nombre
        temporal = destino.with_name(destino.name + ".parcial")
        shutil.copyfile(origen, temporal)
        os.chmod(temporal, 0o600)
        os.replace(temporal, destino)

    def descargar(self, nombre: str, destino: Path) -> None:
        shutil.copyfile(self.directorio / nombre, destino)

    def leer_texto(self, nombre: str) -> str:
        return (self.directorio / nombre).read_text(encoding="utf-8")

    def tamano(self, nombre: str) -> int:
        return (self.directorio / nombre).stat().st_size

    def borrar(self, nombre: str) -> None:
        (self.directorio / nombre).unlink()


class AlmacenS3:
    """Bucket S3 compatible (Railway Buckets, AWS, MinIO). Requiere boto3, que es opcional."""

    def __init__(self, bucket: str, prefijo: str = "", endpoint: Optional[str] = None, region: Optional[str] = None):
        try:
            import boto3  # type: ignore
        except ImportError as exc:
            raise RespaldoError(
                "BACKUP_S3_BUCKET está definido pero boto3 no está instalado. "
                "Añada boto3 a requirements.txt o use BACKUP_DIR."
            ) from exc
        self.bucket = bucket
        self.prefijo = prefijo.strip("/")
        self._cliente = boto3.client("s3", endpoint_url=endpoint or None, region_name=region or None)

    def descripcion(self) -> str:
        return f"bucket s3://{self.bucket}/{self.prefijo}".rstrip("/")

    def _clave(self, nombre: str) -> str:
        return f"{self.prefijo}/{nombre}" if self.prefijo else nombre

    def listar(self) -> list[str]:
        nombres = []
        paginador = self._cliente.get_paginator("list_objects_v2")
        prefijo = self.prefijo + "/" if self.prefijo else ""
        for pagina in paginador.paginate(Bucket=self.bucket, Prefix=prefijo):
            for objeto in pagina.get("Contents", []):
                nombres.append(objeto["Key"][len(prefijo):])
        return sorted(n for n in nombres if n and "/" not in n)

    def subir(self, origen: Path, nombre: str) -> None:
        self._cliente.upload_file(str(origen), self.bucket, self._clave(nombre))

    def descargar(self, nombre: str, destino: Path) -> None:
        self._cliente.download_file(self.bucket, self._clave(nombre), str(destino))

    def leer_texto(self, nombre: str) -> str:
        objeto = self._cliente.get_object(Bucket=self.bucket, Key=self._clave(nombre))
        return objeto["Body"].read().decode("utf-8")

    def tamano(self, nombre: str) -> int:
        return int(self._cliente.head_object(Bucket=self.bucket, Key=self._clave(nombre))["ContentLength"])

    def borrar(self, nombre: str) -> None:
        self._cliente.delete_object(Bucket=self.bucket, Key=self._clave(nombre))


def almacen_desde_entorno(env: Optional[dict] = None, directorio_defecto: str = "backups"):
    env = os.environ if env is None else env
    bucket = env.get("BACKUP_S3_BUCKET", "").strip()
    if bucket:
        return AlmacenS3(
            bucket, env.get("BACKUP_S3_PREFIX", "sovereign-aml"),
            env.get("BACKUP_S3_ENDPOINT", "").strip() or None, env.get("BACKUP_S3_REGION", "").strip() or None,
        )
    return AlmacenLocal(Path(env.get("BACKUP_DIR", directorio_defecto)))


# ---------------------------------------------------------------------------
# Retención abuelo-padre-hijo
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class PoliticaRetencion:
    diarios: int = 7
    semanales: int = 4
    mensuales: int = 12

    @classmethod
    def desde_entorno(cls, env: Optional[dict] = None) -> "PoliticaRetencion":
        env = os.environ if env is None else env

        def _entero(clave: str, defecto: int) -> int:
            valor = env.get(clave, "").strip()
            if not valor:
                return defecto
            if not valor.isdigit() or int(valor) > 3650:
                raise RespaldoError(f"{clave} debe ser un entero entre 0 y 3650.")
            return int(valor)

        return cls(_entero("BACKUP_RETENCION_DIARIOS", 7), _entero("BACKUP_RETENCION_SEMANALES", 4),
                   _entero("BACKUP_RETENCION_MENSUALES", 12))


@dataclass(frozen=True)
class RespaldoListado:
    nombre: str
    fecha: datetime
    valido: bool
    motivo: str = ""


def fecha_desde_nombre(nombre: str) -> Optional[datetime]:
    coincidencia = PATRON_NOMBRE.match(nombre)
    if not coincidencia:
        return None
    return datetime.strptime(coincidencia.group(1), "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)


def nombre_respaldo(fecha: datetime) -> str:
    return PREFIJO_RESPALDO + fecha.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def seleccionar_conservados(respaldos: Iterable[RespaldoListado], politica: PoliticaRetencion) -> set[str]:
    """Nombres a conservar: N diarios más recientes, el más reciente de cada una de las N últimas
    semanas ISO y el más reciente de cada uno de los N últimos meses. El respaldo válido más
    reciente siempre se conserva, aunque la política sea cero en todos los niveles."""
    validos = sorted((r for r in respaldos if r.valido), key=lambda r: r.fecha, reverse=True)
    conservar: set[str] = set()
    if validos:
        conservar.add(validos[0].nombre)
    conservar.update(r.nombre for r in validos[: politica.diarios])
    conservar.update(_mas_reciente_por_grupo(validos, lambda f: f.isocalendar()[:2], politica.semanales))
    conservar.update(_mas_reciente_por_grupo(validos, lambda f: (f.year, f.month), politica.mensuales))
    return conservar


def _mas_reciente_por_grupo(validos_desc: list[RespaldoListado], clave, limite: int) -> set[str]:
    grupos: dict = {}
    for r in validos_desc:
        grupos.setdefault(clave(r.fecha), r.nombre)  # el primero visto es el más reciente
    return {nombre for _, nombre in list(grupos.items())[:limite]}


def inventariar(almacen) -> list[RespaldoListado]:
    """Empareja archivos cifrados con manifiestos y valida lo mínimo (existencia y tamaño)."""
    archivos = set(almacen.listar())
    respaldos = []
    for nombre_archivo in sorted(archivos):
        if not nombre_archivo.endswith(SUFIJO_CIFRADO):
            continue
        nombre = nombre_archivo[: -len(SUFIJO_CIFRADO)]
        fecha = fecha_desde_nombre(nombre)
        if fecha is None:
            continue
        manifiesto_nombre = nombre + SUFIJO_MANIFIESTO
        if manifiesto_nombre not in archivos:
            respaldos.append(RespaldoListado(nombre, fecha, False, "sin manifiesto"))
            continue
        try:
            manifiesto = cargar_manifiesto(almacen.leer_texto(manifiesto_nombre))
            if almacen.tamano(nombre_archivo) != int(manifiesto["bytes_cifrado"]):
                respaldos.append(RespaldoListado(nombre, fecha, False, "tamaño distinto al manifiesto"))
                continue
        except (IntegridadError, OSError, ValueError) as exc:
            respaldos.append(RespaldoListado(nombre, fecha, False, f"manifiesto inválido: {exc}"))
            continue
        respaldos.append(RespaldoListado(nombre, fecha, True))
    return respaldos


def aplicar_retencion(almacen, politica: PoliticaRetencion, simular: bool = False) -> dict:
    """Borra los respaldos fuera de política. Los inválidos se conservan y se reportan
    (nunca se borra algo que no se pudo evaluar, salvo huérfanos sin manifiesto de más de 30 días)."""
    respaldos = inventariar(almacen)
    conservar = seleccionar_conservados(respaldos, politica)
    borrados, mantenidos, invalidos = [], [], []
    ahora = datetime.now(timezone.utc)
    for r in respaldos:
        if not r.valido:
            invalidos.append(f"{r.nombre} ({r.motivo})")
            if r.motivo == "sin manifiesto" and (ahora - r.fecha).days > 30 and not simular:
                almacen.borrar(r.nombre + SUFIJO_CIFRADO)
                borrados.append(r.nombre)
            continue
        if r.nombre in conservar:
            mantenidos.append(r.nombre)
            continue
        borrados.append(r.nombre)
        if not simular:
            almacen.borrar(r.nombre + SUFIJO_CIFRADO)
            almacen.borrar(r.nombre + SUFIJO_MANIFIESTO)
    return {"conservados": sorted(mantenidos), "borrados": sorted(borrados), "invalidos": sorted(invalidos)}


# ---------------------------------------------------------------------------
# Flujos completos
# ---------------------------------------------------------------------------
def directorio_temporal() -> tempfile.TemporaryDirectory:
    base = os.environ.get("BACKUP_TMPDIR") or None
    return tempfile.TemporaryDirectory(prefix="sovereign_aml_bk_", dir=base)


def respaldar(conexion: Conexion, clave_maestra: bytes, almacen, politica: Optional[PoliticaRetencion] = None,
              ahora: Optional[datetime] = None, aplicar_politica: bool = True) -> dict:
    """Ejecuta el respaldo completo y devuelve el manifiesto firmado más el resultado de retención."""
    ahora = ahora or datetime.now(timezone.utc)
    nombre = nombre_respaldo(ahora)
    logger.info("Iniciando respaldo %s de %s hacia %s", nombre, conexion.descripcion(), almacen.descripcion())
    if nombre + SUFIJO_CIFRADO in set(almacen.listar()):
        raise RespaldoError(f"Ya existe un respaldo llamado {nombre}; no se sobrescribe. Reintente en unos segundos.")
    migraciones = leer_migraciones(conexion)
    anclas = leer_anclas_auditoria(conexion)
    logger.info("Migraciones aplicadas: %d (última: %s); anclas de auditoría: %d licencias",
                len(migraciones), max(migraciones) if migraciones else "ninguna", len(anclas))
    with directorio_temporal() as tmp:
        tmp_dir = Path(tmp)
        os.chmod(tmp_dir, 0o700)
        volcado = tmp_dir / (nombre + ".dump")
        cifrado = tmp_dir / (nombre + SUFIJO_CIFRADO)
        ejecutar_pg_dump(conexion, volcado)
        logger.info("pg_dump completado: %d bytes", volcado.stat().st_size)
        sha_plano, bytes_plano, sha_cifrado, bytes_cifrado = cifrar_archivo(volcado, cifrado, clave_maestra)
        volcado.unlink()
        manifiesto = firmar_manifiesto(construir_manifiesto(
            nombre, ahora, conexion, sha_plano, bytes_plano, sha_cifrado, bytes_cifrado,
            migraciones, anclas, version_herramienta("pg_dump"),
        ), clave_maestra)
        manifiesto_ruta = tmp_dir / (nombre + SUFIJO_MANIFIESTO)
        manifiesto_ruta.write_text(json.dumps(manifiesto, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        almacen.subir(cifrado, cifrado.name)
        almacen.subir(manifiesto_ruta, manifiesto_ruta.name)
    logger.info("Respaldo %s almacenado: %d bytes cifrados, SHA-256 %s", nombre, bytes_cifrado, sha_cifrado)
    retencion = {}
    if aplicar_politica:
        retencion = aplicar_retencion(almacen, politica or PoliticaRetencion())
        logger.info("Retención: %d conservados, %d borrados, %d inválidos",
                    len(retencion["conservados"]), len(retencion["borrados"]), len(retencion["invalidos"]))
    return {"manifiesto": manifiesto, "retencion": retencion}


def verificar_respaldo(archivo_cifrado: Path, manifiesto: dict, clave_maestra: bytes, volcado_destino: Path) -> dict:
    """Comprueba firma, hash del cifrado, descifra y comprueba hash y tamaño del volcado."""
    validar_estructura_manifiesto(manifiesto)
    verificar_firma_manifiesto(manifiesto, clave_maestra)
    tamano = archivo_cifrado.stat().st_size
    if tamano != int(manifiesto["bytes_cifrado"]):
        raise IntegridadError(f"Tamaño del archivo cifrado ({tamano}) distinto al del manifiesto ({manifiesto['bytes_cifrado']}).")
    sha_cifrado = sha256_archivo(archivo_cifrado)
    if not hmac.compare_digest(sha_cifrado, manifiesto["sha256_cifrado"]):
        raise IntegridadError("El SHA-256 del archivo cifrado no coincide con el manifiesto (archivo alterado).")
    sha_plano, bytes_plano = descifrar_archivo(archivo_cifrado, volcado_destino, clave_maestra)
    if bytes_plano != int(manifiesto["bytes_plano"]) or not hmac.compare_digest(sha_plano, manifiesto["sha256_plano"]):
        raise IntegridadError("El volcado descifrado no coincide con el hash o tamaño registrado en el manifiesto.")
    return {"sha256_cifrado": sha_cifrado, "sha256_plano": sha_plano, "bytes_plano": bytes_plano}


def comparar_migraciones(conexion: Conexion, manifiesto: dict) -> tuple[bool, str]:
    actuales = set(leer_migraciones(conexion))
    esperadas = set(manifiesto.get("migraciones") or [])
    if actuales == esperadas:
        return True, f"{len(actuales)} migraciones coinciden con el manifiesto"
    return False, f"faltan {sorted(esperadas - actuales)}; sobran {sorted(actuales - esperadas)}"
