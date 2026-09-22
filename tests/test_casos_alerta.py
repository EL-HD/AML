"""Pruebas de persistencia de Casos de Alerta (T1 Fase 2): Art. 29, 30 y 34 Ley 6593.

Cubre: clave estable del caso, aislamiento por tenant (anti IDOR), flujo de
cuatro ojos, historial append-only, retención (sin borrado), auditoría
CAMBIO_ESTADO_CASO y rehidratación de estados sobre el DataFrame de casos.
Usa SQLite en memoria (tests/conftest.py).
"""
import unittest
import uuid

import pandas as pd

import tests.conftest  # noqa: F401
from backend import auditoria, casos_alerta, models
from tests.db_utils import crear_engine_pruebas, crear_session_factory

HASH_LOTE = "a" * 64
FUNDAMENTO = "Operaciones fraccionadas sin justificación económica documentada."


def _df_lote(orden=("C1", "C2")):
    return pd.DataFrame({
        "Cliente": list(orden),
        "Monto": [1000.0, 2500.0][: len(orden)],
        "Perfil": ["Comercio", "Servicios"][: len(orden)],
        "Fecha": ["2026-01-05", "2026-01-06"][: len(orden)],
        "TipoOperacion": ["Deposito", "Transferencia"][: len(orden)],
    })


class BaseCasos(unittest.TestCase):
    def setUp(self):
        crear_engine_pruebas()
        self.Session = crear_session_factory()
        self.db = self.Session()
        self.lid_a = uuid.uuid4()
        self.lid_b = uuid.uuid4()

    def tearDown(self):
        self.db.close()

    def _caso(self, licenciaid=None, cliente="cli-001", usuario="ana", rol="analista"):
        return casos_alerta.obtener_o_crear_caso(
            self.db, licenciaid or self.lid_a, HASH_LOTE, cliente, usuario, rol,
            score_max=9.5, nivel_riesgo="Alto", nombre_archivo="lote.xlsx",
        )

    def _proponer(self, caso, usuario="ana", rol="analista"):
        return casos_alerta.cambiar_estado(
            self.db, caso.licenciaid, caso.id, "Sospechosa_Propuesta", FUNDAMENTO, usuario, rol,
        )


class TestClaveEstable(BaseCasos):
    def test_hash_lote_independiente_de_orden_y_nombre(self):
        original = _df_lote()
        reordenado = original.iloc[::-1].reset_index(drop=True)[list(reversed(original.columns))]
        h1 = casos_alerta.calcular_hash_lote(original)
        h2 = casos_alerta.calcular_hash_lote(reordenado)
        self.assertEqual(len(h1), 64)
        self.assertEqual(h1, h2)

    def test_hash_lote_cambia_si_cambian_los_datos(self):
        df = _df_lote()
        h1 = casos_alerta.calcular_hash_lote(df)
        df.loc[0, "Monto"] = 1001.0
        self.assertNotEqual(h1, casos_alerta.calcular_hash_lote(df))

    def test_clave_caso_normaliza_cliente(self):
        k1 = casos_alerta.clave_caso(self.lid_a, HASH_LOTE, "  cli 001 ")
        k2 = casos_alerta.clave_caso(self.lid_a, HASH_LOTE, "CLI   001")
        self.assertEqual(k1, k2)
        self.assertNotEqual(k1, casos_alerta.clave_caso(self.lid_b, HASH_LOTE, "cli 001"))

    def test_obtener_o_crear_es_idempotente(self):
        c1 = self._caso()
        c2 = self._caso(cliente="CLI-001")
        self.assertEqual(c1.id, c2.id)
        self.assertEqual(self.db.query(models.CasoAlerta).count(), 1)
        self.assertEqual(c1.estado, "Inusual_Pendiente")


class TestAislamientoTenant(BaseCasos):
    def test_mismo_cliente_y_lote_en_dos_licencias_son_casos_distintos(self):
        ca = self._caso(self.lid_a)
        cb = self._caso(self.lid_b)
        self.assertNotEqual(ca.id, cb.id)
        self.assertEqual(len(casos_alerta.listar_casos_lote(self.db, self.lid_a, HASH_LOTE)), 1)
        self.assertEqual(len(casos_alerta.listar_casos_lote(self.db, self.lid_b, HASH_LOTE)), 1)

    def test_otra_licencia_no_puede_leer_ni_mutar_el_caso(self):
        ca = self._caso(self.lid_a)
        self.assertIsNone(casos_alerta.obtener_caso(self.db, self.lid_b, ca.id))
        self.assertEqual(casos_alerta.historial_caso(self.db, self.lid_b, ca.id), [])
        with self.assertRaises(casos_alerta.ErrorCasoAlerta):
            casos_alerta.cambiar_estado(self.db, self.lid_b, ca.id, "Descartada", FUNDAMENTO, "admin2", "admin")
        self.db.refresh(ca)
        self.assertEqual(ca.estado, "Inusual_Pendiente")


