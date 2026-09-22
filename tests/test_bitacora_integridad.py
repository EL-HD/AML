"""Pruebas de la bitácora a prueba de alteraciones (T4 Fase 2): Art. 19 Ley 6593, OWASP A09.

Cubre: cadena válida, alteración de un campo, borrado (hueco en seq),
inserción fuera de orden, aislamiento por tenant, concurrencia simulada,
con y sin HMAC (rotación y retroceso), inmutabilidad en el ORM y serialización
canónica. Usa SQLite en memoria (tests/conftest.py); las alteraciones se
hacen con SQL crudo porque el ORM las rechaza.
"""
import hashlib
import hmac
import json
import os
import threading
import unittest
import uuid
from datetime import datetime, timezone
from unittest import mock

import tests.conftest  # noqa: F401
from sqlalchemy import text

from backend import auditoria, models
from tests.db_utils import crear_engine_pruebas, crear_session_factory

TABLA = 'public."BitacoraAuditoria"'


class BaseBitacora(unittest.TestCase):
    def setUp(self):
        crear_engine_pruebas()
        self.Session = crear_session_factory()
        self.db = self.Session()
        self.lid_a = uuid.uuid4()
        self.lid_b = uuid.uuid4()
        os.environ.pop(auditoria.VARIABLE_HMAC, None)

    def tearDown(self):
        self.db.close()
        os.environ.pop(auditoria.VARIABLE_HMAC, None)

    def _poblar(self, n=5, lid=None):
        lid = lid or self.lid_a
        for i in range(n):
            self.assertTrue(auditoria.registrar_evento(self.db, lid, f"user{i}", "Módulo", f"ACCION_{i}"))

    def _sql(self, sentencia, **params):
        self.db.execute(text(sentencia), params)
        self.db.commit()

    def _lid_sql(self, lid):
        # Uuid genérico de SQLAlchemy se guarda como CHAR(32) en SQLite
        return lid.hex


class TestCadenaValida(BaseBitacora):
    def test_cadena_valida_y_correlativo(self):
        self._poblar(5)
        filas = self.db.query(models.BitacoraAuditoria).filter_by(licenciaid=self.lid_a).order_by(models.BitacoraAuditoria.seq).all()
        self.assertEqual([f.seq for f in filas], [1, 2, 3, 4, 5])
        self.assertEqual(filas[0].hash_prev, auditoria.HASH_GENESIS)
        for anterior, actual in zip(filas, filas[1:]):
            self.assertEqual(actual.hash_prev, anterior.hash)
        self.assertTrue(all(f.hash_alg == auditoria.ALG_SHA256 for f in filas))
        r = auditoria.verificar_cadena(self.db, self.lid_a)
        self.assertTrue(r.integra)
        self.assertEqual((r.total_eslabones, r.verificados, r.primer_seq_roto), (5, 5, None))
        self.assertEqual(r.ultimo_seq, 5)
        self.assertEqual(r.ultimo_hash, filas[-1].hash)
        self.assertEqual(len(r.detalle), 5)
        self.assertTrue(all(d["estado"] == auditoria.ESTADO_OK for d in r.detalle))

    def test_licencia_sin_eventos_es_integra(self):
        r = auditoria.verificar_cadena(self.db, self.lid_a)
        self.assertTrue(r.integra)
        self.assertEqual(r.total_eslabones, 0)
        self.assertIn("Sin eslabones", r.motivo)

    def test_licenciaid_invalido(self):
        self.assertFalse(auditoria.registrar_evento(self.db, "no-es-uuid", "u", "m", "a"))
        with self.assertRaises(ValueError):
            auditoria.verificar_cadena(self.db, "no-es-uuid")

    def test_serializacion_canonica_y_hash_reproducible(self):
        marca = datetime(2026, 9, 17, 12, 30, 45, 123456, tzinfo=timezone.utc)
        datos = auditoria.serializacion_canonica(self.lid_a, 7, "ab" * 32, marca, "ana", "Casos", "VISUALIZACION")
        doc = json.loads(datos)
        self.assertEqual(list(doc.keys()), sorted(doc.keys()))
        self.assertEqual(doc["timestamp"], "2026-09-17T12:30:45.123456Z")
        self.assertEqual(doc["seq"], 7)
        self.assertEqual(doc["licenciaid"], str(self.lid_a))
        esperado = hashlib.sha256(datos).hexdigest()
        self.assertEqual(auditoria.calcular_hash(self.lid_a, 7, "ab" * 32, marca, "ana", "Casos", "VISUALIZACION"), esperado)
        # Un datetime sin zona se asume UTC (así se lee desde la base)
        self.assertEqual(auditoria.timestamp_canonico(marca.replace(tzinfo=None)), "2026-09-17T12:30:45.123456Z")
        with self.assertRaises(ValueError):
            auditoria.calcular_hash(self.lid_a, 1, "0" * 64, marca, "a", "b", "c", alg="md5")
        with self.assertRaises(ValueError):
            auditoria.calcular_hash(self.lid_a, 1, "0" * 64, marca, "a", "b", "c", alg=auditoria.ALG_HMAC)

    def test_resumen_para_exportacion(self):
        self._poblar(2)
        resumen = auditoria.verificar_cadena(self.db, self.lid_a).resumen()
        self.assertEqual(resumen["Resultado"], "Íntegra")
        self.assertEqual(resumen["Eslabones encadenados"], "2")
        self.assertEqual(resumen["HMAC configurado"], "No")


