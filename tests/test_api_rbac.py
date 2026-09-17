"""Pruebas de la API de autenticación: RBAC (S-04), sesión única y perfil."""
import unittest
import uuid
from datetime import date, timedelta

import tests.conftest  # noqa: F401
from fastapi.testclient import TestClient

import auth_api
from backend import crud, models
from tests.db_utils import crear_engine_pruebas, crear_session_factory


def _licencia(user, rol, password="Clave-Segura-2026!"):
    return models.Licencia(
        user=user, name=f"Usuario {user}", mail=f"{user}@ejemplo.com",
        licence_id=uuid.uuid4(), fecha_compra=date.today(), dias_vigencia=365,
        fecha_expiracion=date.today() + timedelta(days=365), empresa="Banco Prueba",
        password_hash=crud.get_password_hash(password), rol=rol,
    )


class TestApiRbac(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = crear_engine_pruebas()
        cls.Session = crear_session_factory(cls.engine)
        cls.client = TestClient(auth_api.app, client=("127.0.0.1", 50000))

    def setUp(self):
        crear_engine_pruebas()
        db = self.Session()
        db.add_all([_licencia("admin1", "admin"), _licencia("analista1", "analista")])
        db.commit()
        db.close()
        auth_api.limitador.limpiar()

    def _token(self, user, password="Clave-Segura-2026!"):
        r = self.client.post("/auth/validate", json={"username": user, "password": password})
        self.assertEqual(r.status_code, 200, r.text)
        datos = r.json()
        self.assertTrue(datos["is_active"], datos)
        self.assertIsNotNone(datos["session_id"])
        return datos["access_token"], datos

    def _auth(self, token):
        return {"Authorization": f"Bearer {token}"}

    def test_analista_recibe_403_en_licencias(self):
        token, _ = self._token("analista1")
        self.assertEqual(self.client.get("/licencias/", headers=self._auth(token)).status_code, 403)
        self.assertEqual(self.client.get("/usuarios/?q=a", headers=self._auth(token)).status_code, 403)
        self.assertEqual(self.client.delete("/licencias/1", headers=self._auth(token)).status_code, 403)
        self.assertEqual(
            self.client.put("/licencias/1", json={"name": "x"}, headers=self._auth(token)).status_code, 403
        )

    def test_admin_administra_licencias(self):
        token, _ = self._token("admin1")
        r = self.client.get("/licencias/", headers=self._auth(token))
        self.assertEqual(r.status_code, 200)
        self.assertEqual({l["rol"] for l in r.json()}, {"admin", "analista"})
        nueva = {
            "user": "oficial1", "name": "Oficial Uno", "mail": "oficial1@ejemplo.com",
            "dias_vigencia": 30, "empresa": "Banco Prueba", "password": "Clave-Segura-2026!",
            "fecha_compra": str(date.today()), "fecha_expiracion": str(date.today() + timedelta(days=30)),
            "rol": "oficial",
        }
        r = self.client.post("/licencias/", json=nueva, headers=self._auth(token))
        self.assertEqual(r.status_code, 201, r.text)
        self.assertEqual(r.json()["rol"], "oficial")

    def test_rol_invalido_se_rechaza(self):
        token, _ = self._token("admin1")
        r = self.client.put("/licencias/2", json={"rol": "superusuario"}, headers=self._auth(token))
        self.assertEqual(r.status_code, 422)

    def test_perfil_no_permite_cambiar_expiracion_ni_rol(self):
        token, datos = self._token("analista1")
        r = self.client.put("/perfil", json={"fecha_expiracion": "2099-01-01"}, headers=self._auth(token))
        self.assertEqual(r.status_code, 422)
        r = self.client.put("/perfil", json={"rol": "admin"}, headers=self._auth(token))
        self.assertEqual(r.status_code, 422)
        r = self.client.put("/perfil", json={"name": "Nuevo Nombre"}, headers=self._auth(token))
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["name"], "Nuevo Nombre")
        self.assertEqual(r.json()["rol"], "analista")

    def test_sesion_desplazada_pierde_acceso(self):
        token_viejo, _ = self._token("admin1")
        self._token("admin1")  # segundo login desplaza al primero
        r = self.client.get("/perfil", headers=self._auth(token_viejo))
        self.assertEqual(r.status_code, 401)

    def test_sin_token_401(self):
        self.assertEqual(self.client.get("/licencias/").status_code, 401)


if __name__ == "__main__":
    unittest.main()