class TestCuatroOjos(BaseCasos):
    def test_analista_propone_pero_no_confirma(self):
        caso = self._proponer(self._caso())
        self.assertEqual(caso.estado, "Sospechosa_Propuesta")
        self.assertEqual(caso.propuesto_por, "ana")
        with self.assertRaises(casos_alerta.PermisoCasoDenegado):
            casos_alerta.cambiar_estado(self.db, self.lid_a, caso.id, "Sospechosa_Confirmada", FUNDAMENTO, "otro", "analista")

    def test_quien_propone_no_aprueba_aunque_sea_oficial(self):
        caso = self._proponer(self._caso(usuario="ofi", rol="oficial"), usuario="Ofi ", rol="oficial")
        with self.assertRaises(casos_alerta.PermisoCasoDenegado):
            casos_alerta.cambiar_estado(self.db, self.lid_a, caso.id, "Sospechosa_Confirmada", FUNDAMENTO, "ofi", "oficial")

    def test_oficial_distinto_aprueba_y_queda_trazado(self):
        caso = self._proponer(self._caso())
        caso = casos_alerta.cambiar_estado(self.db, self.lid_a, caso.id, "Sospechosa_Confirmada", FUNDAMENTO, "ofi", "oficial")
        self.assertEqual(caso.estado, "Sospechosa_Confirmada")
        self.assertEqual(caso.aprobado_por, "ofi")
        self.assertIsNotNone(caso.fecha_clasificacion_sospechosa)
        # Estado terminal: nadie puede seguir moviéndolo.
        self.assertEqual(casos_alerta.transiciones_permitidas(caso, "admin1", "admin"), [])

    def test_no_se_confirma_sin_propuesta_previa(self):
        caso = self._caso()
        with self.assertRaises(casos_alerta.ErrorCasoAlerta):
            casos_alerta.cambiar_estado(self.db, self.lid_a, caso.id, "Sospechosa_Confirmada", FUNDAMENTO, "admin1", "admin")

    def test_auditor_no_gestiona(self):
        caso = self._caso()
        self.assertEqual(casos_alerta.transiciones_permitidas(caso, "aud", "auditor"), [])
        with self.assertRaises(casos_alerta.PermisoCasoDenegado):
            casos_alerta.cambiar_estado(self.db, self.lid_a, caso.id, "Descartada", FUNDAMENTO, "aud", "auditor")

    def test_transiciones_permitidas_para_ui(self):
        caso = self._proponer(self._caso())
        self.assertNotIn("Sospechosa_Confirmada", casos_alerta.transiciones_permitidas(caso, "ana", "analista"))
        self.assertIn("Inusual_Examinada", casos_alerta.transiciones_permitidas(caso, "ana", "analista"))
        self.assertIn("Sospechosa_Confirmada", casos_alerta.transiciones_permitidas(caso, "ofi", "oficial"))
        self.assertEqual(casos_alerta.transiciones_permitidas(caso, "otro", "analista"), [])

    def test_fundamento_obligatorio(self):
        caso = self._caso()
        with self.assertRaises(casos_alerta.ErrorCasoAlerta):
            casos_alerta.cambiar_estado(self.db, self.lid_a, caso.id, "Descartada", "corto", "ana", "analista")


class TestHistorialYRetencion(BaseCasos):
    def test_historial_es_append_only(self):
        caso = self._proponer(self._caso())
        hist = casos_alerta.historial_caso(self.db, self.lid_a, caso.id)
        self.assertEqual([h.accion for h in hist], ["CREAR", "PROPONER_SOSPECHOSA"])
        hist[0].fundamento = "manipulado"
        with self.assertRaises(models.HistorialInmutableError):
            self.db.commit()
        self.db.rollback()
        self.db.delete(hist[0])
        with self.assertRaises(models.HistorialInmutableError):
            self.db.commit()
        self.db.rollback()
        self.assertEqual(len(casos_alerta.historial_caso(self.db, self.lid_a, caso.id)), 2)

    def test_caso_no_se_puede_borrar(self):
        caso = self._caso()
        self.db.delete(caso)
        with self.assertRaises(models.HistorialInmutableError):
            self.db.commit()
        self.db.rollback()
        self.assertEqual(self.db.query(models.CasoAlerta).count(), 1)

    def test_cambio_de_estado_genera_auditoria(self):
        caso = self._proponer(self._caso())
        eventos = self.db.query(models.BitacoraAuditoria).filter(
            models.BitacoraAuditoria.licenciaid == self.lid_a,
            models.BitacoraAuditoria.accion.like(f"{auditoria.CAMBIO_ESTADO_CASO}:%"),
        ).all()
        self.assertEqual(len(eventos), 1)
        self.assertEqual(eventos[0].modulo_accedido, "Casos de Alerta")
        self.assertIn("Sospechosa_Propuesta", eventos[0].accion)
        self.assertEqual(caso.estado, "Sospechosa_Propuesta")


class TestRehidratacion(BaseCasos):
    def test_estados_guardados_se_aplican_sobre_el_dataframe(self):
        caso = self._proponer(self._caso(cliente="cli-001"))
        casos_alerta.cambiar_estado(self.db, self.lid_a, caso.id, "Sospechosa_Confirmada", FUNDAMENTO, "ofi", "oficial")
        casos_df = pd.DataFrame({"Cliente": ["cli-001", "cli-002"], "Score_Max": [9.5, 3.0]})
        registros = casos_alerta.listar_casos_lote(self.db, self.lid_a, HASH_LOTE)
        self.assertEqual(casos_alerta.rehidratar_dataframe(casos_df, registros), 1)
        self.assertEqual(casos_df.loc[0, "Estado_Alerta"], "Sospechosa_Confirmada")
        self.assertEqual(casos_df.loc[0, "Fundamento_Examen"], FUNDAMENTO)
        self.assertIsNotNone(casos_df.loc[0, "Fecha_Clasificacion_Sospechosa"])
        self.assertEqual(casos_df.loc[1, "Estado_Alerta"], "Inusual_Pendiente")

    def test_rehidratar_no_mezcla_tenants(self):
        self._proponer(self._caso(self.lid_b, cliente="cli-001"))
        casos_df = pd.DataFrame({"Cliente": ["cli-001"]})
        registros = casos_alerta.listar_casos_lote(self.db, self.lid_a, HASH_LOTE)
        self.assertEqual(casos_alerta.rehidratar_dataframe(casos_df, registros), 0)
        self.assertEqual(casos_df.loc[0, "Estado_Alerta"], "Inusual_Pendiente")


if __name__ == "__main__":
    unittest.main()