class TestAlteraciones(BaseBitacora):
    def test_alteracion_de_campo_detectada(self):
        self._poblar(5)
        self._sql(f"UPDATE {TABLA} SET accion = 'ACCION_FALSA' WHERE licenciaid = :l AND seq = 3", l=self._lid_sql(self.lid_a))
        r = auditoria.verificar_cadena(self.db, self.lid_a)
        self.assertFalse(r.integra)
        self.assertEqual(r.primer_seq_roto, 3)
        self.assertIn("campo alterado", r.motivo)
        self.assertEqual(r.verificados, 2)
        estados = [d["estado"] for d in r.detalle]
        self.assertEqual(estados, ["OK", "OK", "ROTO", "NO_VERIFICADO", "NO_VERIFICADO"])

    def test_alteracion_de_timestamp_detectada(self):
        self._poblar(3)
        self._sql(f"UPDATE {TABLA} SET timestamp = '2020-01-01 00:00:00.000000' WHERE licenciaid = :l AND seq = 1",
                  l=self._lid_sql(self.lid_a))
        r = auditoria.verificar_cadena(self.db, self.lid_a)
        self.assertFalse(r.integra)
        self.assertEqual(r.primer_seq_roto, 1)

    def test_borrado_detectado_como_hueco(self):
        self._poblar(5)
        self._sql(f"DELETE FROM {TABLA} WHERE licenciaid = :l AND seq = 3", l=self._lid_sql(self.lid_a))
        r = auditoria.verificar_cadena(self.db, self.lid_a)
        self.assertFalse(r.integra)
        self.assertEqual(r.primer_seq_roto, 4)
        self.assertIn("Hueco", r.motivo)

    def test_borrado_del_ultimo_eslabon_lo_detecta_el_siguiente_registro(self):
        # Borrar la cola no deja hueco; el siguiente evento legítimo se encadena al eslabón 4 y
        # la verificación sigue íntegra, pero el "último hash" publicado por la verificación
        # anterior ya no coincide (procedimiento: comparar el último hash entre verificaciones).
        self._poblar(5)
        ultimo_antes = auditoria.verificar_cadena(self.db, self.lid_a).ultimo_hash
        self._sql(f"DELETE FROM {TABLA} WHERE licenciaid = :l AND seq = 5", l=self._lid_sql(self.lid_a))
        self._poblar(1)
        r = auditoria.verificar_cadena(self.db, self.lid_a)
        self.assertEqual(r.ultimo_seq, 5)
        self.assertNotEqual(r.ultimo_hash, ultimo_antes)

    def test_insercion_fuera_de_orden_detectada(self):
        self._poblar(4)
        marca = auditoria.ahora_utc()
        falso = auditoria.calcular_hash(self.lid_a, 5, "f" * 64, marca, "intruso", "X", "Y")
        self._sql(
            f"INSERT INTO {TABLA} (id, licenciaid, username, timestamp, modulo_accedido, accion, seq, hash_prev, hash, hash_alg) "
            "VALUES (:id, :l, 'intruso', :ts, 'X', 'Y', 5, :prev, :h, 'sha256')",
            id=uuid.uuid4().hex, l=self._lid_sql(self.lid_a), ts=marca.replace(tzinfo=None), prev="f" * 64, h=falso,
        )
        r = auditoria.verificar_cadena(self.db, self.lid_a)
        self.assertFalse(r.integra)
        self.assertEqual(r.primer_seq_roto, 5)
        self.assertIn("hash_prev", r.motivo)

    def test_insercion_con_seq_repetido_rechazada_por_unicidad(self):
        self._poblar(2)
        with self.assertRaises(Exception):
            self._sql(
                f"INSERT INTO {TABLA} (id, licenciaid, username, timestamp, modulo_accedido, accion, seq, hash_prev, hash, hash_alg) "
                "VALUES (:id, :l, 'x', :ts, 'X', 'Y', 2, :p, :h, 'sha256')",
                id=uuid.uuid4().hex, l=self._lid_sql(self.lid_a), ts=datetime.now(), p="0" * 64, h="1" * 64,
            )
        self.db.rollback()

    def test_registros_pre_cadena_se_reportan(self):
        self._sql(
            f"INSERT INTO {TABLA} (id, licenciaid, username, timestamp, modulo_accedido, accion) "
            "VALUES (:id, :l, 'legado', :ts, 'Legado', 'VISUALIZACION')",
            id=uuid.uuid4().hex, l=self._lid_sql(self.lid_a), ts=datetime.now(),
        )
        self._poblar(2)
        r = auditoria.verificar_cadena(self.db, self.lid_a)
        self.assertTrue(r.integra)
        self.assertEqual(r.pre_cadena, 1)
        self.assertEqual(r.total_eslabones, 2)

    def test_orm_rechaza_update_y_delete(self):
        self._poblar(1)
        fila = self.db.query(models.BitacoraAuditoria).filter_by(licenciaid=self.lid_a).one()
        fila.accion = "OTRA"
        with self.assertRaises(models.HistorialInmutableError):
            self.db.commit()
        self.db.rollback()
        fila = self.db.query(models.BitacoraAuditoria).filter_by(licenciaid=self.lid_a).one()
        self.db.delete(fila)
        with self.assertRaises(models.HistorialInmutableError):
            self.db.commit()
        self.db.rollback()
        self.assertTrue(auditoria.verificar_cadena(self.db, self.lid_a).integra)


