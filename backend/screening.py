"""
screening.py: motor puro de screening contra listas de sanciones.

Base normativa: Recomendaciones 6 y 7 del GAFI (sanciones financieras dirigidas
relacionadas con terrorismo, su financiamiento y la proliferación de armas de
destrucción masiva) y Art. 23 y 25 de la Ley 6593 (debida diligencia).

Este módulo no depende de Streamlit ni de la base de datos: recibe entradas de
lista y nombres a consultar, y devuelve resultados explicables. La persistencia
vive en backend/screening_repo.py.

Componentes
-----------
  * normalizar_nombre / tokenizar: minúsculas, sin acentos (NFKD), sin
    puntuación, tokens ordenados y sin formas jurídicas (S.A., LTD, ...).
  * jaro_winkler: implementación con biblioteca estándar (sin dependencias).
  * IndiceScreening: índice invertido por token y por prefijo de token para
    no comparar cada consulta contra todas las entradas (listas de ~15.000
    registros con decenas de miles de alias).
  * evaluar / IndiceScreening.buscar: puntaje = máximo entre Jaro-Winkler del
    nombre completo normalizado y una comparación por tokens; el resultado
    incluye lista, entrada, alias coincidente, puntaje y motivo.
  * Parsers OFAC SDN (sdn.csv + alt.csv, sin encabezado) y ONU consolidada
    (XML) endurecidos: tamaño máximo y rechazo de DOCTYPE/ENTITY (XXE y
    "billion laughs") antes de parsear.
  * Descarga opcional desde URLs fijas oficiales (constantes; nunca una URL
    aportada por el usuario) con timeout, tamaño máximo y sin redirecciones.
    Desactivada por defecto (SCREENING_AUTO_DOWNLOAD). El contenedor de
    pruebas no tiene red: la descarga solo se ejercita con dobles de prueba.
"""
from __future__ import annotations

import csv
import hashlib
import io
import os
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple
from urllib.parse import urlparse
from xml.etree import ElementTree as ET  # nosec B405: se rechaza DOCTYPE/ENTITY antes de parsear

# ── Parámetros ───────────────────────────────────────────────────────────
UMBRAL_POR_DEFECTO = 0.88
UMBRAL_MINIMO = 0.70
UMBRAL_MAXIMO = 1.00
MAX_BYTES_ARCHIVO = 50 * 1024 * 1024          # 50 MB por archivo de lista
MAX_LARGO_NOMBRE = 300
LARGO_PREFIJO = 3
MAX_CANDIDATOS = 5000

FUENTE_OFAC = "OFAC_SDN"
FUENTE_ONU = "ONU"
FUENTES = (FUENTE_OFAC, FUENTE_ONU)

# Formas jurídicas y partículas que no aportan identidad al comparar tokens.
_STOP_TOKENS = frozenset({
    "sa", "s", "a", "sociedad", "anonima", "ltda", "ltd", "limited", "llc", "inc",
    "incorporated", "corp", "corporation", "co", "cia", "company", "srl", "sas",
    "plc", "gmbh", "ag", "bv", "nv", "de", "del", "la", "el", "los", "las", "y",
    "and", "the", "of",
})

# ── Descarga oficial (constantes fijas: anti SSRF) ────────────────────────
URL_OFAC_SDN = "https://www.treasury.gov/ofac/downloads/sdn.csv"
URL_OFAC_ALT = "https://www.treasury.gov/ofac/downloads/alt.csv"
URL_ONU_CONSOLIDADA = "https://scsanctions.un.org/resources/xml/en/consolidated.xml"
HOSTS_PERMITIDOS = frozenset({"www.treasury.gov", "scsanctions.un.org"})
TIMEOUT_DESCARGA = 60
VARIABLE_AUTO_DESCARGA = "SCREENING_AUTO_DOWNLOAD"


class ErrorScreening(ValueError):
    """Entrada inválida (archivo, formato, umbral)."""


class ArchivoRechazado(ErrorScreening):
    """El archivo no cumple las validaciones de seguridad (tamaño, XXE, formato)."""


# ── Normalización ────────────────────────────────────────────────────────

def _sin_acentos(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c))


