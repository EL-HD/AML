"""Pruebas del screening de listas de sanciones (T3 Fase 2): GAFI R.6 / R.7.

Cubre: normalización, Jaro-Winkler contra valores conocidos, índice por token,
parsers OFAC SDN y ONU con fixtures ficticios, rechazo XXE y de tamaño,
descarga solo desde URLs fijas (anti SSRF) y desactivada por defecto,
persistencia con aislamiento por tenant, fundamento obligatorio, permisos por
rol, historial append-only, vínculo con el Caso de Alerta (T1) y señal en el
DataFrame de casos. Usa SQLite en memoria (tests/conftest.py).
"""
import os
import unittest
import uuid

import pandas as pd

import tests.conftest  # noqa: F401
from backend import casos_alerta, models, screening, screening_repo
from tests.db_utils import crear_engine_pruebas, crear_session_factory

# Datos ficticios con el formato real de OFAC (sin encabezado, "-0-" como nulo).
SDN_CSV = (
    b'36,"AEROCARIBBEAN AIRLINES",-0- ,"CUBA",-0- ,-0- ,-0- ,-0- ,-0- ,-0- ,-0- ,"a.k.a. \'AERO-CARIBBEAN\'."\n'
    b'173,"ANGLO-CARIBBEAN CO., LTD.",-0- ,"CUBA",-0- ,-0- ,-0- ,-0- ,-0- ,-0- ,-0- ,-0- \n'
    b'9999,"PEREZ LOPEZ, Juan Carlos","individual","SDNTK",-0- ,-0- ,-0- ,-0- ,-0- ,-0- ,-0- ,"DOB 01 Jan 1970"\n'
    b'abc,"FILA INVALIDA",-0-\n'
    b'9999,"DUPLICADO",-0- ,"X",-0- ,-0- ,-0- ,-0- ,-0- ,-0- ,-0- ,-0- \n'
)
ALT_CSV = (
    b'36,12,"aka","AERO-CARIBBEAN",-0- \n'
    b'9999,13,"a.k.a.","Juan Perez",-0- \n'
    b'9999,14,"xxx","IGNORAR TIPO",-0- \n'
    b'zzz,15,"aka","IGNORAR ENT",-0- \n'
)
ONU_XML = (
    b'<?xml version="1.0" encoding="utf-8"?><CONSOLIDATED_LIST><INDIVIDUALS>'
    b'<INDIVIDUAL><DATAID>111</DATAID><FIRST_NAME>Abdul</FIRST_NAME><SECOND_NAME>Rahman</SECOND_NAME>'
    b'<UN_LIST_TYPE>Al-Qaida</UN_LIST_TYPE><NATIONALITY><VALUE>Afganist\xc3\xa1n</VALUE></NATIONALITY>'
    b'<INDIVIDUAL_ALIAS><ALIAS_NAME>Abd al Rahman</ALIAS_NAME></INDIVIDUAL_ALIAS></INDIVIDUAL>'
    b'<INDIVIDUAL><DATAID></DATAID><FIRST_NAME>Sin Referencia</FIRST_NAME></INDIVIDUAL>'
    b'</INDIVIDUALS><ENTITIES><ENTITY><DATAID>222</DATAID><FIRST_NAME>GLOBAL RELIEF FOUNDATION</FIRST_NAME>'
    b'<ENTITY_ALIAS><ALIAS_NAME>GRF; Fondation Secours Mondial</ALIAS_NAME></ENTITY_ALIAS></ENTITY>'
    b'</ENTITIES></CONSOLIDATED_LIST>'
)
XXE_XML = (
    b'<?xml version="1.0"?><!DOCTYPE lolz [<!ENTITY lol "lol"><!ENTITY lol2 "&lol;&lol;&lol;">]>'
    b'<CONSOLIDATED_LIST><INDIVIDUALS><INDIVIDUAL><DATAID>1</DATAID><FIRST_NAME>&lol2;</FIRST_NAME>'
    b'</INDIVIDUAL></INDIVIDUALS></CONSOLIDATED_LIST>'
)
FUNDAMENTO = "Identidad verificada con documento, fecha de nacimiento y nacionalidad."
HASH_LOTE = "b" * 64


