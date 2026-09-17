"""Pruebas de backend.session_token (S-01, S-02) y crud.sesion_vigente."""
import os
import time
import unittest
import uuid
from datetime import date, datetime, timedelta

import tests.conftest  # noqa: F401  (fija variables de entorno de prueba)
from backend import models, session_token
from tests.db_utils import crear_engine_pruebas, crear_session_factory


class TestSessionToken(unittest.TestCase):
    def setUp(self):
        os.environ["SESSION_SIGN_KEY"] = "clave-de-prueba-session-sign-0123456789abcdef"
        self.lid = str(uuid.uuid4())
        self.sid = str(uuid.uuid4())

    def test_caso_valido(self):
        token = session_token.firmar_restauracion(self.lid, self.sid)
        self.assertIsNotNone(token)
        datos = session_token.verificar_restauracion(token)
        self.assertIsNotNone(datos)
        self.assertEqual(datos["lid"], self.lid)
        self.assertEqual(datos["sid"], self.sid)
        self.assertIn("nonce", datos)

    def test_sin_clave_no_firma_ni_verifica(self):
        token = session_token.firmar_restauracion(self.lid, self.sid)
        os.environ["SESSION_SIGN_KEY"] = ""
        self.assertIsNone(session_token.firmar_restauracion(self.lid, self.sid))
        self.assertIsNone(session_token.verificar_restauracion(token))

    def test_clave_corta_se_rechaza(self):
        os.environ["SESSION_SIGN_KEY"] = "corta"
        self.assertIsNone(session_token.firmar_restauracion(self.lid, self.sid))

    def test_payload_sin_firma_se_rechaza(self):
        import base64, json
        cuerpo = base64.urlsafe_b64encode(json.dumps({"lid": self.lid, "sid": self.sid}).encode()).decode()
        self.assertIsNone(session_token.verificar_restauracion(cuerpo))
        self.assertIsNone(session_token.verificar_restauracion(cuerpo + "."))

    def test_firma_alterada(self):
        token = session_token.firmar_restauracion(self.lid, self.sid)
        cuerpo, firma = token.split(".")
        alterada = ("A" if firma[0] != "A" else "B") + firma[1:]
        self.assertIsNone(session_token.verificar_restauracion(f"{cuerpo}.{alterada}"))
        # Cuerpo alterado con firma original
        self.assertIsNone(session_token.verificar_restauracion(f"{cuerpo}x.{firma}"))

    def test_expirado(self):
        hace_una_hora = time.time() - 3600
        token = session_token.firmar_restauracion(self.lid, self.sid, ahora=hace_una_hora)
        self.assertIsNone(session_token.verificar_restauracion(token))

    def test_ttl_no_supera_maximo(self):
        token = session_token.firmar_restauracion(self.lid, self.sid, ttl_segundos=99999)
        datos = session_token.verificar_restauracion(token)
        self.assertLessEqual(datos["exp"] - datos["iat"], session_token.RESTORE_TTL_SECONDS)

    def test_nonce_distinto_en_cada_emision(self):
        t1 = session_token.firmar_restauracion(self.lid, self.sid)
        t2 = session_token.firmar_restauracion(self.lid, self.sid)
        self.assertNotEqual(t1, t2)


class TestSesionVigente(unittest.TestCase):
    def setUp(self):
        from backend import crud
        self.crud = crud
        engine = crear_engine_pruebas()
        self.db = crear_session_factory(engine)()
        self.licencia = models.Licencia(
            user="analista1", name="Analista Uno", mail="a1@ejemplo.com",
            licence_id=uuid.uuid4(), fecha_compra=date.today(), dias_vigencia=365,
            fecha_expiracion=date.today() + timedelta(days=365), empresa="Banco Prueba",
            password_hash="x",
        )
        self.db.add(self.licencia)
        self.db.commit()

    def _nueva_sesion(self, minutos):
        s = models.BitacoraSesions(
            sessionid=uuid.uuid4(), licenciaid=self.licencia.licence_id,
            last_activity=datetime.now() + timedelta(minutes=minutos),
        )
        self.db.add(s)
        self.db.commit()
        return s

    def test_sesion_mas_reciente_es_vigente(self):
        s1 = self._nueva_sesion(0)
        self.assertEqual(self.crud.sesion_vigente(self.db, s1.sessionid).id, self.licencia.id)

    def test_sesion_desplazada_por_otro_login(self):
        s1 = self._nueva_sesion(0)
        s2 = self._nueva_sesion(5)
        self.assertIsNone(self.crud.sesion_vigente(self.db, str(s1.sessionid)))
        self.assertIsNotNone(self.crud.sesion_vigente(self.db, str(s2.sessionid)))

    def test_sesion_inexistente_o_invalida(self):
        self.assertIsNone(self.crud.sesion_vigente(self.db, uuid.uuid4()))
        self.assertIsNone(self.crud.sesion_vigente(self.db, "no-es-uuid"))
        self.assertIsNone(self.crud.sesion_vigente(self.db, None))


if __name__ == "__main__":
    unittest.main()