def tokenizar(nombre, quitar_formas_juridicas: bool = True) -> List[str]:
    """Tokens ordenados, en minúsculas, sin acentos ni puntuación.

    Las formas jurídicas y partículas (S.A., LTD, de, la...) se eliminan salvo
    que no quede ningún token, en cuyo caso se conservan todos.
    """
    if nombre is None:
        return []
    texto = _sin_acentos(str(nombre)).lower()
    texto = re.sub(r"[^a-z0-9]+", " ", texto)
    tokens = [t for t in texto.split() if t]
    if quitar_formas_juridicas:
        # Se descartan formas jurídicas, partículas y siglas de una letra (S.A. de C.V.)
        filtrados = [t for t in tokens if t not in _STOP_TOKENS and len(t) > 1]
        if filtrados:
            tokens = filtrados
    return sorted(tokens)


def normalizar_nombre(nombre) -> str:
    """Cadena canónica: tokens ordenados unidos por espacio."""
    return " ".join(tokenizar(nombre))


# ── Jaro-Winkler (biblioteca estándar) ───────────────────────────────────

def jaro(s1: str, s2: str) -> float:
    if s1 == s2:
        return 1.0
    len1, len2 = len(s1), len(s2)
    if len1 == 0 or len2 == 0:
        return 0.0
    ventana = max(len1, len2) // 2 - 1
    if ventana < 0:
        ventana = 0
    match1 = [False] * len1
    match2 = [False] * len2
    coincidencias = 0
    for i, c1 in enumerate(s1):
        inicio = max(0, i - ventana)
        fin = min(i + ventana + 1, len2)
        for j in range(inicio, fin):
            if not match2[j] and s2[j] == c1:
                match1[i] = match2[j] = True
                coincidencias += 1
                break
    if coincidencias == 0:
        return 0.0
    transposiciones = 0
    k = 0
    for i in range(len1):
        if match1[i]:
            while not match2[k]:
                k += 1
            if s1[i] != s2[k]:
                transposiciones += 1
            k += 1
    t = transposiciones / 2
    m = float(coincidencias)
    return (m / len1 + m / len2 + (m - t) / m) / 3.0


def jaro_winkler(s1: str, s2: str, p: float = 0.1, max_prefijo: int = 4) -> float:
    """Jaro-Winkler estándar (prefijo común hasta 4 caracteres, p = 0.1)."""
    base = jaro(s1, s2)
    prefijo = 0
    for c1, c2 in zip(s1, s2):
        if c1 != c2 or prefijo >= max_prefijo:
            break
        prefijo += 1
    return base + prefijo * p * (1.0 - base)


# ── Similitud de nombres ─────────────────────────────────────────────────

def similitud_tokens(tokens_a: Sequence[str], tokens_b: Sequence[str]) -> float:
    """Promedio del mejor Jaro-Winkler por token (lado más corto contra el más largo),
    atenuado por la diferencia de cantidad de tokens (0.8 + 0.2 * corto/largo)."""
    if not tokens_a or not tokens_b:
        return 0.0
    corto, largo = (tokens_a, tokens_b) if len(tokens_a) <= len(tokens_b) else (tokens_b, tokens_a)
    suma = 0.0
    for t in corto:
        suma += max(jaro_winkler(t, u) for u in largo)
    promedio = suma / len(corto)
    ratio = len(corto) / len(largo)
    return promedio * (0.8 + 0.2 * ratio)


def comparar_nombres(consulta, candidato) -> Tuple[float, str]:
    """Devuelve (puntaje 0..1, motivo legible)."""
    tq = tokenizar(consulta)
    tc = tokenizar(candidato)
    if not tq or not tc:
        return 0.0, "Nombre vacío tras normalizar"
    nq, nc = " ".join(tq), " ".join(tc)
    if nq == nc:
        return 1.0, "Coincidencia exacta del nombre normalizado"
    jw = jaro_winkler(nq, nc)
    st = similitud_tokens(tq, tc)
    if jw >= st:
        return jw, f"Jaro-Winkler {jw:.3f} sobre el nombre completo normalizado"
    comunes = sorted(set(tq) & set(tc))
    detalle = f" (tokens comunes: {', '.join(comunes)})" if comunes else ""
    return st, f"Similitud por tokens {st:.3f}{detalle}"


