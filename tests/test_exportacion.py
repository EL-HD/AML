"""Pruebas de saneado anti-inyección de fórmulas (S-09) y de la bitácora (S-10)."""
import unittest
import uuid

import pandas as pd

import tests.conftest  # noqa: F401
from backend import auditoria, models
from frontend.exportacion import csv_bytes, df_seguro, sanitizar_celda, xlsx_bytes
from tests.db_utils import crear_engine_pruebas, crear_session_factory


class TestSanitizar(unittest.TestCase):
    def test_prefijos_peligrosos(self):
        for v in ("=1+1", "+cmd", "-cmd", "@SUM(A1)", "\tx", "\rx"):
            self.assertTrue(str(sanitizar_celda(v)).startswith("'"), v)

    def test_valores_normales_intactos(self):
        self.assertEqual(sanitizar_celda("Cliente 1"), "Cliente 1")
        self.assertEqual(sanitizar_celda(12.5), 12.5)
        self.assertEqual(sanitizar_celda(True), True)
        self.assertIsNone(sanitizar_celda(None))

    def test_csv_y_xlsx_saneados(self):
        df = pd.DataFrame({"=Cliente": ["=HYPERLINK(\"http://x\")", "Normal"], "Monto": [1, 2]})
        seguro = df_seguro(df)
        self.assertEqual(list(seguro.columns)[0], "'=Cliente")
        self.assertEqual(seguro.iloc[0, 0], "'=HYPERLINK(\"http://x\")")
        csv = csv_bytes(df).decode("utf-8-sig")
        self.assertIn("'=HYPERLINK", csv)
        xlsx = xlsx_bytes(df)
        leido = pd.read_excel(pd.io.common.BytesIO(xlsx))
        self.assertEqual(leido.iloc[0, 0], "'=HYPERLINK(\"http://x\")")


class TestAuditoria(unittest.TestCase):
    def setUp(self):
        self.db = crear_session_factory(crear_engine_pruebas())()

    def tearDown(self):
        self.db.close()

    def test_registra_evento_con_utc(self):
        lid = uuid.uuid4()
        self.assertTrue(auditoria.registrar_evento(self.db, lid, "u", "Módulo", auditoria.EXPORTACION))
        fila = self.db.query(models.BitacoraAuditoria).first()
        self.assertEqual(fila.accion, "EXPORTACION")
        self.assertEqual(fila.licenciaid, lid)

    def test_licencia_invalida_no_rompe(self):
        self.assertFalse(auditoria.registrar_evento(self.db, "no-uuid", "u", "Módulo"))
        self.assertFalse(auditoria.registrar_evento(self.db, None, "u", "Módulo"))


if __name__ == "__main__":
    unittest.main()
