"""Pruebas del límite de intentos, bloqueo de cuenta y mensajes uniformes (S-07)."""
import unittest
import uuid
from datetime import date, timedelta

import tests.conftest  # noqa: F401
from fastapi.testclient import TestClient

import auth_api
from backend import crud, models
from backend.rate_limit import LimitadorIntentos, ip_cliente
from tests.db_utils import crear_engine_pruebas, crear_session_factory


class TestLimitador(unittest.TestCase):
    def test_bloquea_tras_max_intentos_y_expira(self):
        lim = LimitadorIntentos(max_intentos=3, ventana_segundos=60, bloqueo_segundos=100)
        for i in range(3):
            self.assertEqual(lim.segundos_bloqueo("u", ahora=1000 + i), 0)
            lim.registrar_fallo("u", ahora=1000 + i)
        self.assertGreater(lim.segundos_bloqueo("u", ahora=1003), 0)
        self.assertEqual(lim.segundos_bloqueo("u", ahora=1200), 0)

    def test_exito_reinicia(self):
        lim = LimitadorIntentos(max_intentos=2)
        lim.registrar_fallo("u")
        lim.registrar_exito("u")
        lim.registrar_fallo("u")
        self.assertEqual(lim.segundos_bloqueo("u"), 0)

    def test_ip_cliente(self):
        self.assertEqual(ip_cliente("127.0.0.1", "203.0.113.5, 10.0.0.1"), "203.0.113.5")
        self.assertEqual(ip_cliente("127.0.0.1", "no-es-ip"), "127.0.0.1")
        # Desde una IP externa no se confía en la cabecera
        self.assertEqual(ip_cliente("198.51.100.7", "203.0.113.5"), "198.51.100.7")
        self.assertEqual(ip_cliente(None, None), "desconocido")


class TestApiLimite(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.Session = crear_session_factory(crear_engine_pruebas())
        cls.client = TestClient(auth_api.app, client=("127.0.0.1", 50000))

    def setUp(self):
        crear_engine_pruebas()
        db = self.Session()
        db.add(models.Licencia(
            user="oficial1", name="Oficial", mail="o@ejemplo.com", licence_id=uuid.uuid4(),
            fecha_compra=date.today(), dias_vigencia=365,
            fecha_expiracion=date.today() + timedelta(days=365), empresa="Banco",
            password_hash=crud.get_password_hash("Clave-Segura-2026!"), rol="oficial",
        ))
        db.commit()
        db.close()
        auth_api.limitador.limpiar()

    def _intento(self, user, pwd, ip="203.0.113.10"):
        return self.client.post("/auth/validate", json={"username": user, "password": pwd},
                                headers={"X-Forwarded-For": ip})

    def test_mensaje_unico_para_usuario_inexistente_y_clave_incorrecta(self):
        r1 = self._intento("no_existe", "x").json()
        r2 = self._intento("oficial1", "incorrecta").json()
        self.assertEqual(r1["message"], r2["message"])
        self.assertEqual(r1["exists"], r2["exists"])
        self.assertFalse(r2["is_active"])

    def test_bloqueo_por_usuario_tras_cinco_fallos(self):
        for _ in range(5):
            self.assertEqual(self._intento("oficial1", "mala").status_code, 200)
        r = self._intento("oficial1", "Clave-Segura-2026!", ip="203.0.113.99")
        self.assertEqual(r.status_code, 429)
        self.assertIn("Retry-After", r.headers)

    def test_bloqueo_por_ip_no_afecta_otra_ip(self):
        for _ in range(5):
            self._intento("otro", "mala", ip="203.0.113.1")
        self.assertEqual(self._intento("otro2", "mala", ip="203.0.113.1").status_code, 429)
        self.assertEqual(self._intento("otro2", "mala", ip="203.0.113.2").status_code, 200)

    def test_token_tambien_limitado(self):
        for _ in range(5):
            self.client.post("/token", data={"username": "oficial1", "password": "mala"})
        r = self.client.post("/token", data={"username": "oficial1", "password": "Clave-Segura-2026!"})
        self.assertEqual(r.status_code, 429)

    def test_intentos_fallidos_quedan_en_auditoria(self):
        self._intento("oficial1", "mala")
        self._intento("oficial1", "Clave-Segura-2026!")
        db = self.Session()
        acciones = [a.accion for a in db.query(models.BitacoraAuditoria).all()]
        db.close()
        self.assertIn("LOGIN_FALLIDO", acciones)
        self.assertIn("LOGIN_OK", acciones)


if __name__ == "__main__":
    unittest.main()