def validar_umbral(umbral) -> float:
    try:
        valor = float(umbral)
    except (TypeError, ValueError) as exc:
        raise ErrorScreening("El umbral debe ser numérico.") from exc
    if not (UMBRAL_MINIMO <= valor <= UMBRAL_MAXIMO):
        raise ErrorScreening(f"El umbral debe estar entre {UMBRAL_MINIMO:.2f} y {UMBRAL_MAXIMO:.2f}.")
    return valor


# ── Estructuras ──────────────────────────────────────────────────────────

@dataclass(frozen=True)
class EntradaLista:
    """Entrada de una lista de sanciones (sujeto listado con sus alias)."""
    fuente: str
    referencia: str
    nombre: str
    tipo: str = ""
    programa: str = ""
    nacionalidad: str = ""
    alias: Tuple[str, ...] = ()
    id_entrada: Optional[str] = None      # identificador de persistencia (si existe)

    def variantes(self) -> List[Tuple[str, bool]]:
        """[(nombre_o_alias, es_alias)]"""
        return [(self.nombre, False)] + [(a, True) for a in self.alias if a]


@dataclass
class Coincidencia:
    """Resultado explicable de screening."""
    consulta: str
    fuente: str
    referencia: str
    nombre_lista: str
    alias_coincidente: Optional[str]
    puntaje: float
    motivo: str
    tipo: str = ""
    programa: str = ""
    id_entrada: Optional[str] = None

    def como_dict(self) -> dict:
        return {
            "consulta": self.consulta, "fuente": self.fuente, "referencia": self.referencia,
            "nombre_lista": self.nombre_lista, "alias_coincidente": self.alias_coincidente,
            "puntaje": round(self.puntaje, 4), "motivo": self.motivo, "tipo": self.tipo,
            "programa": self.programa, "id_entrada": self.id_entrada,
        }


@dataclass
class ResultadoParseo:
    fuente: str
    entradas: List[EntradaLista]
    filas_leidas: int = 0
    filas_rechazadas: int = 0
    hash_sha256: str = ""
    advertencias: List[str] = field(default_factory=list)


# ── Índice invertido ─────────────────────────────────────────────────────

class IndiceScreening:
    """Índice por token y por prefijo de token sobre nombres y alias.

    Cada variante (nombre o alias) se registra una vez; la búsqueda reúne los
    candidatos que comparten algún token o algún prefijo de token con la
    consulta y solo compara contra ellos.
    """

    def __init__(self, entradas: Iterable[EntradaLista] = ()):
        self._variantes: List[Tuple[EntradaLista, str, bool, Tuple[str, ...]]] = []
        self._por_token: Dict[str, Set[int]] = defaultdict(set)
        self._por_prefijo: Dict[str, Set[int]] = defaultdict(set)
        for entrada in entradas:
            self.agregar(entrada)

    def agregar(self, entrada: EntradaLista) -> None:
        for texto, es_alias in entrada.variantes():
            tokens = tuple(tokenizar(texto))
            if not tokens:
                continue
            idx = len(self._variantes)
            self._variantes.append((entrada, texto, es_alias, tokens))
            for t in tokens:
                self._por_token[t].add(idx)
                if len(t) >= LARGO_PREFIJO:
                    self._por_prefijo[t[:LARGO_PREFIJO]].add(idx)

    def __len__(self) -> int:
        return len(self._variantes)

    def candidatos(self, tokens: Sequence[str]) -> Set[int]:
        encontrados: Set[int] = set()
        for t in tokens:
            encontrados |= self._por_token.get(t, set())
        if len(encontrados) < MAX_CANDIDATOS:
            for t in tokens:
                if len(t) >= LARGO_PREFIJO:
                    encontrados |= self._por_prefijo.get(t[:LARGO_PREFIJO], set())
        return encontrados

    def buscar(self, consulta, umbral: float = UMBRAL_POR_DEFECTO, maximo: int = 10) -> List[Coincidencia]:
        """Coincidencias con puntaje >= umbral, una por entrada (mejor variante), ordenadas."""
        umbral = validar_umbral(umbral)
        tokens = tokenizar(consulta)
        if not tokens:
            return []
        mejores: Dict[Tuple[str, str], Coincidencia] = {}
        for idx in self.candidatos(tokens):
            entrada, texto, es_alias, _tokens = self._variantes[idx]
            puntaje, motivo = comparar_nombres(consulta, texto)
            if puntaje < umbral:
                continue
            clave = (entrada.fuente, entrada.referencia)
            previa = mejores.get(clave)
            if previa is not None and previa.puntaje >= puntaje:
                continue
            mejores[clave] = Coincidencia(
                consulta=str(consulta), fuente=entrada.fuente, referencia=entrada.referencia,
                nombre_lista=entrada.nombre, alias_coincidente=(texto if es_alias else None),
                puntaje=puntaje, motivo=motivo, tipo=entrada.tipo, programa=entrada.programa,
                id_entrada=entrada.id_entrada,
            )
        resultado = sorted(mejores.values(), key=lambda c: (-c.puntaje, c.fuente, c.referencia))
        return resultado[:maximo]


