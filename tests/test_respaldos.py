"""
Pruebas de T7 Respaldos: cifrado por bloques, manifiesto firmado, retención,
protección de producción y ocultamiento de credenciales. No requieren PostgreSQL:
las pruebas con pg_dump/pg_restore reales se documentan en el informe de fase 2.
"""
import io
import json
import logging
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

import tests.conftest  # noqa: F401
from backend import respaldos
from scripts import respaldo_bd, restaurar_bd

CLAVE = respaldos.generar_clave_texto()
CLAVE_BYTES = respaldos.clave_maestra_desde_texto(CLAVE)
URL_PROD = "postgresql://usuario:ContrasenaSecreta123@db.ejemplo.internal:5432/aml_prod"


class AlmacenMemoria:
    """Almacén mínimo en memoria para probar retención sin disco."""

    def __init__(self):
        self.datos = {}

    def descripcion(self):
        return "memoria"

    def listar(self):
        return sorted(self.datos)

    def leer_texto(self, nombre):
        return self.datos[nombre].decode("utf-8")

    def tamano(self, nombre):
        return len(self.datos[nombre])

    def borrar(self, nombre):
        del self.datos[nombre]

    def subir(self, origen, nombre):
        self.datos[nombre] = Path(origen).read_bytes()

    def agregar_respaldo(self, fecha, valido=True, con_manifiesto=True):
        nombre = respaldos.nombre_respaldo(fecha)
        cuerpo = b"x" * 100
        self.datos[nombre + respaldos.SUFIJO_CIFRADO] = cuerpo
        if not con_manifiesto:
            return nombre
        manifiesto = _manifiesto_base(nombre, fecha, bytes_cifrado=len(cuerpo) if valido else 5)
        self.datos[nombre + respaldos.SUFIJO_MANIFIESTO] = json.dumps(manifiesto).encode("utf-8")
        return nombre


def _conexion_local(base="aml_prueba"):
    return respaldos.Conexion("localhost", "5432", "postgres", "pw", base)


def _manifiesto_base(nombre, fecha, bytes_cifrado=100, firmar=True):
    manifiesto = respaldos.construir_manifiesto(
        nombre, fecha, _conexion_local(), "a" * 64, 90, "b" * 64, bytes_cifrado,
        ["001_a.sql", "002_b.sql"], [{"licenciaid": "x", "ultimo_seq": 3, "ultimo_hash": "c" * 64, "hash_alg": "sha256"}],
        "pg_dump 16",
    )
    return respaldos.firmar_manifiesto(manifiesto, CLAVE_BYTES) if firmar else manifiesto


class ConexionTests(unittest.TestCase):
    def test_parsea_url_con_sslmode_y_oculta_credenciales(self):
        c = respaldos.parsear_database_url(URL_PROD + "?sslmode=require")
        self.assertEqual((c.host, c.puerto, c.usuario, c.base, c.sslmode),
                         ("db.ejemplo.internal", "5432", "usuario", "aml_prod", "require"))
        self.assertEqual(c.password, "ContrasenaSecreta123")
        self.assertNotIn("ContrasenaSecreta123", repr(c))
        self.assertNotIn("ContrasenaSecreta123", str(c))
        self.assertEqual(respaldos.url_sin_credenciales(URL_PROD), "postgresql://***:***@db.ejemplo.internal:5432/aml_prod")

    def test_entorno_pg_lleva_password_solo_al_hijo(self):
        c = respaldos.parsear_database_url("postgresql://u:p%40ss@h:5433/base")
        antes = dict(os.environ)
        env = c.entorno_pg()
        self.assertEqual(env["PGPASSWORD"], "p@ss")
        self.assertEqual(env["PGPORT"], "5433")
        self.assertEqual(dict(os.environ), antes)  # el entorno del proceso padre no se toca

    def test_url_invalida(self):
        with self.assertRaises(respaldos.RespaldoError):
            respaldos.parsear_database_url("mysql://u:p@h/base")
        with self.assertRaises(respaldos.RespaldoError):
            respaldos.parsear_database_url("postgresql://u:p@h/")
        with self.assertRaises(respaldos.RespaldoError):
            respaldos.parsear_database_url("postgresql://u:p@h/base;DROP")
        with self.assertRaises(respaldos.RespaldoError):
            respaldos.parsear_database_url("")

    def test_conexion_desde_variables_db(self):
        env = {"DB_HOST": "h", "DB_PORT": "5555", "DB_USER": "u", "DB_PASS": "s", "DB_NAME": "AML"}
        c = respaldos.conexion_desde_entorno(env)
        self.assertEqual(c.descripcion(), "u@h:5555/AML")
        c2 = respaldos.conexion_desde_entorno({"DATABASE_URL": URL_PROD, "DB_NAME": "otra"})
        self.assertEqual(c2.base, "aml_prod")