class TestNormalizacion(unittest.TestCase):
    def test_minusculas_acentos_puntuacion_y_orden(self):
        self.assertEqual(screening.normalizar_nombre("José  PÉREZ-lópez"), "jose lopez perez")
        self.assertEqual(screening.normalizar_nombre("PEREZ LOPEZ, Jose"), "jose lopez perez")

    def test_formas_juridicas_y_siglas(self):
        self.assertEqual(screening.tokenizar("Compañía Ñandú, S.A. de C.V."), ["compania", "nandu"])
        # Si solo quedan formas jurídicas se conservan todos los tokens
        self.assertEqual(screening.tokenizar("Sociedad Anónima"), ["anonima", "sociedad"])

    def test_vacios(self):
        self.assertEqual(screening.tokenizar(None), [])
        self.assertEqual(screening.normalizar_nombre("  ...  "), "")


class TestJaroWinkler(unittest.TestCase):
    def test_valores_conocidos(self):
        self.assertAlmostEqual(screening.jaro_winkler("MARTHA", "MARHTA"), 0.9611, places=4)
        self.assertAlmostEqual(screening.jaro_winkler("DWAYNE", "DUANE"), 0.8400, places=4)
        self.assertAlmostEqual(screening.jaro_winkler("DIXON", "DICKSONX"), 0.8133, places=4)
        self.assertAlmostEqual(screening.jaro("CRATE", "TRACE"), 0.7333, places=4)

    def test_extremos(self):
        self.assertEqual(screening.jaro_winkler("abc", "abc"), 1.0)
        self.assertEqual(screening.jaro_winkler("", "abc"), 0.0)
        self.assertEqual(screening.jaro_winkler("abc", "xyz"), 0.0)

    def test_comparacion_explicable(self):
        puntaje, motivo = screening.comparar_nombres("Juan Perez", "PEREZ, Juan")
        self.assertEqual(puntaje, 1.0)
        self.assertIn("exacta", motivo)
        puntaje, motivo = screening.comparar_nombres("Juan Perez", "Juan Carlos Perez Lopez")
        self.assertGreaterEqual(puntaje, screening.UMBRAL_POR_DEFECTO)
        self.assertIn("tokens", motivo)
        puntaje, _ = screening.comparar_nombres("Pedro Gomez", "Juan Carlos Perez Lopez")
        self.assertLess(puntaje, screening.UMBRAL_POR_DEFECTO)

    def test_umbral_validado(self):
        with self.assertRaises(screening.ErrorScreening):
            screening.validar_umbral(0.2)
        with self.assertRaises(screening.ErrorScreening):
            screening.validar_umbral("alto")


class TestIndice(unittest.TestCase):
    def setUp(self):
        self.entradas = [
            screening.EntradaLista("OFAC_SDN", "1", "PEREZ LOPEZ, Juan Carlos", alias=("Juan Perez",)),
            screening.EntradaLista("ONU", "2", "Abdul Rahman", alias=("Abd al Rahman",)),
            screening.EntradaLista("OFAC_SDN", "3", "Banco Delta Asia"),
        ]
        self.indice = screening.IndiceScreening(self.entradas)

    def test_candidatos_por_token_y_prefijo(self):
        self.assertEqual(len(self.indice), 5)
        self.assertTrue(self.indice.candidatos(["perez"]))
        self.assertTrue(self.indice.candidatos(["perex"]))  # prefijo "per"
        self.assertFalse(self.indice.candidatos(["zzz"]))

    def test_busqueda_devuelve_mejor_variante_por_entrada(self):
        resultados = self.indice.buscar("Juan Pérez")
        self.assertEqual(len(resultados), 1)
        self.assertEqual(resultados[0].referencia, "1")
        self.assertEqual(resultados[0].alias_coincidente, "Juan Perez")
        self.assertEqual(resultados[0].puntaje, 1.0)

    def test_sin_coincidencias_bajo_umbral(self):
        self.assertEqual(self.indice.buscar("Pedro Gomez"), [])
        self.assertEqual(self.indice.buscar(""), [])

    def test_evaluar_deduplica_consultas(self):
        salida = screening.evaluar(["Juan Perez", "juan perez", None, "nan", "Delta Asia Bank"], self.indice)
        self.assertEqual([c.referencia for c in salida], ["1", "3"])