def evaluar(consultas: Iterable[str], indice: IndiceScreening, umbral: float = UMBRAL_POR_DEFECTO) -> List[Coincidencia]:
    """Ejecuta el screening de varios nombres (sin repetidos) y concatena coincidencias."""
    vistos: Set[str] = set()
    salida: List[Coincidencia] = []
    for consulta in consultas:
        if consulta is None:
            continue
        texto = re.sub(r"\s+", " ", str(consulta)).strip()
        if not texto or texto.lower() in ("nan", "none"):
            continue
        clave = normalizar_nombre(texto)
        if not clave or clave in vistos:
            continue
        vistos.add(clave)
        salida.extend(indice.buscar(texto, umbral))
    return salida


# ── Validaciones de archivo ──────────────────────────────────────────────

def validar_tamano(contenido: bytes, maximo: int = MAX_BYTES_ARCHIVO) -> bytes:
    if not isinstance(contenido, (bytes, bytearray)):
        raise ArchivoRechazado("Se esperaba el contenido del archivo en bytes.")
    if len(contenido) == 0:
        raise ArchivoRechazado("El archivo está vacío.")
    if len(contenido) > maximo:
        raise ArchivoRechazado(f"El archivo supera el máximo permitido de {maximo // (1024 * 1024)} MB.")
    return bytes(contenido)


def hash_archivo(contenido: bytes) -> str:
    return hashlib.sha256(contenido).hexdigest()


_PATRON_XXE = re.compile(rb"<!\s*(DOCTYPE|ENTITY)", re.IGNORECASE)


def _texto_limpio(valor, maximo: int = MAX_LARGO_NOMBRE) -> str:
    texto = re.sub(r"\s+", " ", str(valor or "")).strip()
    if texto in ("-0-", "-0", "null", "None"):
        return ""
    return texto[:maximo]


def _decodificar(contenido: bytes) -> str:
    for codificacion in ("utf-8-sig", "latin-1"):
        try:
            return contenido.decode(codificacion)
        except UnicodeDecodeError:
            continue
    raise ArchivoRechazado("No fue posible decodificar el archivo de texto.")


# ── Parser OFAC SDN ──────────────────────────────────────────────────────
# sdn.csv (sin encabezado, 12 columnas): ent_num, SDN_Name, SDN_Type, Program,
#   Title, Call_Sign, Vess_type, Tonnage, GRT, Vess_flag, Vess_owner, Remarks
# alt.csv (sin encabezado, 5 columnas): ent_num, alt_num, alt_type, alt_name, alt_remarks
_COLUMNAS_SDN = 12
_COLUMNAS_ALT = 5
_TIPOS_ALIAS_OFAC = frozenset({"aka", "fka", "nka"})


def _leer_csv(contenido: bytes) -> Iterable[List[str]]:
    texto = _decodificar(validar_tamano(contenido))
    return csv.reader(io.StringIO(texto))