class ClaveTests(unittest.TestCase):
    def test_clave_valida_y_derivaciones_distintas(self):
        self.assertEqual(len(CLAVE_BYTES), 32)
        self.assertNotEqual(respaldos.clave_cifrado(CLAVE_BYTES), respaldos.clave_firma(CLAVE_BYTES))

    def test_clave_invalida(self):
        for texto in (None, "", "   ", "no-es-base64!!", "YWJj"):
            with self.assertRaises(respaldos.ClaveInvalidaError):
                respaldos.clave_maestra_desde_texto(texto)


class CifradoTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _cifrar(self, contenido, bloque=None):
        origen = self.dir / "plano.bin"
        origen.write_bytes(contenido)
        cifrado = self.dir / "cifrado.enc"
        with mock.patch.object(respaldos, "TAMANO_BLOQUE", bloque or respaldos.TAMANO_BLOQUE):
            resultado = respaldos.cifrar_archivo(origen, cifrado, CLAVE_BYTES)
        return origen, cifrado, resultado

    def test_ida_y_vuelta_multibloque(self):
        contenido = os.urandom(10_000)
        _, cifrado, (sha_plano, n_plano, sha_cif, n_cif) = self._cifrar(contenido, bloque=1024)
        self.assertEqual(n_plano, 10_000)
        self.assertEqual(n_cif, cifrado.stat().st_size)
        self.assertEqual(sha_cif, respaldos.sha256_archivo(cifrado))
        self.assertNotIn(contenido[:64], cifrado.read_bytes())
        destino = self.dir / "vuelta.bin"
        sha, n = respaldos.descifrar_archivo(cifrado, destino, CLAVE_BYTES)
        self.assertEqual((sha, n), (sha_plano, 10_000))
        self.assertEqual(destino.read_bytes(), contenido)

    def test_archivo_vacio(self):
        _, cifrado, _ = self._cifrar(b"")
        destino = self.dir / "vuelta.bin"
        self.assertEqual(respaldos.descifrar_archivo(cifrado, destino, CLAVE_BYTES)[1], 0)

    def test_clave_incorrecta(self):
        _, cifrado, _ = self._cifrar(b"datos" * 100)
        otra = respaldos.clave_maestra_desde_texto(respaldos.generar_clave_texto())
        with self.assertRaisesRegex(respaldos.IntegridadError, "clave incorrecta o archivo alterado"):
            respaldos.descifrar_archivo(cifrado, self.dir / "v.bin", otra)

    def test_byte_alterado_truncado_y_datos_extra(self):
        _, cifrado, _ = self._cifrar(os.urandom(3000), bloque=1000)
        original = cifrado.read_bytes()
        alterado = bytearray(original)
        alterado[len(respaldos.MAGIA) + 8 + 5 + 10] ^= 0x01
        cifrado.write_bytes(bytes(alterado))
        with self.assertRaises(respaldos.IntegridadError):
            respaldos.descifrar_archivo(cifrado, self.dir / "v.bin", CLAVE_BYTES)
        cifrado.write_bytes(original[:-7])
        with self.assertRaisesRegex(respaldos.IntegridadError, "truncado"):
            respaldos.descifrar_archivo(cifrado, self.dir / "v.bin", CLAVE_BYTES)
        cifrado.write_bytes(original + b"extra")
        with self.assertRaisesRegex(respaldos.IntegridadError, "datos adicionales"):
            respaldos.descifrar_archivo(cifrado, self.dir / "v.bin", CLAVE_BYTES)
        cifrado.write_bytes(b"NOESUNRESPALDO" + original)
        with self.assertRaisesRegex(respaldos.IntegridadError, "cabecera"):
            respaldos.descifrar_archivo(cifrado, self.dir / "v.bin", CLAVE_BYTES)

    def test_bloques_reordenados_se_detectan(self):
        _, cifrado, _ = self._cifrar(os.urandom(2000), bloque=1000)
        datos = cifrado.read_bytes()
        cab = len(respaldos.MAGIA) + 8
        largo1 = int.from_bytes(datos[cab:cab + 4], "big") + 5
        bloque1, bloque2 = datos[cab:cab + largo1], datos[cab + largo1:]
        cifrado.write_bytes(datos[:cab] + bloque2 + bloque1)
        with self.assertRaises(respaldos.IntegridadError):
            respaldos.descifrar_archivo(cifrado, self.dir / "v.bin", CLAVE_BYTES)


