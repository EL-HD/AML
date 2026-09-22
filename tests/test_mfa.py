"""Pruebas de MFA TOTP (T6 Fase 2): RFC 6238, ventana, anti-replay, cifrado,
token intermedio, flujo API completo, recuperación de un solo uso, política
MFA_ENFORCE, restablecimiento y restauración de sesión."""
import base64
import json
import os
import time
import unittest
import uuid
from datetime import date, datetime, timedelta, timezone

import tests.conftest  # noqa: F401
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

import auth_api
from backend import auditoria, crud, mfa, models, session_token, totp
from tests.db_utils import crear_engine_pruebas, crear_session_factory

CLAVE_FERNET = Fernet.generate_key().decode("ascii")
SECRETO_RFC = b"12345678901234567890"
SECRETO_RFC_B32 = base64.b32encode(SECRETO_RFC).decode("ascii")
PASSWORD = "Clave-Segura-2026!"


def _licencia(user, rol):
    return models.Licencia(
        user=user, name=f"Usuario {user}", mail=f"{user}@ejemplo.com",
        licence_id=uuid.uuid4(), fecha_compra=date.today(), dias_vigencia=365,
        fecha_expiracion=date.today() + timedelta(days=365), empresa="Banco Prueba",
        password_hash=crud.get_password_hash(PASSWORD), rol=rol,
    )


def _codigo_actual(secreto_b32: str, desplazamiento_pasos: int = 0) -> str:
    return totp.totp(secreto_b32, time.time() + desplazamiento_pasos * totp.PASO_SEGUNDOS)