def parsear_ofac_sdn(sdn_csv: bytes, alt_csv: Optional[bytes] = None) -> ResultadoParseo:
    """Convierte sdn.csv (+ alt.csv opcional) en entradas con alias."""
    resultado = ResultadoParseo(fuente=FUENTE_OFAC, entradas=[], hash_sha256=hash_archivo(sdn_csv))
    alias_por_ent: Dict[str, List[str]] = defaultdict(list)
    if alt_csv:
        for fila in _leer_csv(alt_csv):
            if not fila or (len(fila) == 1 and not fila[0].strip()):
                continue
            resultado.filas_leidas += 1
            if len(fila) < 4 or not fila[0].strip().isdigit():
                resultado.filas_rechazadas += 1
                continue
            tipo = fila[2].strip().lower().replace(".", "")
            nombre_alias = _texto_limpio(fila[3])
            if tipo not in _TIPOS_ALIAS_OFAC or not nombre_alias:
                resultado.filas_rechazadas += 1
                continue
            alias_por_ent[fila[0].strip()].append(nombre_alias)
    vistos: Set[str] = set()
    for fila in _leer_csv(sdn_csv):
        if not fila or (len(fila) == 1 and not fila[0].strip()):
            continue
        resultado.filas_leidas += 1
        if len(fila) < 4 or not fila[0].strip().isdigit():
            resultado.filas_rechazadas += 1
            continue
        ent = fila[0].strip()
        nombre = _texto_limpio(fila[1])
        if not nombre or ent in vistos:
            resultado.filas_rechazadas += 1
            continue
        vistos.add(ent)
        if len(fila) < _COLUMNAS_SDN:
            resultado.advertencias.append(f"Fila {ent}: {len(fila)} columnas (se esperaban {_COLUMNAS_SDN}).")
        resultado.entradas.append(EntradaLista(
            fuente=FUENTE_OFAC, referencia=ent, nombre=nombre,
            tipo=_texto_limpio(fila[2], 40).lower() or "individual",
            programa=_texto_limpio(fila[3], 200),
            nacionalidad=_texto_limpio(fila[9], 100) if len(fila) > 9 else "",
            alias=tuple(dict.fromkeys(alias_por_ent.get(ent, []))),
        ))
    if not resultado.entradas:
        raise ArchivoRechazado("El archivo sdn.csv no contiene entradas válidas.")
    resultado.advertencias = resultado.advertencias[:20]
    return resultado


# ── Parser ONU consolidada (XML) ─────────────────────────────────────────

def parsear_xml_seguro(contenido: bytes) -> ET.Element:
    """Parsea XML con xml.etree tras rechazar DOCTYPE/ENTITY y verificar tamaño."""
    datos = validar_tamano(contenido)
    if _PATRON_XXE.search(datos):
        raise ArchivoRechazado("XML rechazado: contiene DOCTYPE o ENTITY (riesgo XXE / expansión de entidades).")
    try:
        raiz = ET.fromstring(datos)  # nosec B314: sin DOCTYPE ni ENTITY no hay expansión posible
    except ET.ParseError as exc:
        raise ArchivoRechazado(f"XML mal formado: {exc}") from exc
    return raiz


def _texto_hijo(nodo: ET.Element, etiqueta: str) -> str:
    hijo = nodo.find(etiqueta)
    return _texto_limpio(hijo.text if hijo is not None else "")


def _nombre_onu(nodo: ET.Element) -> str:
    partes = [_texto_hijo(nodo, e) for e in ("FIRST_NAME", "SECOND_NAME", "THIRD_NAME", "FOURTH_NAME")]
    return _texto_limpio(" ".join(p for p in partes if p))


def _alias_onu(nodo: ET.Element, etiqueta: str) -> Tuple[str, ...]:
    alias = []
    for a in nodo.findall(etiqueta):
        texto = _texto_hijo(a, "ALIAS_NAME")
        if texto:
            alias.extend(_texto_limpio(x) for x in texto.split(";") if _texto_limpio(x))
    return tuple(dict.fromkeys(alias))