class TestParsers(unittest.TestCase):
    def test_ofac_sdn_con_alias_y_validacion_de_filas(self):
        resultado = screening.parsear_ofac_sdn(SDN_CSV, ALT_CSV)
        self.assertEqual(resultado.fuente, "OFAC_SDN")
        self.assertEqual(len(resultado.entradas), 3)
        self.assertEqual(resultado.filas_rechazadas, 4)  # fila inválida, duplicado, alias tipo xxx, alias ent zzz
        self.assertEqual(len(resultado.hash_sha256), 64)
        por_ref = {e.referencia: e for e in resultado.entradas}
        self.assertEqual(por_ref["36"].alias, ("AERO-CARIBBEAN",))
        self.assertEqual(por_ref["9999"].alias, ("Juan Perez",))
        self.assertEqual(por_ref["9999"].tipo, "individual")
        self.assertEqual(por_ref["9999"].programa, "SDNTK")
        self.assertEqual(por_ref["173"].tipo, "individual")

    def test_ofac_sin_entradas_validas(self):
        with self.assertRaises(screening.ArchivoRechazado):
            screening.parsear_ofac_sdn(b'abc,"x"\n')

    def test_onu_xml(self):
        resultado = screening.parsear_onu_consolidada(ONU_XML)
        self.assertEqual(len(resultado.entradas), 2)
        self.assertEqual(resultado.filas_rechazadas, 1)
        individuo, entidad = resultado.entradas
        self.assertEqual(individuo.nombre, "Abdul Rahman")
        self.assertEqual(individuo.alias, ("Abd al Rahman",))
        self.assertEqual(individuo.programa, "Al-Qaida")
        self.assertEqual(individuo.nacionalidad, "Afganistán")
        self.assertEqual(entidad.tipo, "entity")
        self.assertEqual(entidad.alias, ("GRF", "Fondation Secours Mondial"))

    def test_rechaza_xxe_y_billion_laughs(self):
        with self.assertRaises(screening.ArchivoRechazado):
            screening.parsear_onu_consolidada(XXE_XML)
        with self.assertRaises(screening.ArchivoRechazado):
            screening.parsear_xml_seguro(b'<?xml version="1.0"?><!doctype x><x/>')

    def test_rechaza_xml_mal_formado_y_vacio(self):
        with self.assertRaises(screening.ArchivoRechazado):
            screening.parsear_onu_consolidada(b"<CONSOLIDATED_LIST><INDIVIDUALS>")
        with self.assertRaises(screening.ArchivoRechazado):
            screening.parsear_onu_consolidada(b"")

    def test_limite_de_tamano(self):
        with self.assertRaises(screening.ArchivoRechazado):
            screening.validar_tamano(b"x" * (screening.MAX_BYTES_ARCHIVO + 1))
        with self.assertRaises(screening.ArchivoRechazado):
            screening.validar_tamano("texto")

    def test_extension(self):
        self.assertEqual(screening.validar_extension("../../sdn.csv", ("csv",)), "sdn.csv")
        with self.assertRaises(screening.ArchivoRechazado):
            screening.validar_extension("sdn.exe", ("csv",))


class _RespuestaFalsa:
    def __init__(self, contenido: bytes, status_code: int = 200):
        self._contenido = contenido
        self.status_code = status_code
        self.cerrada = False

    def iter_content(self, chunk_size=65536):
        for i in range(0, len(self._contenido), chunk_size):
            yield self._contenido[i:i + chunk_size]

    def close(self):
        self.cerrada = True


