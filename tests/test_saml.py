"""Pruebas de importación/exportación .saml con límites y lista blanca de configuración (S-08)."""
import io
import json
import unittest
import zipfile

import pandas as pd

import tests.conftest  # noqa: F401
from backend.config_aml import config_por_defecto, validar_config
from frontend import mod_sesion


def _df():
    return pd.DataFrame({
        "Fecha": ["2026-01-01"], "Cliente": ["C1"], "EsPEP": ["NO"], "EsCPE": ["NO"],
        "Monto": [100.0], "Perfil": [1000.0], "Ubicacion": ["Guatemala"],
        "UbicacionRiesgo": ["NO"], "TipoOperacion": ["Deposito"], "Cliente_Destino": ["C2"],
    })


def _saml(cfg=None, meta=None, csv=None):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("transactions.csv", csv if csv is not None else _df().to_csv(index=False))
        zf.writestr("config.json", json.dumps(cfg if cfg is not None else config_por_defecto()))
        zf.writestr("session.json", json.dumps(meta if meta is not None else {"nombre_archivo": "x.xlsx"}))
    buf.seek(0)
    return buf


class TestConfig(unittest.TestCase):
    def test_defaults_validos(self):
        self.assertEqual(validar_config({}), config_por_defecto())

    def test_clave_desconocida_rechazada(self):
        with self.assertRaises(ValueError):
            validar_config({"__class__": "x"})
        with self.assertRaises(ValueError):
            validar_config({"clave_nueva": 1})

    def test_rango_y_tipo(self):
        with self.assertRaises(ValueError):
            validar_config({"umbral_absoluto": -5})
        with self.assertRaises(ValueError):
            validar_config({"score_critico": "abc"})
        with self.assertRaises(ValueError):
            validar_config({"ubicaciones_manuales": ["x" * 500]})
        self.assertEqual(validar_config({"umbral_absoluto": "25000"})["umbral_absoluto"], 25000)


class TestSaml(unittest.TestCase):
    def test_ida_y_vuelta(self):
        datos = mod_sesion.exportar_sesion(_df(), config_por_defecto(), "archivo.xlsx")
        df, cfg, meta = mod_sesion.importar_sesion(io.BytesIO(datos))
        self.assertEqual(len(df), 1)
        self.assertEqual(cfg, config_por_defecto())
        self.assertEqual(meta["nombre_archivo"], "archivo.xlsx")
        self.assertEqual(meta["filas"], 1)

    def test_config_con_clave_extra_rechazada(self):
        cfg = config_por_defecto()
        cfg["inyectada"] = True
        with self.assertRaises(ValueError):
            mod_sesion.importar_sesion(_saml(cfg=cfg))

    def test_config_fuera_de_rango_rechazada(self):
        cfg = config_por_defecto()
        cfg["score_critico"] = 999
        with self.assertRaises(ValueError):
            mod_sesion.importar_sesion(_saml(cfg=cfg))

    def test_zip_corrupto(self):
        with self.assertRaises(ValueError):
            mod_sesion.importar_sesion(io.BytesIO(b"no es zip"))

    def test_archivo_demasiado_grande(self):
        grande = io.BytesIO(b"0" * (mod_sesion.MAX_BYTES_COMPRIMIDO + 1))
        with self.assertRaises(ValueError):
            mod_sesion.importar_sesion(grande)

    def test_tasa_de_compresion_sospechosa(self):
        csv = "Fecha,Cliente\n" + ("A,B\n" * 2_000_000)
        with self.assertRaises(ValueError):
            mod_sesion.importar_sesion(_saml(csv=csv))

    def test_exceso_de_filas(self):
        antiguo = mod_sesion.MAX_FILAS
        mod_sesion.MAX_FILAS = 5
        try:
            df = pd.concat([_df()] * 10, ignore_index=True)
            with self.assertRaises(ValueError):
                mod_sesion.importar_sesion(_saml(csv=df.to_csv(index=False)))
        finally:
            mod_sesion.MAX_FILAS = antiguo

    def test_meta_saneada(self):
        meta = {"nombre_archivo": "n" * 500, "otro": {"x": 1}, "filas": "999"}
        _, _, meta_out = mod_sesion.importar_sesion(_saml(meta=meta))
        self.assertEqual(len(meta_out["nombre_archivo"]), 200)
        self.assertNotIn("otro", meta_out)
        self.assertEqual(meta_out["filas"], 1)


if __name__ == "__main__":
    unittest.main()
