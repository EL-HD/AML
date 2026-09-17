"""
Pruebas estáticas del proxy inverso (T5 Fase 2): Caddyfile, supervisord.conf y
Dockerfile deben ser coherentes entre sí y con .streamlit/config.toml.

No requieren el binario de Caddy: se usa un parser mínimo del Caddyfile
(bloques por llaves, una directiva por línea, comentarios con #). Si el binario
está disponible en PATH, además se ejecuta `caddy validate`.
"""
import os
import re
import shutil
import subprocess
import unittest
from pathlib import Path

from tests.conftest import ROOT
from scripts.verificar_cabeceras import parsear_csp

CADDYFILE = ROOT / "Caddyfile"
SUPERVISORD = ROOT / "supervisord.conf"
DOCKERFILE = ROOT / "Dockerfile"
STREAMLIT_CONFIG = ROOT / ".streamlit" / "config.toml"

CABECERAS_REQUERIDAS = (
    "Content-Security-Policy",
    "Strict-Transport-Security",
    "X-Frame-Options",
    "X-Content-Type-Options",
    "Referrer-Policy",
    "Permissions-Policy",
)


def _lineas_utiles(texto: str):
    for cruda in texto.splitlines():
        linea = cruda.split("#", 1)[0].strip() if not cruda.strip().startswith("#") else ""
        if linea:
            yield linea


def parsear_caddyfile(texto: str) -> dict:
    """Devuelve un árbol {directiva: [tokens]} anidado por bloques {}."""
    raiz: dict = {"_directivas": []}
    pila = [raiz]
    for linea in _lineas_utiles(texto):
        if linea == "}":
            pila.pop()
            continue
        abre = linea.endswith("{")
        cuerpo = linea[:-1].strip() if abre else linea
        tokens = re.findall(r'"[^"]*"|\S+', cuerpo)
        tokens = [t.strip('"') for t in tokens]
        if abre:
            hijo = {"_directivas": []}
            pila[-1][cuerpo or "_global"] = hijo
            pila[-1]["_directivas"].append(tokens)
            pila.append(hijo)
        else:
            pila[-1]["_directivas"].append(tokens)
    if len(pila) != 1:
        raise ValueError("Llaves desbalanceadas en el Caddyfile")
    return raiz


def _bloque(arbol: dict, prefijo: str) -> dict:
    for clave, valor in arbol.items():
        if clave != "_directivas" and clave.startswith(prefijo):
            return valor
    raise KeyError(prefijo)


def _cabeceras(bloque_header: dict) -> dict:
    return {d[0]: " ".join(d[1:]) for d in bloque_header["_directivas"] if len(d) >= 2}