class TestTotpRfc(unittest.TestCase):
    """Vectores de prueba oficiales: RFC 4226 (apéndice D) y RFC 6238 (apéndice B, SHA-1)."""

    def test_vectores_hotp_rfc4226(self):
        esperados = ["755224", "287082", "359152", "969429", "338314",
                     "254676", "287922", "162583", "399871", "520489"]
        for contador, esperado in enumerate(esperados):
            self.assertEqual(totp.hotp(SECRETO_RFC, contador), esperado)

    def test_vectores_totp_rfc6238_sha1(self):
        vectores = {59: "94287082", 1111111109: "07081804", 1111111111: "14050471",
                    1234567890: "89005924", 2000000000: "69279037", 20000000000: "65353130"}
        for momento, esperado in vectores.items():
            self.assertEqual(totp.totp(SECRETO_RFC_B32, momento, digitos=8), esperado)
            self.assertEqual(totp.totp(SECRETO_RFC_B32, momento), esperado[-6:])

    def test_secreto_generado_es_base32_de_160_bits(self):
        secreto = totp.generar_secreto()
        self.assertEqual(len(totp.decodificar_secreto(secreto)), 20)
        self.assertRegex(secreto, r"^[A-Z2-7]+$")
        self.assertEqual(totp.secreto_en_bloques("ABCDEFGHIJ"), "ABCD EFGH IJ")
        with self.assertRaises(ValueError):
            totp.decodificar_secreto("no-es-base32!")

    def test_uri_otpauth(self):
        uri = totp.uri_otpauth("ABCDEFGH", "oficial1")
        self.assertTrue(uri.startswith("otpauth://totp/Sovereign%20AML%3Aoficial1?secret=ABCDEFGH"))
        self.assertIn("issuer=Sovereign%20AML", uri)
        self.assertIn("digits=6", uri)
        self.assertIn("period=30", uri)

    def test_ventana_mas_menos_uno(self):
        momento = 1_700_000_000
        for paso in (-1, 0, 1):
            codigo = totp.totp(SECRETO_RFC_B32, momento + paso * 30)
            self.assertEqual(totp.verificar_totp(SECRETO_RFC_B32, codigo, momento), momento // 30 + paso)
        for paso in (-2, 2):
            codigo = totp.totp(SECRETO_RFC_B32, momento + paso * 30)
            self.assertIsNone(totp.verificar_totp(SECRETO_RFC_B32, codigo, momento))

    def test_anti_replay_por_contador(self):
        momento = 1_700_000_000
        contador = momento // 30
        codigo = totp.totp(SECRETO_RFC_B32, momento)
        self.assertEqual(totp.verificar_totp(SECRETO_RFC_B32, codigo, momento, ultimo_contador=contador - 1), contador)
        self.assertIsNone(totp.verificar_totp(SECRETO_RFC_B32, codigo, momento, ultimo_contador=contador))
        # Un código del paso anterior tampoco sirve si ya se aceptó el actual
        anterior = totp.totp(SECRETO_RFC_B32, momento - 30)
        self.assertIsNone(totp.verificar_totp(SECRETO_RFC_B32, anterior, momento, ultimo_contador=contador))

    def test_formatos_invalidos(self):
        for codigo in ("", "12345", "1234567", "abcdef", None, "12 34 5x"):
            self.assertIsNone(totp.verificar_totp(SECRETO_RFC_B32, codigo, 1_700_000_000))
        self.assertIsNone(totp.verificar_totp("secreto!invalido", "123456", 1_700_000_000))

    def test_codigos_recuperacion_hash_y_verificacion(self):
        codigos = totp.generar_codigos_recuperacion()
        self.assertEqual(len(set(codigos)), 10)
        for c in codigos:
            self.assertRegex(c, r"^[A-Z2-9]{5}-[A-Z2-9]{5}$")
        hash_ = totp.hash_codigo_recuperacion(codigos[0])
        self.assertTrue(hash_.startswith("pbkdf2_sha256$"))
        self.assertNotIn(codigos[0].replace("-", ""), hash_)
        self.assertTrue(totp.verificar_codigo_recuperacion(codigos[0], hash_))
        self.assertTrue(totp.verificar_codigo_recuperacion(codigos[0].lower().replace("-", " "), hash_))
        self.assertFalse(totp.verificar_codigo_recuperacion(codigos[1], hash_))
        self.assertFalse(totp.verificar_codigo_recuperacion(codigos[0], "basura"))
        self.assertFalse(totp.verificar_codigo_recuperacion(codigos[0], "pbkdf2_sha256$1$00$00"))


class _BaseMfa(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = crear_engine_pruebas()
        cls.Session = crear_session_factory(cls.engine)
        cls.client = TestClient(auth_api.app, client=("127.0.0.1", 50000))

    def setUp(self):
        os.environ["MFA_ENCRYPTION_KEY"] = CLAVE_FERNET
        os.environ["MFA_ENFORCE"] = "false"
        crear_engine_pruebas()
        db = self.Session()
        db.add_all([_licencia("admin1", "admin"), _licencia("oficial1", "oficial"),
                    _licencia("admin2", "admin"), _licencia("analista1", "analista")])
        db.commit()
        db.close()
        auth_api.limitador.limpiar()
        auth_api._mfa_jti_usados.clear()

    def tearDown(self):
        os.environ.pop("MFA_ENCRYPTION_KEY", None)
        os.environ.pop("MFA_ENFORCE", None)

    def _usuario(self, db, user):
        return crud.get_licencia_by_user(db, user)

    def _enrolar(self, user):
        """Enrola por backend y devuelve (secreto, codigos_recuperacion)."""
        db = self.Session()
        try:
            lic = self._usuario(db, user)
            material = mfa.iniciar_enrolamiento(db, lic)
            codigos = mfa.confirmar_enrolamiento(db, lic, _codigo_actual(material["secreto"]))
            return material["secreto"], codigos
        finally:
            db.close()

    def _acciones(self, user):
        db = self.Session()
        try:
            lic = self._usuario(db, user)
            filas = (db.query(models.BitacoraAuditoria)
                     .filter(models.BitacoraAuditoria.licenciaid == lic.licence_id)
                     .order_by(models.BitacoraAuditoria.seq).all())
            return [f.accion for f in filas]
        finally:
            db.close()

    def _auth(self, token):
        return {"Authorization": f"Bearer {token}"}

    def _login(self, user, password=PASSWORD):
        r = self.client.post("/auth/validate", json={"username": user, "password": password})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()


class TestMfaBackend(_BaseMfa):
    def test_secreto_cifrado_en_bd_y_descifrable(self):
        db = self.Session()
        lic = self._usuario(db, "oficial1")
        material = mfa.iniciar_enrolamiento(db, lic)
        registro = mfa.obtener(db, lic.licence_id)
        self.assertNotEqual(registro.secreto_cifrado, material["secreto"])
        self.assertNotIn(material["secreto"], registro.secreto_cifrado)
        self.assertEqual(mfa.descifrar_secreto(registro.secreto_cifrado), material["secreto"])
        self.assertFalse(registro.activo)
        self.assertIn("otpauth://totp/", material["uri"])
        # Con otra clave el secreto no se descifra (fail-closed)
        os.environ["MFA_ENCRYPTION_KEY"] = Fernet.generate_key().decode("ascii")
        self.assertIsNone(mfa.descifrar_secreto(registro.secreto_cifrado))
        db.close()

    def test_sin_clave_no_se_enrola_pero_estado_informa(self):
        os.environ["MFA_ENCRYPTION_KEY"] = ""
        db = self.Session()
        lic = self._usuario(db, "admin1")
        self.assertFalse(mfa.mfa_disponible())
        self.assertFalse(mfa.estado(db, lic).disponible)
        with self.assertRaises(mfa.MfaError):
            mfa.iniciar_enrolamiento(db, lic)
        os.environ["MFA_ENCRYPTION_KEY"] = "clave-invalida"
        self.assertFalse(mfa.mfa_disponible())
        db.close()

    def test_confirmacion_exige_codigo_valido_y_audita(self):
        db = self.Session()
        lic = self._usuario(db, "oficial1")
        material = mfa.iniciar_enrolamiento(db, lic)
        with self.assertRaises(mfa.MfaError):
            mfa.confirmar_enrolamiento(db, lic, "000000")
        self.assertFalse(mfa.esta_activo(db, lic.licence_id))
        codigos = mfa.confirmar_enrolamiento(db, lic, _codigo_actual(material["secreto"]))
        self.assertEqual(len(codigos), 10)
        registro = mfa.obtener(db, lic.licence_id)
        self.assertTrue(registro.activo)
        self.assertEqual(registro.codigos_restantes, 10)
        for c in codigos:
            self.assertNotIn(c.replace("-", ""), registro.codigos_recuperacion)
        self.assertEqual(len(json.loads(registro.codigos_recuperacion)), 10)
        db.close()
        self.assertEqual(self._acciones("oficial1"), [auditoria.MFA_FALLIDO, auditoria.MFA_ENROLADO])

    def test_replay_del_mismo_codigo_se_rechaza(self):
        secreto, _ = self._enrolar("oficial1")
        db = self.Session()
        lic = self._usuario(db, "oficial1")
        sid = uuid.uuid4()
        # El código usado para confirmar ya no sirve (mismo contador)
        self.assertFalse(mfa.verificar(db, lic, _codigo_actual(secreto), sid))
        siguiente = _codigo_actual(secreto, 1)
        self.assertTrue(mfa.verificar(db, lic, siguiente, sid))
        self.assertFalse(mfa.verificar(db, lic, siguiente, uuid.uuid4()))
        self.assertTrue(mfa.sesion_autorizada(db, lic, sid))
        db.close()

    def test_codigo_recuperacion_un_solo_uso(self):
        _, codigos = self._enrolar("admin1")
        db = self.Session()
        lic = self._usuario(db, "admin1")
        sid = uuid.uuid4()
        self.assertTrue(mfa.verificar(db, lic, codigos[3], sid))
        self.assertEqual(mfa.obtener(db, lic.licence_id).codigos_restantes, 9)
        self.assertFalse(mfa.verificar(db, lic, codigos[3], sid))
        self.assertTrue(mfa.verificar(db, lic, codigos[4].lower(), sid))
        db.close()
        acciones = self._acciones("admin1")
        self.assertEqual(acciones.count(auditoria.MFA_RECUPERACION), 2)
        self.assertEqual(acciones.count(auditoria.MFA_FALLIDO), 1)

    def test_recuperacion_funciona_sin_clave_de_cifrado(self):
        secreto, codigos = self._enrolar("admin1")
        os.environ["MFA_ENCRYPTION_KEY"] = ""
        db = self.Session()
        lic = self._usuario(db, "admin1")
        self.assertFalse(mfa.verificar(db, lic, _codigo_actual(secreto, 1), uuid.uuid4()))
        self.assertTrue(mfa.verificar(db, lic, codigos[0], uuid.uuid4()))
        db.close()

    def test_sesion_autorizada_solo_la_que_supero_mfa(self):
        db = self.Session()
        lic = self._usuario(db, "oficial1")
        self.assertTrue(mfa.sesion_autorizada(db, lic, uuid.uuid4()))  # sin MFA
        db.close()
        secreto, _ = self._enrolar("oficial1")
        db = self.Session()
        lic = self._usuario(db, "oficial1")
        self.assertFalse(mfa.sesion_autorizada(db, lic, uuid.uuid4()))
        self.assertFalse(mfa.sesion_autorizada(db, lic, "no-es-uuid"))
        sid = uuid.uuid4()
        self.assertTrue(mfa.verificar(db, lic, _codigo_actual(secreto, 1), sid))
        self.assertTrue(mfa.sesion_autorizada(db, lic, str(sid)))
        db.close()

    def test_restauracion_de_sesion_firmada_no_salta_mfa(self):
        """Un token de restauración válido con una sesión creada solo por contraseña no autoriza."""
        secreto, _ = self._enrolar("oficial1")
        os.environ["SESSION_SIGN_KEY"] = "clave-de-prueba-session-sign-0123456789abcdef"
        db = self.Session()
        _, activo, _, lic = crud.validate_auth(db, "oficial1", PASSWORD)
        self.assertTrue(activo)
        sid = lic.current_session_id
        token = session_token.firmar_restauracion(lic.licence_id, sid)
        datos = session_token.verificar_restauracion(token)
        self.assertIsNotNone(datos)
        usuario = crud.sesion_vigente(db, datos["sid"])
        self.assertIsNotNone(usuario)
        self.assertFalse(mfa.sesion_autorizada(db, usuario, datos["sid"]))
        self.assertTrue(mfa.verificar(db, usuario, _codigo_actual(secreto, 1), sid))
        self.assertTrue(mfa.sesion_autorizada(db, usuario, datos["sid"]))
        db.close()

    def test_app_py_valida_mfa_al_restaurar(self):
        from pathlib import Path
        fuente = (Path(__file__).resolve().parent.parent / "app.py").read_text(encoding="utf-8")
        inicio = fuente.index("def _restaurar_desde_token")
        cuerpo = fuente[inicio:fuente.index("\ndef ", inicio + 10)]
        self.assertIn("mfa.sesion_autorizada(db, usuario, datos[\"sid\"])", cuerpo)

    def test_politica_enforce(self):
        db = self.Session()
        admin, analista = self._usuario(db, "admin1"), self._usuario(db, "analista1")
        self.assertFalse(mfa.enrolamiento_pendiente(db, admin))
        os.environ["MFA_ENFORCE"] = "true"
        self.assertTrue(mfa.enrolamiento_pendiente(db, admin))
        self.assertFalse(mfa.enrolamiento_pendiente(db, analista))
        estado = mfa.estado(db, admin)
        self.assertTrue(estado.obligatorio and estado.enrolamiento_pendiente and not estado.activo)
        db.close()
        self._enrolar("admin1")
        db = self.Session()
        self.assertFalse(mfa.enrolamiento_pendiente(db, self._usuario(db, "admin1")))
        db.close()

    def test_restablecimiento_propio_y_por_admin(self):
        secreto, codigos = self._enrolar("oficial1")
        self._enrolar("admin1")
        db = self.Session()
        oficial, admin, admin2 = (self._usuario(db, u) for u in ("oficial1", "admin1", "admin2"))
        with self.assertRaises(mfa.MfaError):
            mfa.restablecer_propio(db, oficial, "000000")
        self.assertTrue(mfa.esta_activo(db, oficial.licence_id))
        with self.assertRaises(mfa.MfaError):
            mfa.restablecer_por_admin(db, admin, admin)  # el propio, sin código
        with self.assertRaises(mfa.MfaError):
            mfa.restablecer_por_admin(db, oficial, admin)  # no es admin
        mfa.restablecer_por_admin(db, admin2, admin)
        self.assertFalse(mfa.esta_activo(db, admin.licence_id))
        mfa.restablecer_propio(db, oficial, codigos[0])
        self.assertFalse(mfa.esta_activo(db, oficial.licence_id))
        with self.assertRaises(mfa.MfaError):
            mfa.restablecer_por_admin(db, admin2, self._usuario(db, "analista1"))  # sin MFA configurado
        db.close()
        self.assertIn(f"{auditoria.MFA_RESTABLECIDO}:propio", self._acciones("oficial1"))
        self.assertIn(f"{auditoria.MFA_RESTABLECIDO}:admin=admin2", self._acciones("admin1"))
        self.assertIn(f"{auditoria.MFA_RESTABLECIDO}:usuario=admin1", self._acciones("admin2"))


class TestMfaApi(_BaseMfa):
    def test_login_sin_mfa_no_cambia(self):
        datos = self._login("analista1")
        self.assertTrue(datos["is_active"])
        self.assertFalse(datos["mfa_requerido"])
        self.assertFalse(datos["mfa_enrolamiento_pendiente"])
        self.assertIsNotNone(datos["access_token"])

    def test_flujo_completo_login_con_mfa(self):
        secreto, _ = self._enrolar("oficial1")
        datos = self._login("oficial1")
        self.assertTrue(datos["mfa_requerido"])
        self.assertFalse(datos["is_active"])
        self.assertIsNone(datos["licencia"])
        self.assertIsNone(datos["access_token"])
        self.assertIsNone(datos["session_id"])
        token_mfa = datos["mfa_token"]
        # El token intermedio no da acceso a nada
        self.assertEqual(self.client.get("/perfil", headers=self._auth(token_mfa)).status_code, 401)
        self.assertEqual(self.client.get("/auth/mfa/estado", headers=self._auth(token_mfa)).status_code, 401)
        # Código incorrecto
        r = self.client.post("/auth/mfa/verificar", json={"mfa_token": token_mfa, "codigo": "000000"})
        self.assertEqual(r.status_code, 401)
        # Código correcto
        r = self.client.post("/auth/mfa/verificar",
                             json={"mfa_token": token_mfa, "codigo": _codigo_actual(secreto, 1)})
        self.assertEqual(r.status_code, 200, r.text)
        final = r.json()
        self.assertTrue(final["is_active"])
        self.assertEqual(final["licencia"]["user"], "oficial1")
        self.assertIsNotNone(final["session_id"])
        r = self.client.get("/perfil", headers=self._auth(final["access_token"]))
        self.assertEqual(r.status_code, 200, r.text)
        acciones = self._acciones("oficial1")
        self.assertIn(auditoria.MFA_OK, acciones)
        self.assertIn(auditoria.MFA_FALLIDO, acciones)

    def test_token_intermedio_un_solo_uso_y_expiracion(self):
        secreto, _ = self._enrolar("oficial1")
        token_mfa = self._login("oficial1")["mfa_token"]
        r = self.client.post("/auth/mfa/verificar",
                             json={"mfa_token": token_mfa, "codigo": _codigo_actual(secreto, 1)})
        self.assertEqual(r.status_code, 200, r.text)
        # Reutilización del mismo token (aunque el código sea nuevo)
        r = self.client.post("/auth/mfa/verificar",
                             json={"mfa_token": token_mfa, "codigo": _codigo_actual(secreto, 1)})
        self.assertEqual(r.status_code, 401)
        # Token expirado
        import jwt as pyjwt
        claims = pyjwt.decode(token_mfa, options={"verify_signature": False}, audience=auth_api.JWT_AUDIENCE)
        self.assertEqual(claims["typ"], "mfa")
        self.assertLessEqual(claims["exp"] - claims["iat"], 5 * 60)
        claims["exp"] = int(datetime.now(timezone.utc).timestamp()) - 10
        claims["jti"] = uuid.uuid4().hex
        vencido = pyjwt.encode(claims, auth_api.SECRET_KEY, algorithm="HS256")
        r = self.client.post("/auth/mfa/verificar", json={"mfa_token": vencido, "codigo": _codigo_actual(secreto, 1)})
        self.assertEqual(r.status_code, 401)
        # Un JWT de acceso no sirve como token MFA ni al revés
        acceso = self._login("analista1")["access_token"]
        r = self.client.post("/auth/mfa/verificar", json={"mfa_token": acceso, "codigo": "123456"})
        self.assertEqual(r.status_code, 401)

    def test_jwt_sin_mfa_no_accede_aunque_sea_valido(self):
        """Un JWT de acceso forjado con la firma legítima pero con una sesión que no superó el MFA se rechaza."""
        self._enrolar("oficial1")
        db = self.Session()
        _, _, _, lic = crud.validate_auth(db, "oficial1", PASSWORD)
        token = auth_api._token_final(lic)
        db.close()
        self.assertEqual(self.client.get("/perfil", headers=self._auth(token)).status_code, 401)

    def test_verificar_tiene_limite_de_intentos(self):
        self._enrolar("oficial1")
        token_mfa = self._login("oficial1")["mfa_token"]
        for _ in range(auth_api._RL_MAX_ATTEMPTS):
            r = self.client.post("/auth/mfa/verificar", json={"mfa_token": token_mfa, "codigo": "000000"})
            self.assertEqual(r.status_code, 401)
        r = self.client.post("/auth/mfa/verificar", json={"mfa_token": token_mfa, "codigo": "000000"})
        self.assertEqual(r.status_code, 429)
        self.assertIn("Retry-After", r.headers)

    def test_endpoint_token_oauth2_exige_codigo(self):
        secreto, codigos = self._enrolar("oficial1")
        r = self.client.post("/token", data={"username": "oficial1", "password": PASSWORD})
        self.assertEqual(r.status_code, 401)
        r = self.client.post("/token", data={"username": "oficial1", "password": PASSWORD, "codigo_mfa": "000000"})
        self.assertEqual(r.status_code, 401)
        r = self.client.post("/token", data={"username": "oficial1", "password": PASSWORD,
                                             "codigo_mfa": _codigo_actual(secreto, 1)})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(self.client.get("/perfil", headers=self._auth(r.json()["access_token"])).status_code, 200)
        r = self.client.post("/token", data={"username": "oficial1", "password": PASSWORD, "codigo_mfa": codigos[0]})
        self.assertEqual(r.status_code, 200, r.text)

    def test_enrolamiento_por_api_y_recuperacion(self):
        datos = self._login("admin1")
        cab = self._auth(datos["access_token"])
        r = self.client.get("/auth/mfa/estado", headers=cab)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {"disponible": True, "activo": False, "obligatorio": False,
                                    "enrolamiento_pendiente": False, "codigos_restantes": 0, "enrolado_en": None})
        r = self.client.post("/auth/mfa/enrolar", headers=cab)
        self.assertEqual(r.status_code, 200, r.text)
        material = r.json()
        self.assertIn("otpauth://totp/", material["uri"])
        r = self.client.post("/auth/mfa/confirmar", json={"codigo": "000000"}, headers=cab)
        self.assertEqual(r.status_code, 400)
        r = self.client.post("/auth/mfa/confirmar", json={"codigo": _codigo_actual(material["secreto"])}, headers=cab)
        self.assertEqual(r.status_code, 200, r.text)
        codigos = r.json()["codigos_recuperacion"]
        self.assertEqual(len(codigos), 10)
        # La sesión que confirmó sigue autorizada; el estado refleja el MFA activo
        r = self.client.get("/auth/mfa/estado", headers=cab)
        self.assertTrue(r.json()["activo"])
        self.assertEqual(r.json()["codigos_restantes"], 10)
        # Enrolar de nuevo con MFA activo se rechaza
        self.assertEqual(self.client.post("/auth/mfa/enrolar", headers=cab).status_code, 409)
        # Nuevo login: exige MFA; recuperación de un solo uso
        token_mfa = self._login("admin1")["mfa_token"]
        r = self.client.post("/auth/mfa/verificar", json={"mfa_token": token_mfa, "codigo": codigos[0]})
        self.assertEqual(r.status_code, 200, r.text)
        token_mfa = self._login("admin1")["mfa_token"]
        r = self.client.post("/auth/mfa/verificar", json={"mfa_token": token_mfa, "codigo": codigos[0]})
        self.assertEqual(r.status_code, 401)
        self.assertIn(auditoria.MFA_RECUPERACION, self._acciones("admin1"))

    def test_enrolar_sin_clave_devuelve_409(self):
        os.environ["MFA_ENCRYPTION_KEY"] = ""
        cab = self._auth(self._login("admin1")["access_token"])
        self.assertFalse(self.client.get("/auth/mfa/estado", headers=cab).json()["disponible"])
        r = self.client.post("/auth/mfa/enrolar", headers=cab)
        self.assertEqual(r.status_code, 409)
        self.assertIn("MFA_ENCRYPTION_KEY", r.json()["detail"])

    def test_enforce_bloquea_todo_salvo_enrolamiento(self):
        os.environ["MFA_ENFORCE"] = "true"
        datos = self._login("oficial1")
        self.assertTrue(datos["is_active"])
        self.assertTrue(datos["mfa_enrolamiento_pendiente"])
        cab = self._auth(datos["access_token"])
        self.assertEqual(self.client.get("/perfil", headers=cab).status_code, 403)
        self.assertEqual(self.client.get("/auth/mfa/estado", headers=cab).status_code, 200)
        r = self.client.post("/auth/mfa/enrolar", headers=cab)
        self.assertEqual(r.status_code, 200)
        r = self.client.post("/auth/mfa/confirmar", json={"codigo": _codigo_actual(r.json()["secreto"])}, headers=cab)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(self.client.get("/perfil", headers=cab).status_code, 200)
        # El analista no está sujeto a la política
        datos = self._login("analista1")
        self.assertFalse(datos["mfa_enrolamiento_pendiente"])
        self.assertEqual(self.client.get("/perfil", headers=self._auth(datos["access_token"])).status_code, 200)

    def test_restablecer_por_api(self):
        self._enrolar("oficial1")
        secreto_admin, codigos_admin = self._enrolar("admin1")
        db = self.Session()
        id_admin = self._usuario(db, "admin1").id
        id_oficial = self._usuario(db, "oficial1").id
        db.close()
        token_mfa = self._login("admin1")["mfa_token"]
        r = self.client.post("/auth/mfa/verificar",
                             json={"mfa_token": token_mfa, "codigo": _codigo_actual(secreto_admin, 1)})
        self.assertEqual(r.status_code, 200, r.text)
        cab = self._auth(r.json()["access_token"])
        # Admin: no puede restablecer el propio sin código; sí el de otro usuario
        self.assertEqual(self.client.post(f"/auth/mfa/restablecer/{id_admin}", headers=cab).status_code, 400)
        self.assertEqual(self.client.post("/auth/mfa/restablecer/9999", headers=cab).status_code, 404)
        self.assertEqual(self.client.post(f"/auth/mfa/restablecer/{id_oficial}", headers=cab).status_code, 204)
        self.assertTrue(self._login("oficial1")["is_active"])
        # Analista no puede restablecer a nadie
        cab_analista = self._auth(self._login("analista1")["access_token"])
        self.assertEqual(self.client.post(f"/auth/mfa/restablecer/{id_admin}", headers=cab_analista).status_code, 403)
        # Propio con código (el TOTP vigente ya se usó en el login: se usa uno de recuperación)
        r = self.client.post("/auth/mfa/restablecer", json={"codigo": "000000"}, headers=cab)
        self.assertEqual(r.status_code, 400)
        r = self.client.post("/auth/mfa/restablecer", json={"codigo": codigos_admin[0]}, headers=cab)
        self.assertEqual(r.status_code, 204)
        self.assertTrue(self._login("admin1")["is_active"])
        self.assertIn(f"{auditoria.MFA_RESTABLECIDO}:usuario=oficial1", self._acciones("admin1"))

if __name__ == "__main__":
    unittest.main()