class TestDescargaOficial(unittest.TestCase):
    def setUp(self):
        self._previo = os.environ.get(screening.VARIABLE_AUTO_DESCARGA)

    def tearDown(self):
        if self._previo is None:
            os.environ.pop(screening.VARIABLE_AUTO_DESCARGA, None)
        else:
            os.environ[screening.VARIABLE_AUTO_DESCARGA] = self._previo

    def test_desactivada_por_defecto(self):
        os.environ.pop(screening.VARIABLE_AUTO_DESCARGA, None)
        self.assertFalse(screening.auto_descarga_habilitada())
        with self.assertRaises(screening.ErrorScreening):
            screening.descargar_oficial(screening.URL_OFAC_SDN, cliente_http=lambda *a, **k: _RespuestaFalsa(b"x"))

    def test_solo_urls_fijas_https(self):
        os.environ[screening.VARIABLE_AUTO_DESCARGA] = "true"
        for url in ("http://www.treasury.gov/ofac/downloads/sdn.csv", "https://evil.example/sdn.csv",
                    "https://www.treasury.gov/otro.csv", "https://127.0.0.1/x"):
            with self.assertRaises(screening.ErrorScreening):
                screening.descargar_oficial(url, cliente_http=lambda *a, **k: _RespuestaFalsa(b"x"))

    def test_descarga_con_doble_sin_redirecciones_y_con_limite(self):
        os.environ[screening.VARIABLE_AUTO_DESCARGA] = "true"
        llamadas = {}

        def cliente(url, timeout, stream, allow_redirects):
            llamadas.update(url=url, timeout=timeout, stream=stream, allow_redirects=allow_redirects)
            return _RespuestaFalsa(SDN_CSV)

        datos = screening.descargar_oficial(screening.URL_OFAC_SDN, cliente_http=cliente)
        self.assertEqual(datos, SDN_CSV)
        self.assertFalse(llamadas["allow_redirects"])
        self.assertEqual(llamadas["timeout"], screening.TIMEOUT_DESCARGA)
        with self.assertRaises(screening.ErrorScreening):
            screening.descargar_oficial(screening.URL_OFAC_SDN, cliente_http=lambda *a, **k: _RespuestaFalsa(b"x", 302))
        with self.assertRaises(screening.ArchivoRechazado):
            screening.descargar_oficial(screening.URL_ONU_CONSOLIDADA, max_bytes=10,
                                        cliente_http=lambda *a, **k: _RespuestaFalsa(b"y" * 100))


class BaseRepo(unittest.TestCase):
    def setUp(self):
        crear_engine_pruebas()
        self.db = crear_session_factory()()
        self.lid_a = uuid.uuid4()
        self.lid_b = uuid.uuid4()
        screening_repo._cache_indice.clear()

    def tearDown(self):
        self.db.close()

    def _cargar(self):
        screening_repo.cargar_lista(self.db, "OFAC_SDN", "sdn.csv", SDN_CSV, "admin1", "admin",
                                    licenciaid=self.lid_a, secundario=ALT_CSV, version="2026-09-01")
        screening_repo.cargar_lista(self.db, "ONU", "consolidated.xml", ONU_XML, "admin1", "admin",
                                    licenciaid=self.lid_a)

    def _ejecutar(self, licenciaid=None, hash_lote=HASH_LOTE):
        return screening_repo.ejecutar_screening(
            self.db, licenciaid or self.lid_a,
            [("Juan Carlos Pérez López", "Cliente"), ("Aero Caribbean", "Cliente_Destino"),
             ("Pedro Gomez", "Cliente"), ("Global Relief Fundation", "Cliente")],
            "oficial1", "oficial", hash_lote=hash_lote,
        )


class TestCargaListas(BaseRepo):
    def test_solo_admin_carga(self):
        with self.assertRaises(screening_repo.PermisoScreeningDenegado):
            screening_repo.cargar_lista(self.db, "OFAC_SDN", "sdn.csv", SDN_CSV, "of", "oficial", licenciaid=self.lid_a)

    def test_carga_registra_version_hash_cantidad_y_desactiva_anterior(self):
        self._cargar()
        activas = {l.fuente: l for l in screening_repo.listas_activas(self.db)}
        self.assertEqual(set(activas), {"OFAC_SDN", "ONU"})
        self.assertEqual(activas["OFAC_SDN"].cantidad_entradas, 3)
        self.assertEqual(activas["OFAC_SDN"].hash_sha256, screening.hash_archivo(SDN_CSV))
        self.assertEqual(activas["OFAC_SDN"].version, "2026-09-01")
        with self.assertRaises(screening_repo.ErrorScreeningRepo):  # misma versión (mismo hash)
            screening_repo.cargar_lista(self.db, "OFAC_SDN", "sdn.csv", SDN_CSV, "admin1", "admin", licenciaid=self.lid_a)
        nueva = screening_repo.cargar_lista(self.db, "OFAC_SDN", "sdn2.csv", SDN_CSV + b"\n", "admin1", "admin",
                                            licenciaid=self.lid_a)
        activas = [l for l in screening_repo.listas_activas(self.db) if l.fuente == "OFAC_SDN"]
        self.assertEqual([l.id for l in activas], [nueva.id])
        self.assertEqual(len(screening_repo.listar_listas(self.db)), 3)
        eventos = self.db.query(models.BitacoraAuditoria).filter(
            models.BitacoraAuditoria.accion.like("CARGA_LISTA_SANCION%")).count()
        self.assertEqual(eventos, 3)

    def test_carga_rechaza_xxe(self):
        with self.assertRaises(screening.ArchivoRechazado):
            screening_repo.cargar_lista(self.db, "ONU", "c.xml", XXE_XML, "admin1", "admin", licenciaid=self.lid_a)
        self.assertEqual(screening_repo.listas_activas(self.db), [])