def parsear_onu_consolidada(xml_bytes: bytes) -> ResultadoParseo:
    """Convierte la lista consolidada del Consejo de Seguridad de la ONU (XML) en entradas."""
    raiz = parsear_xml_seguro(xml_bytes)
    resultado = ResultadoParseo(fuente=FUENTE_ONU, entradas=[], hash_sha256=hash_archivo(xml_bytes))
    vistos: Set[str] = set()
    for etiqueta_nodo, tipo, etiqueta_alias in (
        ("INDIVIDUAL", "individual", "INDIVIDUAL_ALIAS"),
        ("ENTITY", "entity", "ENTITY_ALIAS"),
    ):
        for nodo in raiz.iter(etiqueta_nodo):
            resultado.filas_leidas += 1
            referencia = _texto_hijo(nodo, "DATAID") or _texto_hijo(nodo, "REFERENCE_NUMBER")
            nombre = _nombre_onu(nodo)
            if not referencia or not nombre or referencia in vistos:
                resultado.filas_rechazadas += 1
                continue
            vistos.add(referencia)
            nac = nodo.find("NATIONALITY")
            resultado.entradas.append(EntradaLista(
                fuente=FUENTE_ONU, referencia=referencia, nombre=nombre, tipo=tipo,
                programa=_texto_hijo(nodo, "UN_LIST_TYPE")[:200],
                nacionalidad=(_texto_hijo(nac, "VALUE")[:100] if nac is not None else ""),
                alias=_alias_onu(nodo, etiqueta_alias),
            ))
    if not resultado.entradas:
        raise ArchivoRechazado("El XML no contiene entradas INDIVIDUAL ni ENTITY válidas.")
    return resultado


def parsear_por_fuente(fuente: str, principal: bytes, secundario: Optional[bytes] = None) -> ResultadoParseo:
    if fuente == FUENTE_OFAC:
        return parsear_ofac_sdn(principal, secundario)
    if fuente == FUENTE_ONU:
        return parsear_onu_consolidada(principal)
    raise ErrorScreening(f"Fuente de lista desconocida: {fuente}")


def validar_extension(nombre_archivo: str, permitidas: Sequence[str]) -> str:
    nombre = os.path.basename(str(nombre_archivo or ""))
    ext = nombre.rsplit(".", 1)[-1].lower() if "." in nombre else ""
    if ext not in permitidas:
        raise ArchivoRechazado(f"Extensión no permitida: se aceptan {', '.join(permitidas)}.")
    return nombre[:255]


# ── Descarga oficial opcional ─────────────────────────────────────────────

def auto_descarga_habilitada() -> bool:
    return os.getenv(VARIABLE_AUTO_DESCARGA, "false").strip().lower() in ("1", "true", "si", "yes")


def _verificar_url_fija(url: str) -> None:
    partes = urlparse(url)
    if partes.scheme != "https" or partes.hostname not in HOSTS_PERMITIDOS:
        raise ErrorScreening("URL de descarga no autorizada (solo hosts oficiales fijos por HTTPS).")
    if url not in (URL_OFAC_SDN, URL_OFAC_ALT, URL_ONU_CONSOLIDADA):
        raise ErrorScreening("Solo se permiten las URLs oficiales definidas en el código.")


def descargar_oficial(url: str, timeout: int = TIMEOUT_DESCARGA, max_bytes: int = MAX_BYTES_ARCHIVO,
                      cliente_http=None) -> bytes:
    """Descarga una de las URLs oficiales (constantes) sin seguir redirecciones.

    `cliente_http` permite inyectar un doble de prueba con la firma de
    requests.get(url, timeout=..., stream=..., allow_redirects=...). En el
    contenedor de pruebas no hay red, por lo que la ruta real no se ejercita.
    """
    if not auto_descarga_habilitada():
        raise ErrorScreening(f"Descarga automática desactivada: defina {VARIABLE_AUTO_DESCARGA}=true.")
    _verificar_url_fija(url)
    if cliente_http is None:
        import requests  # importación diferida: dependencia ya presente en requirements
        cliente_http = requests.get
    respuesta = cliente_http(url, timeout=timeout, stream=True, allow_redirects=False)
    try:
        if getattr(respuesta, "status_code", 0) != 200:
            raise ErrorScreening(f"Descarga rechazada: estado HTTP {getattr(respuesta, 'status_code', '?')}.")
        buffer = bytearray()
        for trozo in respuesta.iter_content(chunk_size=65536):
            if not trozo:
                continue
            buffer.extend(trozo)
            if len(buffer) > max_bytes:
                raise ArchivoRechazado("Descarga interrumpida: supera el tamaño máximo permitido.")
    finally:
        cerrar = getattr(respuesta, "close", None)
        if callable(cerrar):
            cerrar()
    return validar_tamano(bytes(buffer), max_bytes)
