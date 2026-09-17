"""
Verificación de cabeceras de seguridad y del proxy inverso (T5 Fase 2).

Uso:
    python scripts/verificar_cabeceras.py http://127.0.0.1:8080 [--websocket]

Comprueba, contra un servidor en vivo (Caddy delante de Streamlit):
- que la página raíz responde 200 con las cabeceras de seguridad requeridas;
- que la CSP contiene las directivas críticas (frame-ancestors, object-src, etc.);
- que no se expone la cabecera Server;
- que /_stcore/health responde "ok" a través del proxy;
- opcionalmente, que /_stcore/stream acepta el upgrade a WebSocket (101).

Sale con código 0 si todo se cumple y 1 en caso contrario. Solo biblioteca estándar.
"""
from __future__ import annotations

import argparse
import base64
import http.client
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

CABECERAS_REQUERIDAS = (
    "content-security-policy",
    "strict-transport-security",
    "x-frame-options",
    "x-content-type-options",
    "referrer-policy",
    "permissions-policy",
)

DIRECTIVAS_CSP_REQUERIDAS = {
    "default-src": ("'self'",),
    "frame-ancestors": ("'none'",),
    "object-src": ("'none'",),
    "base-uri": ("'self'",),
    "form-action": ("'self'",),
    "connect-src": ("'self'",),
}

TIMEOUT = 15


def parsear_csp(valor: str) -> dict[str, list[str]]:
    """Convierte 'a b c; d e' en {'a': ['b', 'c'], 'd': ['e']}."""
    directivas: dict[str, list[str]] = {}
    for trozo in valor.split(";"):
        partes = trozo.strip().split()
        if partes:
            directivas[partes[0].lower()] = partes[1:]
    return directivas


def _obtener(url: str) -> tuple[int, dict[str, str], bytes]:
    peticion = urllib.request.Request(url, headers={"User-Agent": "verificar-cabeceras/1.0"})
    try:
        with urllib.request.urlopen(peticion, timeout=TIMEOUT) as resp:  # nosec B310: esquema http(s) fijado por el operador
            cabeceras = {k.lower(): v for k, v in resp.headers.items()}
            return resp.status, cabeceras, resp.read()
    except urllib.error.HTTPError as exc:
        cabeceras = {k.lower(): v for k, v in exc.headers.items()}
        return exc.code, cabeceras, exc.read()


def verificar_pagina(base: str, hallazgos: list[str]) -> dict[str, str]:
    estado, cabeceras, cuerpo = _obtener(base + "/")
    if estado != 200:
        hallazgos.append(f"GET / devolvió {estado} (se esperaba 200)")
    if b"<div id=\"root\">" not in cuerpo:
        hallazgos.append("GET / no devolvió el index.html de Streamlit")
    for nombre in CABECERAS_REQUERIDAS:
        if nombre not in cabeceras:
            hallazgos.append(f"Falta la cabecera {nombre}")
    if "server" in cabeceras:
        hallazgos.append(f"Se expone la cabecera Server: {cabeceras['server']}")
    hsts = cabeceras.get("strict-transport-security", "")
    if "max-age=31536000" not in hsts:
        hallazgos.append(f"HSTS sin max-age de un año: {hsts!r}")
    if "preload" in hsts:
        hallazgos.append("HSTS no debe incluir preload")
    if cabeceras.get("x-frame-options", "").upper() != "DENY":
        hallazgos.append("X-Frame-Options debe ser DENY")
    if cabeceras.get("x-content-type-options", "").lower() != "nosniff":
        hallazgos.append("X-Content-Type-Options debe ser nosniff")
    csp = parsear_csp(cabeceras.get("content-security-policy", ""))
    for directiva, valores in DIRECTIVAS_CSP_REQUERIDAS.items():
        presentes = csp.get(directiva, [])
        for valor in valores:
            if valor not in presentes:
                hallazgos.append(f"CSP: {directiva} debe incluir {valor} (actual: {presentes})")
    if "'unsafe-eval'" in csp.get("script-src", []):
        hallazgos.append("CSP: script-src no debe incluir 'unsafe-eval'")
    return cabeceras


def verificar_salud(base: str, hallazgos: list[str]) -> None:
    estado, _cabeceras, cuerpo = _obtener(base + "/_stcore/health")
    if estado != 200 or cuerpo.strip() != b"ok":
        hallazgos.append(f"/_stcore/health devolvió {estado} {cuerpo[:40]!r}")


def verificar_websocket(base: str, hallazgos: list[str]) -> None:
    """Envía el handshake de upgrade a /_stcore/stream y espera 101."""
    partes = urllib.parse.urlsplit(base)
    puerto = partes.port or (443 if partes.scheme == "https" else 80)
    clase = http.client.HTTPSConnection if partes.scheme == "https" else http.client.HTTPConnection
    conexion = clase(partes.hostname, puerto, timeout=TIMEOUT)
    clave = base64.b64encode(os.urandom(16)).decode("ascii")
    try:
        conexion.putrequest("GET", "/_stcore/stream", skip_host=True, skip_accept_encoding=True)
        conexion.putheader("Host", partes.netloc)
        conexion.putheader("Origin", base)
        conexion.putheader("Upgrade", "websocket")
        conexion.putheader("Connection", "Upgrade")
        conexion.putheader("Sec-WebSocket-Key", clave)
        conexion.putheader("Sec-WebSocket-Version", "13")
        conexion.endheaders()
        respuesta = conexion.getresponse()
        if respuesta.status != 101:
            hallazgos.append(f"/_stcore/stream devolvió {respuesta.status} en lugar de 101")
        elif respuesta.getheader("Upgrade", "").lower() != "websocket":
            hallazgos.append("La respuesta 101 no confirma Upgrade: websocket")
    except (OSError, http.client.HTTPException) as exc:
        hallazgos.append(f"WebSocket: {exc}")
    finally:
        conexion.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verifica cabeceras de seguridad de Sovereign AML.")
    parser.add_argument("url", help="URL base, p. ej. http://127.0.0.1:8080")
    parser.add_argument("--websocket", action="store_true", help="Probar también el upgrade a WebSocket")
    args = parser.parse_args(argv)
    base = args.url.rstrip("/")
    hallazgos: list[str] = []
    try:
        cabeceras = verificar_pagina(base, hallazgos)
        verificar_salud(base, hallazgos)
        if args.websocket:
            verificar_websocket(base, hallazgos)
    except (OSError, urllib.error.URLError) as exc:
        print(f"No se pudo conectar con {base}: {exc}")
        return 1
    for nombre in CABECERAS_REQUERIDAS:
        print(f"{nombre}: {cabeceras.get(nombre, '(ausente)')}")
    if hallazgos:
        print("\nHALLAZGOS:")
        for h in hallazgos:
            print(f" - {h}")
        return 1
    print("\nTodas las comprobaciones se cumplen.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