class TestTenantYConcurrencia(BaseBitacora):
    def test_aislamiento_por_tenant(self):
        self._poblar(3, self.lid_a)
        self._poblar(2, self.lid_b)
        self._poblar(1, self.lid_a)
        seqs_a = [f.seq for f in self.db.query(models.BitacoraAuditoria).filter_by(licenciaid=self.lid_a).order_by(models.BitacoraAuditoria.seq)]
        seqs_b = [f.seq for f in self.db.query(models.BitacoraAuditoria).filter_by(licenciaid=self.lid_b).order_by(models.BitacoraAuditoria.seq)]
        self.assertEqual((seqs_a, seqs_b), ([1, 2, 3, 4], [1, 2]))
        # Romper B no afecta a A
        self._sql(f"UPDATE {TABLA} SET username = 'x' WHERE licenciaid = :l AND seq = 1", l=self._lid_sql(self.lid_b))
        self.assertTrue(auditoria.verificar_cadena(self.db, self.lid_a).integra)
        rb = auditoria.verificar_cadena(self.db, self.lid_b)
        self.assertFalse(rb.integra)
        self.assertEqual(rb.total_eslabones, 2)

    def test_concurrencia_simulada_sin_bifurcacion(self):
        errores = []

        def trabajador(i):
            db = self.Session()
            try:
                for j in range(10):
                    if not auditoria.registrar_evento(db, self.lid_a, f"hilo{i}", "Concurrencia", f"E{j}"):
                        errores.append((i, j))
            finally:
                db.close()

        hilos = [threading.Thread(target=trabajador, args=(i,)) for i in range(6)]
        for t in hilos:
            t.start()
        for t in hilos:
            t.join()
        self.assertEqual(errores, [])
        r = auditoria.verificar_cadena(self.db, self.lid_a)
        self.assertTrue(r.integra, r.motivo)
        self.assertEqual(r.total_eslabones, 60)

    def test_colision_de_seq_se_reintenta(self):
        self._poblar(1)
        original = auditoria._ultimo_eslabon
        llamadas = {"n": 0}

        def ultimo_desfasado(db, lid):
            llamadas["n"] += 1
            fila = original(db, lid)
            if llamadas["n"] == 1:
                # Simula una lectura obsoleta: devuelve seq 0 para provocar seq=1 duplicado
                return type("Fila", (), {"seq": 0, "hash": auditoria.HASH_GENESIS})()
            return fila

        with mock.patch.object(auditoria, "_ultimo_eslabon", ultimo_desfasado):
            with mock.patch.object(auditoria, "_es_postgresql", return_value=False):
                self.assertTrue(auditoria.registrar_evento(self.db, self.lid_a, "u", "m", "a"))
        self.assertEqual(llamadas["n"], 2)
        r = auditoria.verificar_cadena(self.db, self.lid_a)
        self.assertTrue(r.integra)
        self.assertEqual(r.total_eslabones, 2)

    def test_error_de_bd_no_rompe_el_flujo(self):
        with mock.patch.object(auditoria, "_insertar_eslabon", side_effect=auditoria.SQLAlchemyError("caída")):
            antes = auditoria.fallos_registro
            self.assertFalse(auditoria.registrar_evento(self.db, self.lid_a, "u", "m", "a"))
            self.assertEqual(auditoria.fallos_registro, antes + 1)

    def test_bloqueo_advisory_en_postgresql(self):
        ejecutadas = []
        original_execute = self.db.execute

        def execute_espia(sentencia, *args, **kwargs):
            ejecutadas.append(str(sentencia))
            if "pg_advisory_xact_lock" in str(sentencia) or "TIME ZONE" in str(sentencia):
                return None
            return original_execute(sentencia, *args, **kwargs)

        with mock.patch.object(auditoria, "_es_postgresql", return_value=True):
            with mock.patch.object(self.db, "execute", execute_espia):
                self.assertTrue(auditoria.registrar_evento(self.db, self.lid_a, "u", "m", "a"))
        self.assertTrue(any("pg_advisory_xact_lock" in s for s in ejecutadas))
        self.assertTrue(any("TIME ZONE 'UTC'" in s for s in ejecutadas))
        clave = auditoria._clave_advisory(self.lid_a)
        self.assertTrue(-(2 ** 63) <= clave < 2 ** 63)
        self.assertEqual(clave, auditoria._clave_advisory(self.lid_a))


