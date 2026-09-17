"""Pruebas de la política de contraseñas (S-11)."""
import unittest

import tests.conftest  # noqa: F401
from pydantic import ValidationError

from backend import schemas
from backend.politica_password import validar_password


class TestPolitica(unittest.TestCase):
    def test_valida(self):
        validar_password("Cumplimiento#2026!", "oficial1")

    def test_rechazos(self):
        casos = {
            "Corta#1a": "12 caracteres",
            "todominusculas#123": "mayúscula",
            "TODOMAYUSCULAS#123": "minúscula",
            "SinNumeros#Aqui!": "número",
            "SinSimbolos2026Aa": "símbolo",
            "Password2026!": "común",
            "Oficial1-Clave#2026": "usuario",
        }
        for clave, motivo in casos.items():
            with self.assertRaises(ValueError, msg=motivo):
                validar_password(clave, "oficial1")

    def test_schema_licencia_aplica_politica(self):
        base = dict(user="nuevo", name="N", mail="n@ejemplo.com", dias_vigencia=30, empresa="E",
                    fecha_compra="2026-01-01", fecha_expiracion="2026-02-01")
        with self.assertRaises(ValidationError):
            schemas.LicenciaCreate(password="debil", **base)
        schemas.LicenciaCreate(password="Cumplimiento#2026!", **base)


if __name__ == "__main__":
    unittest.main()
