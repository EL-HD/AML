"""Prueba de regresión: las migraciones SQL se envían sin sustitución de parámetros.

Contexto del fallo que motiva esta prueba (CI de 2026-09-17, job "Migraciones
idempotentes (PostgreSQL 16)"): scripts/db_migrate.py aplicaba cada archivo con
SQLAlchemy.exec_driver_sql(sql), que entrega a psycopg2 un diccionario vacío
como parámetros. Al encontrar "%" en el SQL, psycopg2 intenta interpolar y
aborta con:

    TypeError: sqlalchemy.cyextension.immutabledict.immutabledict
               is not a sequence

Las migraciones 004, 005 y 006 usan "%" como marcador de PL/pgSQL en
RAISE EXCEPTION, por lo que el fallo era determinista a partir de la primera de
ellas. La corrección ejecuta el SQL por el cursor DBAPI con un único argumento.

Estas pruebas no requieren PostgreSQL: verifican el contrato de la llamada
mediante dobles de prueba, que es justamente lo que el error rompía.
"""
import unittest
from pathlib import Path

import tests.conftest  # noqa: F401  (fija variables de entorno y DATABASE_URL de prueba)

from scripts.db_migrate import ejecutar_sql_literal

RAIZ = Path(__file__).resolve().parent.parent
MIGRACIONES = RAIZ / "migrations"


class CursorEspia:
    def __init__(self):
        self.llamadas = []
        self.cerrado = False

    def execute(self, *args, **kwargs):
        self.llamadas.append((args, kwargs))

    def close(self):
        self.cerrado = True


class CursorQueFalla(CursorEspia):
    def execute(self, *args, **kwargs):
        super().execute(*args, **kwargs)
        raise RuntimeError("fallo simulado del motor")


class ConexionEspia:
    """Doble de sqlalchemy.Connection: expone .connection.cursor()."""

    def __init__(self, cursor):
        self._cursor = cursor
        self.connection = self

    def cursor(self):
        return self._cursor


class TestEjecutarSqlLiteral(unittest.TestCase):
    def test_execute_recibe_un_solo_argumento(self):
        """Sin parámetros no hay interpolación: ni "%" ni ":x" se reinterpretan."""
        cursor = CursorEspia()
        sql = "RAISE EXCEPTION 'Operación % no permitida en %', a, b; -- :M"

        ejecutar_sql_literal(ConexionEspia(cursor), sql)

        self.assertEqual(len(cursor.llamadas), 1)
        args, kwargs = cursor.llamadas[0]
        self.assertEqual(args, (sql,))
        self.assertEqual(kwargs, {})

    def test_cursor_se_cierra_siempre(self):
        cursor = CursorQueFalla()

        with self.assertRaises(RuntimeError):
            ejecutar_sql_literal(ConexionEspia(cursor), "SELECT 1")

        self.assertTrue(cursor.cerrado, "el cursor debe cerrarse aunque execute falle")

    def test_sql_vacio_o_invalido_se_rechaza(self):
        for entrada in ("", "   ", None, 123):
            with self.subTest(entrada=entrada):
                cursor = CursorEspia()
                with self.assertRaises(ValueError):
                    ejecutar_sql_literal(ConexionEspia(cursor), entrada)
                self.assertEqual(cursor.llamadas, [])


class TestMigracionesConMarcadorPorcentaje(unittest.TestCase):
    def test_hay_migraciones_con_porcentaje(self):
        """Documenta el motivo del fix: si algún día no quedara ninguna, esta
        prueba avisa de que la regresión ya no estaría cubierta por datos reales."""
        con_porcentaje = [
            f.name for f in sorted(MIGRACIONES.glob("*.sql"))
            if "%" in f.read_text(encoding="utf-8")
        ]
        self.assertTrue(
            con_porcentaje,
            "ninguna migración contiene '%': revisar si esta prueba sigue siendo pertinente",
        )


if __name__ == "__main__":
    unittest.main()
