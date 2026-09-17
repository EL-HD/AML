"""Pruebas del caché de análisis cifrado y ligado al tenant (S-03)."""
import os
import unittest
import uuid
from pathlib import Path

import tests.conftest  # noqa: F401
from frontend import cache_analisis


class TestCacheAnalisis(unittest.TestCase):
    def setUp(self):
        os.environ["SESSION_SIGN_KEY"] = "clave-de-prueba-session-sign-0123456789abcdef"
        self.lid_a = str(uuid.uuid4())
        self.lid_b = str(uuid.uuid4())
        self.cid = str(uuid.uuid4())
        self.contenido = b"PK-contenido-de-prueba"

    def tearDown(self):
        cache_analisis.eliminar(self.lid_a, self.cid)
        cache_analisis.eliminar(self.lid_b, self.cid)

    def test_guardar_y_cargar_mismo_tenant(self):
        self.assertTrue(cache_analisis.guardar(self.lid_a, self.cid, self.contenido))
        self.assertEqual(cache_analisis.cargar(self.lid_a, self.cid), self.contenido)

    def test_acceso_cruzado_entre_tenants_se_niega(self):
        cache_analisis.guardar(self.lid_a, self.cid, self.contenido)
        self.assertIsNone(cache_analisis.cargar(self.lid_b, self.cid))

    def test_contenido_en_disco_esta_cifrado_y_con_permisos_0600(self):
        cache_analisis.guardar(self.lid_a, self.cid, self.contenido)
        ruta = cache_analisis.ruta_cache(self.lid_a, self.cid)
        crudo = Path(ruta).read_bytes()
        self.assertNotIn(self.contenido, crudo)
        self.assertEqual(oct(ruta.stat().st_mode & 0o777), "0o600")

    def test_identificadores_invalidos(self):
        self.assertIsNone(cache_analisis.ruta_cache("../../etc/passwd", self.cid))
        self.assertIsNone(cache_analisis.ruta_cache(self.lid_a, "x"))
        self.assertFalse(cache_analisis.guardar(None, self.cid, b"x"))
        self.assertIsNone(cache_analisis.cargar(None, None))

    def test_sin_clave_no_persiste(self):
        os.environ["SESSION_SIGN_KEY"] = ""
        self.assertFalse(cache_analisis.guardar(self.lid_a, self.cid, self.contenido))
        self.assertIsNone(cache_analisis.cargar(self.lid_a, self.cid))

    def test_archivo_manipulado_se_descarta(self):
        cache_analisis.guardar(self.lid_a, self.cid, self.contenido)
        ruta = cache_analisis.ruta_cache(self.lid_a, self.cid)
        ruta.write_bytes(b"basura")
        self.assertIsNone(cache_analisis.cargar(self.lid_a, self.cid))
        self.assertFalse(ruta.exists())

    def test_expirado_se_elimina(self):
        cache_analisis.guardar(self.lid_a, self.cid, self.contenido)
        ruta = cache_analisis.ruta_cache(self.lid_a, self.cid)
        viejo = ruta.stat().st_mtime - cache_analisis.TTL_SEGUNDOS - 10
        os.utime(ruta, (viejo, viejo))
        self.assertIsNone(cache_analisis.cargar(self.lid_a, self.cid))
        self.assertFalse(ruta.exists())


if __name__ == "__main__":
    unittest.main()
