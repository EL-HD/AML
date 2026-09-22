"""Pruebas de las validaciones de entrada externa añadidas tras el análisis de SonarCloud.

Cubren las tres funciones de saneamiento de backend/respaldos.py y la
validación de URL de scripts/verificar_cabeceras.py:

    ruta_segura      Path Traversal        (pythonsecurity:S2083, S8707)
    texto_para_log   Log Injection         (pythonsecurity:S5145)
    _validar_argv    Command Arg Injection (pythonsecurity:S6350, S8705)
    url_validada     SSRF                  (pythonsecurity:S8703)

El caso de Log Injection no es teórico: el manifiesto de un respaldo es un JSON
de origen externo y sus campos se escriben en la bitácora de la restauración.
Un manifiesto manipulado no debe poder insertar líneas falsas en un registro
que forma parte del expediente de cumplimiento.
"""
import tempfile
import unittest
from pathlib import Path

import tests.conftest  # noqa: F401

from backend import respaldos
from scripts.verificar_cabeceras import url_validada


class TestRutaSegura(unittest.TestCase):
    def test_acepta_ruta_dentro_de_base_permitida(self):
        with tempfile.TemporaryDirectory() as tmp:
            objetivo = Path(tmp) / "respaldo.dump.enc"
            objetivo.write_bytes(b"contenido")
            resuelta = respaldos.ruta_segura(objetivo, debe_existir=True)
            self.assertEqual(resuelta, objetivo.resolve())

    def test_devuelve_ruta_resuelta_sin_componentes_relativos(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "sub").mkdir()
            objetivo = base / "sub" / ".." / "archivo.txt"
            (base / "archivo.txt").write_text("x", encoding="utf-8")
            resuelta = respaldos.ruta_segura(objetivo, debe_existir=True)
            self.assertNotIn("..", resuelta.parts)
            self.assertEqual(resuelta, (base / "archivo.txt").resolve())

    def test_rechaza_ruta_fuera_de_las_bases_permitidas(self):
        with self.assertRaises(respaldos.RespaldoError):
            respaldos.ruta_segura("/etc/passwd")

    def test_rechaza_escape_por_componentes_relativos(self):
        with tempfile.TemporaryDirectory() as tmp:
            fuga = Path(tmp) / ".." / ".." / ".." / "etc" / "shadow"
            with self.assertRaises(respaldos.RespaldoError):
                respaldos.ruta_segura(fuga)

    def test_rechaza_vacio_nulo_y_control(self):
        for entrada in ("", "   ", "archivo\x00.dump", "archivo\n.dump", None):
            with self.subTest(entrada=entrada):
                with self.assertRaises(respaldos.RespaldoError):
                    respaldos.ruta_segura(entrada)

    def test_debe_existir_y_para_escritura_son_explicitos(self):
        with tempfile.TemporaryDirectory() as tmp:
            inexistente = Path(tmp) / "no_esta.dump"
            with self.assertRaises(respaldos.RespaldoError):
                respaldos.ruta_segura(inexistente, debe_existir=True)
            # Como destino de escritura sí es válida: su directorio existe.
            self.assertEqual(
                respaldos.ruta_segura(inexistente, para_escritura=True), inexistente.resolve()
            )
            with self.assertRaises(respaldos.RespaldoError):
                respaldos.ruta_segura(Path(tmp) / "falta" / "x.dump", para_escritura=True)

    def test_variable_de_entorno_amplia_las_bases(self):
        import os
        with tempfile.TemporaryDirectory() as tmp:
            externo = Path(tmp).resolve()
            previo = os.environ.get(respaldos.VARIABLE_RUTAS_PERMITIDAS)
            os.environ[respaldos.VARIABLE_RUTAS_PERMITIDAS] = str(externo)
            try:
                self.assertIn(externo, respaldos.bases_permitidas())
            finally:
                if previo is None:
                    os.environ.pop(respaldos.VARIABLE_RUTAS_PERMITIDAS, None)
                else:
                    os.environ[respaldos.VARIABLE_RUTAS_PERMITIDAS] = previo


class TestTextoParaLog(unittest.TestCase):
    def test_neutraliza_salto_de_linea_inyectado(self):
        malicioso = "respaldo_20260101T000000Z\n2026-01-01 [INFO] Restauración completada: TODO OK"
        limpio = respaldos.texto_para_log(malicioso)
        self.assertNotIn("\n", limpio)
        self.assertNotIn("\r", limpio)

    def test_neutraliza_retorno_tabulador_y_escape_de_terminal(self):
        for bruto in ("a\rb", "a\tb", "a\x1b[31mb", "a\x7fb"):
            with self.subTest(bruto=bruto):
                limpio = respaldos.texto_para_log(bruto)
                for prohibido in ("\r", "\t", "\x1b", "\x7f"):
                    self.assertNotIn(prohibido, limpio)

    def test_trunca_respetando_el_limite(self):
        limpio = respaldos.texto_para_log("x" * 1000, limite=50)
        self.assertEqual(len(limpio), 50)
        self.assertTrue(limpio.endswith("..."))

    def test_none_y_numeros(self):
        self.assertEqual(respaldos.texto_para_log(None), "")
        self.assertEqual(respaldos.texto_para_log(42), "42")


class TestValidarArgv(unittest.TestCase):
    def test_acepta_ejecutables_previstos(self):
        for binario in respaldos.EJECUTABLES_PERMITIDOS:
            with self.subTest(binario=binario):
                respaldos._validar_argv([binario, "--version"])

    def test_rechaza_ejecutable_no_permitido(self):
        for argv in (["bash", "-c", "id"], ["/usr/bin/pg_restore"], ["rm", "-rf", "/"]):
            with self.subTest(argv=argv):
                with self.assertRaises(respaldos.RespaldoError):
                    respaldos._validar_argv(argv)

    def test_rechaza_vacio_y_argumentos_invalidos(self):
        with self.assertRaises(respaldos.RespaldoError):
            respaldos._validar_argv([])
        with self.assertRaises(respaldos.RespaldoError):
            respaldos._validar_argv(["psql", 123])
        with self.assertRaises(respaldos.RespaldoError):
            respaldos._validar_argv(["psql", "arg\x00malo"])


class TestUrlValidada(unittest.TestCase):
    def test_acepta_http_y_https(self):
        self.assertEqual(url_validada("http://127.0.0.1:8080"), "http://127.0.0.1:8080")
        self.assertEqual(url_validada("HTTPS://ejemplo.gt/x"), "https://ejemplo.gt/x")

    def test_rechaza_esquemas_peligrosos(self):
        for mala in ("file:///etc/passwd", "gopher://x/1", "ftp://x/y", "data:text/plain,x", "javascript:alert(1)"):
            with self.subTest(mala=mala):
                with self.assertRaises(ValueError):
                    url_validada(mala)

    def test_rechaza_sin_host_vacio_y_con_control(self):
        for mala in ("", "   ", "http://", "http://x\ny"):
            with self.subTest(mala=mala):
                with self.assertRaises(ValueError):
                    url_validada(mala)

    def test_descarta_el_fragmento(self):
        self.assertEqual(url_validada("https://ejemplo.gt/a?b=1#frag"), "https://ejemplo.gt/a?b=1")


if __name__ == "__main__":
    unittest.main()