class ManifiestoTests(unittest.TestCase):
    def test_firma_y_verificacion(self):
        fecha = datetime(2026, 9, 17, 3, 0, tzinfo=timezone.utc)
        m = _manifiesto_base("respaldo_20260917T030000Z", fecha)
        self.assertEqual(m["fecha_utc"], "2026-09-17T03:00:00Z")
        self.assertEqual(m["ultima_migracion"], "002_b.sql")
        self.assertEqual(m["anclas_auditoria"][0]["ultimo_seq"], 3)
        respaldos.verificar_firma_manifiesto(m, CLAVE_BYTES)
        alterado = dict(m, sha256_plano="0" * 64)
        with self.assertRaises(respaldos.IntegridadError):
            respaldos.verificar_firma_manifiesto(alterado, CLAVE_BYTES)
        otra = respaldos.clave_maestra_desde_texto(respaldos.generar_clave_texto())
        with self.assertRaises(respaldos.IntegridadError):
            respaldos.verificar_firma_manifiesto(m, otra)
        sin_firma = {k: v for k, v in m.items() if k != "firma_hmac"}
        with self.assertRaises(respaldos.IntegridadError):
            respaldos.verificar_firma_manifiesto(sin_firma, CLAVE_BYTES)

    def test_estructura(self):
        with self.assertRaisesRegex(respaldos.IntegridadError, "JSON"):
            respaldos.cargar_manifiesto("{no json")
        with self.assertRaisesRegex(respaldos.IntegridadError, "faltan campos"):
            respaldos.cargar_manifiesto(json.dumps({"version": 1}))
        m = _manifiesto_base("respaldo_20260917T030000Z", datetime.now(timezone.utc))
        m["sha256_plano"] = "zz"
        with self.assertRaisesRegex(respaldos.IntegridadError, "SHA-256"):
            respaldos.validar_estructura_manifiesto(m)
        m = _manifiesto_base("respaldo_20260917T030000Z", datetime.now(timezone.utc))
        m["version"] = 99
        with self.assertRaisesRegex(respaldos.IntegridadError, "Versión"):
            respaldos.validar_estructura_manifiesto(m)

    def test_verificar_respaldo_completo(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            plano = d / "p.dump"
            plano.write_bytes(b"PGDMP" + os.urandom(500))
            cifrado = d / "respaldo_20260917T030000Z.dump.enc"
            sha_p, n_p, sha_c, n_c = respaldos.cifrar_archivo(plano, cifrado, CLAVE_BYTES)
            fecha = datetime(2026, 9, 17, 3, 0, tzinfo=timezone.utc)
            m = respaldos.firmar_manifiesto(respaldos.construir_manifiesto(
                "respaldo_20260917T030000Z", fecha, _conexion_local(), sha_p, n_p, sha_c, n_c, [], [], "pg_dump"),
                CLAVE_BYTES)
            salida = d / "salida.dump"
            r = respaldos.verificar_respaldo(cifrado, m, CLAVE_BYTES, salida)
            self.assertEqual(r["sha256_plano"], sha_p)
            self.assertEqual(salida.read_bytes(), plano.read_bytes())
            # Manifiesto legítimamente firmado pero con hash de otro archivo: se detecta
            m2 = respaldos.firmar_manifiesto(dict(m, sha256_cifrado="0" * 64), CLAVE_BYTES)
            with self.assertRaisesRegex(respaldos.IntegridadError, "archivo alterado"):
                respaldos.verificar_respaldo(cifrado, m2, CLAVE_BYTES, salida)
            m3 = respaldos.firmar_manifiesto(dict(m, sha256_plano="0" * 64), CLAVE_BYTES)
            with self.assertRaisesRegex(respaldos.IntegridadError, "volcado descifrado"):
                respaldos.verificar_respaldo(cifrado, m3, CLAVE_BYTES, salida)


class RetencionTests(unittest.TestCase):
    def _listado(self, dias, base=None):
        base = base or datetime(2026, 9, 17, 3, 0, tzinfo=timezone.utc)
        return [respaldos.RespaldoListado(respaldos.nombre_respaldo(base - timedelta(days=d)),
                                          base - timedelta(days=d), True) for d in dias]

    def test_politica_por_defecto_conserva_diarios_semanales_y_mensuales(self):
        respaldos_ = self._listado(range(0, 400))
        conservar = respaldos.seleccionar_conservados(respaldos_, respaldos.PoliticaRetencion())
        fechas = sorted((r.fecha for r in respaldos_ if r.nombre in conservar), reverse=True)
        base = respaldos_[0].fecha
        # 7 diarios consecutivos
        self.assertEqual(fechas[:7], [base - timedelta(days=d) for d in range(7)])
        # semanas ISO distintas entre los semanales y meses distintos entre los mensuales
        semanas = {f.isocalendar()[:2] for f in fechas}
        meses = {(f.year, f.month) for f in fechas}
        self.assertGreaterEqual(len(semanas), 4)
        self.assertEqual(len(meses), 12)
        self.assertLessEqual(len(conservar), 7 + 4 + 12)
        self.assertNotIn(respaldos_[-1].nombre, conservar)

    def test_nunca_borra_el_ultimo_valido_aunque_politica_sea_cero(self):
        listado = self._listado([0, 1, 2])
        listado[0] = respaldos.RespaldoListado(listado[0].nombre, listado[0].fecha, False, "sin manifiesto")
        conservar = respaldos.seleccionar_conservados(listado, respaldos.PoliticaRetencion(0, 0, 0))
        self.assertEqual(conservar, {listado[1].nombre})

    def test_politica_desde_entorno(self):
        p = respaldos.PoliticaRetencion.desde_entorno({"BACKUP_RETENCION_DIARIOS": "3"})
        self.assertEqual((p.diarios, p.semanales, p.mensuales), (3, 4, 12))
        with self.assertRaises(respaldos.RespaldoError):
            respaldos.PoliticaRetencion.desde_entorno({"BACKUP_RETENCION_SEMANALES": "-1"})

    def test_aplicar_retencion_borra_antiguos_y_conserva_invalidos(self):
        almacen = AlmacenMemoria()
        base = datetime.now(timezone.utc)
        recientes = [almacen.agregar_respaldo(base - timedelta(days=d)) for d in range(3)]
        antiguo = almacen.agregar_respaldo(base - timedelta(days=400))
        invalido = almacen.agregar_respaldo(base - timedelta(days=1, hours=1), valido=False)
        huerfano_reciente = almacen.agregar_respaldo(base - timedelta(days=2, hours=1), con_manifiesto=False)
        huerfano_viejo = almacen.agregar_respaldo(base - timedelta(days=45), con_manifiesto=False)
        simulado = respaldos.aplicar_retencion(almacen, respaldos.PoliticaRetencion(2, 0, 0), simular=True)
        self.assertEqual(simulado["borrados"], sorted([recientes[2], antiguo]))
        self.assertEqual(len(almacen.datos), 12)
        resultado = respaldos.aplicar_retencion(almacen, respaldos.PoliticaRetencion(2, 0, 0))
        self.assertEqual(resultado["conservados"], sorted(recientes[:2]))
        self.assertEqual(resultado["borrados"], sorted([recientes[2], antiguo, huerfano_viejo]))
        self.assertEqual(len(resultado["invalidos"]), 3)
        self.assertIn(invalido + respaldos.SUFIJO_CIFRADO, almacen.datos)
        self.assertIn(huerfano_reciente + respaldos.SUFIJO_CIFRADO, almacen.datos)
        self.assertNotIn(antiguo + respaldos.SUFIJO_MANIFIESTO, almacen.datos)
        self.assertNotIn(huerfano_viejo + respaldos.SUFIJO_CIFRADO, almacen.datos)

    def test_inventario_ignora_nombres_ajenos(self):
        almacen = AlmacenMemoria()
        almacen.datos["local_20260101.dump"] = b"x"
        almacen.datos["respaldo_malformado.dump.enc"] = b"x"
        self.assertEqual(respaldos.inventariar(almacen), [])

    def test_almacen_local_permisos(self):
        with tempfile.TemporaryDirectory() as tmp:
            almacen = respaldos.AlmacenLocal(Path(tmp) / "sub")
            origen = Path(tmp) / "o.bin"
            origen.write_bytes(b"abc")
            almacen.subir(origen, "respaldo_20260917T030000Z.dump.enc")
            ruta = Path(tmp) / "sub" / "respaldo_20260917T030000Z.dump.enc"
            self.assertEqual(oct(ruta.stat().st_mode & 0o777), "0o600")
            self.assertEqual(almacen.listar(), ["respaldo_20260917T030000Z.dump.enc"])

    def test_s3_sin_boto3_es_error_claro(self):
        with mock.patch.dict("sys.modules", {"boto3": None}):
            with self.assertRaisesRegex(respaldos.RespaldoError, "boto3"):
                respaldos.almacen_desde_entorno({"BACKUP_S3_BUCKET": "b"})


class ProduccionTests(unittest.TestCase):
    def setUp(self):
        self.prod = respaldos.parsear_database_url(URL_PROD)

    def test_deteccion(self):
        mismo = respaldos.parsear_database_url("postgresql://otro:x@DB.ejemplo.internal:5432/aml_prod")
        self.assertTrue(respaldos.es_produccion(mismo, self.prod))
        otra_base = respaldos.parsear_database_url("postgresql://u:x@db.ejemplo.internal:5432/aml_prueba")
        self.assertFalse(respaldos.es_produccion(otra_base, self.prod))
        railway = respaldos.parsear_database_url("postgresql://u:x@postgres.railway.internal:5432/railway")
        self.assertTrue(respaldos.es_produccion(railway, None))
        proxy = respaldos.parsear_database_url("postgresql://u:x@reseau.proxy.rlwy.net:29108/railway")
        self.assertTrue(respaldos.es_produccion(proxy, None))
        extra = respaldos.parsear_database_url("postgresql://u:x@bd.miempresa.com:5432/x")
        self.assertFalse(respaldos.es_produccion(extra, None))
        self.assertTrue(respaldos.es_produccion(extra, None, ["bd.miempresa.com"]))

    def test_doble_confirmacion(self):
        destino = respaldos.parsear_database_url("postgresql://u:x@postgres.railway.internal:5432/railway")
        with self.assertRaises(respaldos.ProduccionProtegidaError):
            respaldos.autorizar_destino(destino, None, False, "")
        with self.assertRaises(respaldos.ProduccionProtegidaError):
            respaldos.autorizar_destino(destino, None, True, "")
        with self.assertRaises(respaldos.ProduccionProtegidaError):
            respaldos.autorizar_destino(destino, None, False, "si")
        self.assertTrue(respaldos.autorizar_destino(destino, None, True, "si"))
        local = respaldos.parsear_database_url("postgresql://u:x@localhost:5432/aml_prueba")
        self.assertFalse(respaldos.autorizar_destino(local, self.prod, False, ""))


class SinSecretosTests(unittest.TestCase):
    def _capturar(self, secretos, mensaje, *args):
        flujo = io.StringIO()
        manejador = logging.StreamHandler(flujo)
        manejador.addFilter(respaldos.FiltroSinSecretos(secretos))
        registrador = logging.getLogger("prueba.respaldos")
        registrador.handlers = [manejador]
        registrador.propagate = False
        registrador.setLevel(logging.INFO)
        registrador.info(mensaje, *args)
        return flujo.getvalue()

    def test_filtro_oculta_url_y_secreto(self):
        salida = self._capturar(["ContrasenaSecreta123"], "conectando a %s con %s", URL_PROD, "ContrasenaSecreta123")
        self.assertNotIn("ContrasenaSecreta123", salida)
        self.assertIn("postgresql://***:***@db.ejemplo.internal", salida)

    def test_salida_segura(self):
        texto = respaldos._salida_segura("error en " + URL_PROD + " clave ContrasenaSecreta123", ["ContrasenaSecreta123"])
        self.assertNotIn("ContrasenaSecreta123", texto)

    def test_script_respaldo_sin_clave_no_expone_password(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {
            "DATABASE_URL": URL_PROD, "BACKUP_DIR": tmp, "BACKUP_ENCRYPTION_KEY": "",
        }), self.assertLogs(respaldos.logger, level="ERROR") as registro:
            self.assertEqual(respaldo_bd.main([]), 1)
        self.assertNotIn("ContrasenaSecreta123", "\n".join(registro.output))
        self.assertIn("BACKUP_ENCRYPTION_KEY", "\n".join(registro.output))

    def test_script_restaurar_bloquea_produccion_antes_de_tocar_archivos(self):
        with mock.patch.dict(os.environ, {"DATABASE_URL": URL_PROD, "BACKUP_ENCRYPTION_KEY": CLAVE,
                                          "BACKUP_PERMITIR_RESTAURAR_PRODUCCION": ""}), \
                mock.patch.object(respaldos, "_ejecutar") as ejecutar, \
                self.assertLogs(respaldos.logger, level="ERROR") as registro:
            codigo = restaurar_bd.main(["--respaldo", "respaldo_20260917T030000Z", "--destino", URL_PROD,
                                        "--confirmar-produccion"])
        self.assertEqual(codigo, 2)
        ejecutar.assert_not_called()
        texto = "\n".join(registro.output)
        self.assertIn("PRODUCCION", texto)
        self.assertNotIn("ContrasenaSecreta123", texto)

    def test_script_restaurar_nombre_invalido_y_archivo_inexistente(self):
        with mock.patch.dict(os.environ, {"BACKUP_ENCRYPTION_KEY": CLAVE, "DATABASE_URL": ""}), \
                self.assertLogs(respaldos.logger, level="ERROR"):
            self.assertEqual(restaurar_bd.main(["--respaldo", "../etc/passwd", "--verificar-solo"]), 1)
            self.assertEqual(restaurar_bd.main(["--archivo", "/no/existe.dump.enc", "--verificar-solo"]), 1)

    def test_script_restaurar_archivo_local_verificar_solo(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            plano = d / "p.dump"
            plano.write_bytes(os.urandom(300))
            nombre = "respaldo_20260917T030000Z"
            cifrado = d / (nombre + respaldos.SUFIJO_CIFRADO)
            sha_p, n_p, sha_c, n_c = respaldos.cifrar_archivo(plano, cifrado, CLAVE_BYTES)
            m = respaldos.firmar_manifiesto(respaldos.construir_manifiesto(
                nombre, datetime.now(timezone.utc), _conexion_local(), sha_p, n_p, sha_c, n_c, [], [], "pg"), CLAVE_BYTES)
            (d / (nombre + respaldos.SUFIJO_MANIFIESTO)).write_text(json.dumps(m), encoding="utf-8")
            with mock.patch.dict(os.environ, {"BACKUP_ENCRYPTION_KEY": CLAVE, "DATABASE_URL": ""}), \
                    mock.patch.object(respaldos, "_ejecutar") as ejecutar:
                self.assertEqual(restaurar_bd.main(["--archivo", str(cifrado), "--verificar-solo"]), 0)
                salida = d / "salida.dump"
                self.assertEqual(restaurar_bd.main(["--archivo", str(cifrado), "--solo-descifrar", str(salida)]), 0)
                self.assertEqual(salida.read_bytes(), plano.read_bytes())
                self.assertEqual(oct(salida.stat().st_mode & 0o777), "0o600")
                with self.assertLogs(respaldos.logger, level="ERROR"):
                    self.assertEqual(restaurar_bd.main(["--archivo", str(cifrado), "--solo-descifrar", str(salida)]), 1)
            ejecutar.assert_not_called()


if __name__ == "__main__":
    unittest.main()