class TestCaddyfile(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.texto = CADDYFILE.read_text(encoding="utf-8")
        cls.arbol = parsear_caddyfile(cls.texto)
        cls.sitio = _bloque(cls.arbol, ":{$PORT")
        cls.header = _bloque(cls.sitio, "header")
        cls.cabeceras = _cabeceras(cls.header)
        cls.csp = parsear_csp(cls.cabeceras["Content-Security-Policy"])

    def test_sin_tls_automatico_ni_admin(self):
        globales = _bloque(self.arbol, "_global")["_directivas"]
        self.assertIn(["auto_https", "off"], globales)
        self.assertIn(["admin", "off"], globales)

    def test_escucha_en_puerto_de_railway(self):
        self.assertIn(":{$PORT:8080}", self.arbol)

    def test_proxy_hacia_streamlit_local(self):
        proxy = _bloque(self.sitio, "reverse_proxy 127.0.0.1:8501")
        header_up = {d[1]: d[2] for d in proxy["_directivas"] if d[0] == "header_up"}
        self.assertEqual(header_up.get("X-Forwarded-For"), "{client_ip}")
        self.assertEqual(header_up.get("X-Real-IP"), "{client_ip}")

    def test_ip_real_solo_desde_proxies_de_confianza(self):
        servidores = _bloque(_bloque(self.arbol, "_global"), "servers")["_directivas"]
        self.assertIn(["trusted_proxies", "static", "private_ranges"], servidores)
        self.assertIn(["client_ip_headers", "X-Real-IP"], servidores)

    def test_todas_las_cabeceras_requeridas(self):
        for nombre in CABECERAS_REQUERIDAS:
            self.assertIn(nombre, self.cabeceras, nombre)
        self.assertIn(["-Server"], self.header["_directivas"])
        self.assertIn(["-Via"], self.header["_directivas"])
        self.assertIn(["defer"], self.header["_directivas"])

    def test_valores_de_cabeceras(self):
        self.assertEqual(self.cabeceras["Strict-Transport-Security"], "max-age=31536000")
        self.assertEqual(self.cabeceras["X-Frame-Options"], "DENY")
        self.assertEqual(self.cabeceras["X-Content-Type-Options"], "nosniff")
        self.assertEqual(self.cabeceras["Referrer-Policy"], "strict-origin-when-cross-origin")
        for permiso in ("camera=()", "microphone=()", "geolocation=()", "payment=()"):
            self.assertIn(permiso, self.cabeceras["Permissions-Policy"])

    def test_csp_directivas_criticas(self):
        self.assertEqual(self.csp["default-src"], ["'self'"])
        self.assertEqual(self.csp["frame-ancestors"], ["'none'"])
        self.assertEqual(self.csp["object-src"], ["'none'"])
        self.assertEqual(self.csp["base-uri"], ["'self'"])
        self.assertEqual(self.csp["form-action"], ["'self'"])
        self.assertNotIn("'unsafe-eval'", self.csp["script-src"])
        self.assertNotIn("*", self.csp["script-src"])

    def test_csp_compatible_con_streamlit(self):
        self.assertIn("'unsafe-inline'", self.csp["script-src"])
        self.assertIn("'unsafe-inline'", self.csp["style-src"])
        self.assertIn("https://fonts.googleapis.com", self.csp["style-src"])
        self.assertIn("https://fonts.gstatic.com", self.csp["font-src"])
        self.assertIn("data:", self.csp["img-src"])
        self.assertIn("blob:", self.csp["worker-src"])
        self.assertIn("'self'", self.csp["connect-src"])
        self.assertIn("wss://{http.request.hostport}", self.csp["connect-src"])
        self.assertNotIn("wss:", self.csp["connect-src"])

    def test_fuentes_externas_de_la_app_estan_en_csp(self):
        css = (ROOT / "frontend" / "theme" / "styles.css").read_text(encoding="utf-8")
        for host in re.findall(r"https://([a-z0-9.-]+)", css):
            permitido = any(f"https://{host}" in v for v in self.csp.values())
            self.assertTrue(permitido, f"{host} no está permitido en la CSP")

    def test_limite_de_cuerpo_coherente_con_streamlit(self):
        cuerpo = _bloque(self.sitio, "request_body")["_directivas"]
        tamano = next(d[1] for d in cuerpo if d[0] == "max_size")
        mb_caddy = int(re.fullmatch(r"(\d+)MiB", tamano).group(1))  # MiB: misma unidad que Streamlit
        cfg = STREAMLIT_CONFIG.read_text(encoding="utf-8")
        mb_streamlit = int(re.search(r"maxUploadSize\s*=\s*(\d+)", cfg).group(1))
        self.assertGreaterEqual(mb_caddy, mb_streamlit)
        self.assertLessEqual(mb_caddy - mb_streamlit, 2)

    def test_compresion_activa(self):
        self.assertIn(["encode", "zstd", "gzip"], self.sitio["_directivas"])

    def test_sin_guiones_largos_ni_emojis(self):
        self.assertNotIn("—", self.texto)
        self.assertFalse(re.search(r"[\U0001F300-\U0001FAFF]", self.texto))

    @unittest.skipUnless(shutil.which("caddy"), "binario caddy no disponible")
    def test_caddy_validate(self):
        resultado = subprocess.run(  # nosec B603: binario fijo, sin shell
            [shutil.which("caddy"), "validate", "--config", str(CADDYFILE), "--adapter", "caddyfile"],
            capture_output=True, text=True, env={**os.environ, "PORT": "8080"}, timeout=60,
        )
        self.assertEqual(resultado.returncode, 0, resultado.stderr)


class TestSupervisordYDockerfile(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sup = SUPERVISORD.read_text(encoding="utf-8")
        cls.docker = DOCKERFILE.read_text(encoding="utf-8")

    def _programa(self, nombre: str) -> str:
        m = re.search(rf"\[program:{nombre}\](.*?)(?=\n\[|\Z)", self.sup, re.S)
        self.assertIsNotNone(m, f"falta [program:{nombre}]")
        return m.group(1)

    def test_streamlit_solo_loopback(self):
        st = self._programa("streamlit")
        self.assertIn("--server.address 127.0.0.1", st)
        self.assertIn("--server.port 8501", st)
        self.assertNotIn("0.0.0.0", st)

    def test_caddy_arranca_despues_de_streamlit(self):
        caddy = self._programa("caddy")
        self.assertIn("caddy run --config /app/Caddyfile --adapter caddyfile", caddy)
        prioridad = {n: int(re.search(r"priority=(\d+)", self._programa(n)).group(1))
                     for n in ("fastapi", "streamlit", "caddy")}
        self.assertLess(prioridad["fastapi"], prioridad["streamlit"])
        self.assertLess(prioridad["streamlit"], prioridad["caddy"])
        self.assertIn("autorestart=true", caddy)

    def test_dockerfile_instala_caddy_verificado(self):
        self.assertRegex(self.docker, r"ARG CADDY_VERSION=\d+\.\d+\.\d+")
        self.assertRegex(self.docker, r"ARG CADDY_SHA512_AMD64=[0-9a-f]{128}")
        self.assertRegex(self.docker, r"ARG CADDY_SHA512_ARM64=[0-9a-f]{128}")
        self.assertIn("sha512sum -c", self.docker)
        self.assertIn("github.com/caddyserver/caddy/releases/download", self.docker)
        self.assertIn("COPY --from=builder /usr/local/bin/caddy /usr/local/bin/caddy", self.docker)

    def test_dockerfile_healthcheck_por_el_proxy(self):
        self.assertIn("os.environ.get('PORT'", self.docker)
        self.assertNotIn("localhost:8501/_stcore/health", self.docker)
        self.assertIn("EXPOSE 8080", self.docker)
        self.assertRegex(self.docker, r"\n\s+PORT=8080")


if __name__ == "__main__":
    unittest.main()