class TestHmac(BaseBitacora):
    def test_con_hmac_los_eslabones_se_firman_con_clave(self):
        os.environ[auditoria.VARIABLE_HMAC] = "clave-secreta-de-prueba"
        self._poblar(3)
        filas = self.db.query(models.BitacoraAuditoria).filter_by(licenciaid=self.lid_a).order_by(models.BitacoraAuditoria.seq).all()
        self.assertTrue(all(f.hash_alg == auditoria.ALG_HMAC for f in filas))
        datos = auditoria.serializacion_canonica(self.lid_a, 1, auditoria.HASH_GENESIS, filas[0].timestamp,
                                                 filas[0].username, filas[0].modulo_accedido, filas[0].accion)
        self.assertEqual(filas[0].hash, hmac.new(b"clave-secreta-de-prueba", datos, hashlib.sha256).hexdigest())
        r = auditoria.verificar_cadena(self.db, self.lid_a)
        self.assertTrue(r.integra)
        self.assertTrue(r.hmac_configurado)

    def test_hmac_alteracion_detectada_y_clave_incorrecta(self):
        os.environ[auditoria.VARIABLE_HMAC] = "clave-secreta-de-prueba"
        self._poblar(3)
        self._sql(f"UPDATE {TABLA} SET modulo_accedido = 'Otro' WHERE licenciaid = :l AND seq = 2", l=self._lid_sql(self.lid_a))
        self.assertEqual(auditoria.verificar_cadena(self.db, self.lid_a).primer_seq_roto, 2)
        os.environ[auditoria.VARIABLE_HMAC] = "otra-clave"
        r = auditoria.verificar_cadena(self.db, self.lid_a)
        self.assertFalse(r.integra)
        self.assertEqual(r.primer_seq_roto, 1)

    def test_sin_clave_los_eslabones_hmac_no_son_verificables(self):
        os.environ[auditoria.VARIABLE_HMAC] = "clave-secreta-de-prueba"
        self._poblar(2)
        os.environ.pop(auditoria.VARIABLE_HMAC)
        r = auditoria.verificar_cadena(self.db, self.lid_a)
        self.assertFalse(r.integra)
        self.assertEqual(r.primer_seq_roto, 1)
        self.assertIn(auditoria.VARIABLE_HMAC, r.motivo)
        self.assertEqual(r.detalle[0]["estado"], auditoria.ESTADO_NO_VERIFICABLE)

    def test_rotacion_sha256_a_hmac_es_valida_pero_no_el_retroceso(self):
        self._poblar(2)
        os.environ[auditoria.VARIABLE_HMAC] = "clave-secreta-de-prueba"
        self._poblar(2)
        r = auditoria.verificar_cadena(self.db, self.lid_a)
        self.assertTrue(r.integra)
        self.assertEqual(r.verificados, 4)
        # Un atacante sin clave recalcula el eslabón 5 con sha256: retroceso detectado
        prev = r.ultimo_hash
        marca = auditoria.ahora_utc()
        h = auditoria.calcular_hash(self.lid_a, 5, prev, marca, "intruso", "X", "Y")
        self._sql(
            f"INSERT INTO {TABLA} (id, licenciaid, username, timestamp, modulo_accedido, accion, seq, hash_prev, hash, hash_alg) "
            "VALUES (:id, :l, 'intruso', :ts, 'X', 'Y', 5, :prev, :h, 'sha256')",
            id=uuid.uuid4().hex, l=self._lid_sql(self.lid_a), ts=marca.replace(tzinfo=None), prev=prev, h=h,
        )
        r = auditoria.verificar_cadena(self.db, self.lid_a)
        self.assertFalse(r.integra)
        self.assertEqual(r.primer_seq_roto, 5)
        self.assertIn("Retroceso", r.motivo)


if __name__ == "__main__":
    unittest.main()