class TestEjecucionYDecision(BaseRepo):
    def test_sin_listas_activas(self):
        with self.assertRaises(screening_repo.ErrorScreeningRepo):
            self._ejecutar()

    def test_solo_admin_u_oficial_ejecuta(self):
        self._cargar()
        with self.assertRaises(screening_repo.PermisoScreeningDenegado):
            screening_repo.ejecutar_screening(self.db, self.lid_a, [("x", "Cliente")], "ana", "analista")

    def test_ejecucion_persiste_coincidencias_explicables_e_idempotente(self):
        self._cargar()
        resumen = self._ejecutar()
        self.assertEqual(resumen["consultas"], 4)
        self.assertEqual(resumen["nuevas"], 3)
        coincidencias = screening_repo.listar_coincidencias(self.db, self.lid_a)
        por_cliente = {c.cliente: c for c in coincidencias}
        self.assertEqual(por_cliente["Aero Caribbean"].alias_coincidente, "AERO-CARIBBEAN")
        self.assertEqual(por_cliente["Aero Caribbean"].origen, "Cliente_Destino")
        self.assertEqual(por_cliente["Juan Carlos Pérez López"].fuente, "OFAC_SDN")
        self.assertEqual(por_cliente["Global Relief Fundation"].fuente, "ONU")
        self.assertTrue(all(c.estado == "Pendiente" and c.motivo for c in coincidencias))
        # Segunda ejecución: no duplica
        resumen2 = self._ejecutar()
        self.assertEqual(resumen2["nuevas"], 0)
        self.assertEqual(resumen2["existentes"], 3)
        self.assertEqual(len(screening_repo.listar_coincidencias(self.db, self.lid_a)), 3)

    def test_aislamiento_por_tenant(self):
        self._cargar()
        self._ejecutar()
        self.assertEqual(screening_repo.listar_coincidencias(self.db, self.lid_b), [])
        self.assertEqual(screening_repo.senales_por_cliente(self.db, self.lid_b), {})
        c = screening_repo.listar_coincidencias(self.db, self.lid_a)[0]
        self.assertIsNone(screening_repo.obtener_coincidencia(self.db, self.lid_b, c.id))
        with self.assertRaises(screening_repo.ErrorScreeningRepo):
            screening_repo.decidir(self.db, self.lid_b, c.id, "Descartada", FUNDAMENTO, "of2", "oficial")
        self.assertEqual(screening_repo.historial_decisiones(self.db, self.lid_b, c.id), [])

    def test_fundamento_obligatorio_y_roles(self):
        self._cargar()
        self._ejecutar()
        c = screening_repo.listar_coincidencias(self.db, self.lid_a)[0]
        with self.assertRaises(screening_repo.ErrorScreeningRepo):
            screening_repo.decidir(self.db, self.lid_a, c.id, "Descartada", "corto", "of1", "oficial")
        with self.assertRaises(screening_repo.PermisoScreeningDenegado):
            screening_repo.decidir(self.db, self.lid_a, c.id, "Descartada", FUNDAMENTO, "ana", "analista")
        with self.assertRaises(screening_repo.PermisoScreeningDenegado):
            screening_repo.decidir(self.db, self.lid_a, c.id, "Descartada", FUNDAMENTO, "aud", "auditor")
        with self.assertRaises(screening_repo.ErrorScreeningRepo):
            screening_repo.decidir(self.db, self.lid_a, c.id, "Pendiente", FUNDAMENTO, "of1", "oficial")
        self.assertEqual(screening_repo.obtener_coincidencia(self.db, self.lid_a, c.id).estado, "Pendiente")

    def test_confirmacion_vincula_caso_y_audita(self):
        self._cargar()
        self._ejecutar()
        por_cliente = {c.cliente: c for c in screening_repo.listar_coincidencias(self.db, self.lid_a)}
        c = screening_repo.decidir(self.db, self.lid_a, por_cliente["Juan Carlos Pérez López"].id, "Confirmada",
                                   FUNDAMENTO, "of1", "oficial")
        self.assertEqual(c.estado, "Confirmada")
        self.assertEqual(c.revisor, "of1")
        self.assertIsNotNone(c.caso_id)
        caso = casos_alerta.obtener_caso(self.db, self.lid_a, c.caso_id)
        self.assertEqual(caso.cliente, "JUAN CARLOS PÉREZ LÓPEZ")
        self.assertEqual(caso.hash_lote, HASH_LOTE)
        # Contraparte (Cliente_Destino) confirmada: no crea caso, pero queda con señal
        d = screening_repo.decidir(self.db, self.lid_a, por_cliente["Aero Caribbean"].id, "Confirmada",
                                   FUNDAMENTO, "admin1", "admin")
        self.assertIsNone(d.caso_id)
        historial = screening_repo.historial_decisiones(self.db, self.lid_a, c.id)
        self.assertEqual([(x.estado_anterior, x.estado_nuevo) for x in historial], [("Pendiente", "Confirmada")])
        eventos = [e.accion for e in self.db.query(models.BitacoraAuditoria).filter(
            models.BitacoraAuditoria.licenciaid == self.lid_a).all()]
        self.assertIn("DECISION_SCREENING:Pendiente->Confirmada", eventos)
        self.assertTrue(any(e.startswith("EJECUCION_SCREENING") for e in eventos))

    def test_historial_decisiones_append_only(self):
        self._cargar()
        self._ejecutar()
        c = screening_repo.listar_coincidencias(self.db, self.lid_a)[0]
        screening_repo.decidir(self.db, self.lid_a, c.id, "Descartada", FUNDAMENTO, "of1", "oficial")
        decision = screening_repo.historial_decisiones(self.db, self.lid_a, c.id)[0]
        decision.fundamento = "alterado"
        with self.assertRaises(models.HistorialInmutableError):
            self.db.commit()
        self.db.rollback()
        self.db.delete(screening_repo.historial_decisiones(self.db, self.lid_a, c.id)[0])
        with self.assertRaises(models.HistorialInmutableError):
            self.db.commit()
        self.db.rollback()

    def test_senal_en_dataframe_de_casos(self):
        self._cargar()
        self._ejecutar()
        casos = pd.DataFrame({"Cliente": ["Juan Carlos Pérez López", "Pedro Gomez", "Global Relief Fundation"]})
        senales = screening_repo.senales_por_cliente(self.db, self.lid_a)
        self.assertEqual(screening_repo.marcar_dataframe(casos, senales), 2)
        self.assertEqual(list(casos["Screening_Sanciones"]), ["Pendiente", "Sin coincidencia", "Pendiente"])
        por_cliente = {c.cliente: c for c in screening_repo.listar_coincidencias(self.db, self.lid_a)}
        screening_repo.decidir(self.db, self.lid_a, por_cliente["Global Relief Fundation"].id, "Descartada",
                               FUNDAMENTO, "of1", "oficial")
        screening_repo.decidir(self.db, self.lid_a, por_cliente["Juan Carlos Pérez López"].id, "Confirmada",
                               FUNDAMENTO, "of1", "oficial")
        casos2 = pd.DataFrame({"Cliente": ["Juan Carlos Pérez López", "Global Relief Fundation"]})
        screening_repo.marcar_dataframe(casos2, screening_repo.senales_por_cliente(self.db, self.lid_a))
        self.assertEqual(list(casos2["Screening_Sanciones"]), ["Confirmada", "Sin coincidencia"])
        self.assertEqual(len(screening_repo.coincidencias_cliente(self.db, self.lid_a, "juan carlos perez lopez")), 1)


if __name__ == "__main__":
    unittest.main()
