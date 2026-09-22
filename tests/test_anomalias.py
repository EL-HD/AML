"""Pruebas de la señal de anomalía (T8): backend/anomalias.py y su integración."""
import unittest

import numpy as np
import pandas as pd

import tests.conftest  # noqa: F401
from backend import anomalias
from backend.config_aml import config_por_defecto, validar_config
from backend.procesador import procesar_transacciones

ANOMALOS = [f"ANOM{i}" for i in range(15)]


def _lote_sintetico(n_normales=1500, n_clientes=300, semilla=7):
    """Lote con clientes normales y 15 clientes con fraccionamiento nocturno en efectivo."""
    rng = np.random.default_rng(semilla)
    cli = rng.integers(0, n_clientes, n_normales)
    perfil = rng.choice([3000, 5000, 8000, 12000], n_clientes)
    monto = np.round(np.abs(rng.normal(perfil[cli] * 0.6, perfil[cli] * 0.2)), 2)
    fecha = (pd.Timestamp("2026-01-01") + pd.to_timedelta(rng.integers(0, 90, n_normales), unit="D")
             + pd.to_timedelta(rng.integers(8, 18, n_normales), unit="h"))
    df = pd.DataFrame({
        "Cliente": [f"C{i}" for i in cli], "Monto": monto, "Perfil": perfil[cli], "Fecha": fecha,
        "TipoOperacion": rng.choice(["Transferencia", "Cheque", "Depósito en banco", "Efectivo"], n_normales),
        "Cliente_Destino": [f"C{i}" for i in rng.integers(0, n_clientes, n_normales)],
        "UbicacionRiesgo": rng.choice(["No", "No", "No", "Si"], n_normales),
    })
    filas = []
    for c in ANOMALOS:
        for k in range(10):
            filas.append({"Cliente": c, "Monto": float(rng.choice([9500, 9800, 9900])), "Perfil": 5000,
                          "Fecha": pd.Timestamp("2026-02-02 23:00") + pd.Timedelta(minutes=k),
                          "TipoOperacion": "Efectivo", "Cliente_Destino": f"X{k}", "UbicacionRiesgo": "Si"})
    return pd.concat([df, pd.DataFrame(filas)], ignore_index=True)


class TestBosqueAislamiento(unittest.TestCase):
    def test_reproducible_con_semilla_y_distinto_sin_ella(self):
        rng = np.random.default_rng(0)
        X = rng.normal(size=(300, 4))
        X[:5] += 8.0
        s1 = anomalias.BosqueAislamiento(50, 128, semilla=1).fit(X).puntuar(X)
        s2 = anomalias.BosqueAislamiento(50, 128, semilla=1).fit(X).puntuar(X)
        s3 = anomalias.BosqueAislamiento(50, 128, semilla=2).fit(X).puntuar(X)
        np.testing.assert_array_equal(s1, s2)
        self.assertFalse(np.array_equal(s1, s3))

    def test_puntaje_en_rango_y_atipicos_arriba(self):
        rng = np.random.default_rng(3)
        X = rng.normal(size=(500, 3))
        X[:10] += 10.0
        s = anomalias.BosqueAislamiento(100, 256, semilla=42).fit(X).puntuar(X)
        self.assertTrue(((s >= 0) & (s <= 1)).all())
        top = set(np.argsort(-s)[:10])
        self.assertGreaterEqual(len(top & set(range(10))), 9)

    def test_columnas_constantes_no_rompen(self):
        X = np.ones((50, 3))
        s = anomalias.BosqueAislamiento(20, 32, semilla=0).fit(X).puntuar(X)
        self.assertEqual(len(s), 50)
        self.assertTrue(np.isfinite(s).all())


class TestParametros(unittest.TestCase):
    def test_desde_config_y_hash_estable(self):
        cfg = config_por_defecto()
        p1 = anomalias.ParametrosAnomalia.desde_config(cfg)
        p2 = anomalias.ParametrosAnomalia.desde_config(dict(cfg))
        self.assertEqual(p1.hash(), p2.hash())
        self.assertNotEqual(p1.hash(), anomalias.ParametrosAnomalia.desde_config({**cfg, "anomalia_semilla": 7}).hash())

    def test_validacion_percentiles(self):
        with self.assertRaises(anomalias.ErrorAnomalias):
            anomalias.ParametrosAnomalia(percentil_alto=70, percentil_medio=80).validar()

    def test_config_aml_acepta_y_valida_claves_nuevas(self):
        cfg = validar_config({"anomalia_percentil_alto": 95, "anomalia_percentil_medio": 80})
        self.assertEqual(cfg["anomalia_percentil_alto"], 95)
        self.assertTrue(cfg["anomalia_activa"])
        with self.assertRaises(ValueError):
            validar_config({"anomalia_percentil_alto": 70, "anomalia_percentil_medio": 80})
        with self.assertRaises(ValueError):
            validar_config({"anomalia_n_arboles": 5})


class TestCalculoAnomalias(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = config_por_defecto()
        cls.df = _lote_sintetico()

    def test_detecta_anomalias_inyectadas_en_top_k(self):
        r = anomalias.calcular_anomalias(self.df, self.cfg)
        self.assertEqual(r.metadata["metodo_clientes"], anomalias.METODO_ENSAMBLE)
        top = r.clientes.head(len(ANOMALOS))["Cliente"].tolist()
        precision = len(set(top) & set(ANOMALOS)) / len(ANOMALOS)
        self.assertGreaterEqual(precision, 0.8, f"precisión en el top-{len(ANOMALOS)}: {precision}")
        niveles = r.clientes.set_index("Cliente").loc[ANOMALOS, "Anomalia_Nivel"]
        self.assertGreaterEqual((niveles == anomalias.NIVEL_ALTO).mean(), 0.8)

    def test_reproducible(self):
        r1 = anomalias.calcular_anomalias(self.df, self.cfg)
        r2 = anomalias.calcular_anomalias(self.df, self.cfg)
        pd.testing.assert_frame_equal(r1.clientes.drop(columns=["Anomalia_Variables"]),
                                      r2.clientes.drop(columns=["Anomalia_Variables"]))
        pd.testing.assert_frame_equal(r1.transacciones, r2.transacciones)
        self.assertEqual(r1.metadata["hash_parametros"], r2.metadata["hash_parametros"])

    def test_explicabilidad_coherente(self):
        r = anomalias.calcular_anomalias(self.df, self.cfg)
        fila = r.clientes[r.clientes["Cliente"] == ANOMALOS[0]].iloc[0]
        variables = fila["Anomalia_Variables"]
        self.assertEqual(len(variables), 3)
        zs = [abs(v["z"]) for v in variables]
        self.assertEqual(zs, sorted(zs, reverse=True))
        for v in variables:
            esperado = "por encima" if v["valor"] > v["referencia"] else "por debajo"
            self.assertEqual(v["direccion"], esperado)
            self.assertIn(v["etiqueta"], v["texto"])
            self.assertIn(v["variable"], r.variables_cliente.columns)
            self.assertAlmostEqual(v["valor"], float(r.variables_cliente.loc[ANOMALOS[0], v["variable"]]), places=6)
        nombres = {v["variable"] for v in variables}
        self.assertTrue(nombres & {"tx_dia_max", "prop_cerca_umbral", "prop_hora_atipica", "transacciones",
                                    "ratio_total_perfil", "desv_perfil_max", "prop_efectivo", "prop_ubicacion_riesgo"})
        self.assertIn(fila["Anomalia_Explicacion"], " ".join(v["texto"] for v in variables))

    def test_percentiles_y_niveles(self):
        r = anomalias.calcular_anomalias(self.df, self.cfg)
        p = r.clientes["Anomalia_Percentil"]
        self.assertTrue(((p >= 0) & (p <= 100)).all())
        self.assertAlmostEqual(float(p.max()), 100.0)
        self.assertTrue(set(r.clientes["Anomalia_Nivel"]) <= {"Alto", "Medio", "Bajo"})
        alto = r.clientes[r.clientes["Anomalia_Nivel"] == "Alto"]["Anomalia_Percentil"]
        self.assertTrue((alto >= 90).all())

    def test_no_altera_score_imperator_ni_df(self):
        df_raw = self.df.copy()
        df_p, casos, _m, _i = procesar_transacciones(df_raw.copy(), dict(self.cfg))
        score_antes = casos["Score_Max"].copy()
        nivel_antes = casos["Nivel_Riesgo"].copy()
        df_antes = df_p.copy()
        r = anomalias.calcular_anomalias(df_p, self.cfg)
        anomalias.marcar_casos(casos, r)
        pd.testing.assert_series_equal(casos["Score_Max"], score_antes)
        pd.testing.assert_series_equal(casos["Nivel_Riesgo"], nivel_antes)
        pd.testing.assert_frame_equal(df_p, df_antes)
        self.assertIn("Anomalia_Percentil", casos.columns)
        self.assertIn("Anomalia_Nivel", casos.columns)
        self.assertTrue(casos["Anomalia_Percentil"].notna().all())
        # Reprocesar con el motor produce el mismo score: la señal es independiente
        _d2, casos2, _m2, _i2 = procesar_transacciones(df_raw.copy(), dict(self.cfg))
        pd.testing.assert_series_equal(casos2["Score_Max"], score_antes)

    def test_puntos_ciegos(self):
        df_p, casos, _m, _i = procesar_transacciones(self.df.copy(), dict(self.cfg))
        r = anomalias.calcular_anomalias(df_p, self.cfg)
        anomalias.marcar_casos(casos, r)
        ciegos = anomalias.puntos_ciegos(casos, anomalias.ParametrosAnomalia(score_punto_ciego=3.0))
        self.assertTrue((ciegos["Anomalia_Nivel"] == "Alto").all())
        self.assertTrue((ciegos["Score_Max"] < 3.0).all())
        self.assertTrue(anomalias.puntos_ciegos(pd.DataFrame(columns=["Cliente"])).empty)

    def test_pocos_datos_usa_mad_y_no_falla(self):
        df = self.df[self.df["Cliente"].isin([f"C{i}" for i in range(5)] + ANOMALOS[:1])]
        r = anomalias.calcular_anomalias(df, self.cfg)
        self.assertEqual(r.metadata["metodo_clientes"], anomalias.METODO_MAD)
        self.assertEqual(r.metadata["n_clientes"], df["Cliente"].nunique())
        self.assertEqual(r.clientes.iloc[0]["Cliente"], ANOMALOS[0])
        una = anomalias.calcular_anomalias(self.df.head(1), self.cfg)
        self.assertEqual(len(una.clientes), 1)
        self.assertEqual(float(una.clientes["Anomalia_Percentil"].iloc[0]), 100.0)

    def test_columnas_faltantes_y_nulos(self):
        df = self.df.drop(columns=["Fecha", "Cliente_Destino", "UbicacionRiesgo", "TipoOperacion", "Perfil"]).copy()
        df["Monto"] = df["Monto"].astype(object)
        df.loc[df.index[:20], "Monto"] = None
        df.loc[df.index[20:25], "Monto"] = "texto"
        r = anomalias.calcular_anomalias(df, self.cfg)
        self.assertFalse(r.vacio)
        self.assertTrue(np.isfinite(r.clientes["Anomalia_Score"]).all())
        self.assertNotIn("dias_activos", r.metadata["variables_cliente"])
        self.assertNotIn("contrapartes_unicas", r.metadata["variables_cliente"])
        sin = anomalias.calcular_anomalias(self.df.drop(columns=["Monto"]), self.cfg)
        self.assertTrue(sin.vacio)
        self.assertIn("Monto", sin.metadata["motivo"])
        vacio = anomalias.calcular_anomalias(self.df.iloc[0:0], self.cfg)
        self.assertTrue(vacio.vacio)

    def test_desactivada_por_configuracion(self):
        r = anomalias.calcular_anomalias(self.df, {**self.cfg, "anomalia_activa": False})
        self.assertTrue(r.vacio)
        casos = pd.DataFrame({"Cliente": ["A"], "Score_Max": [1.0]})
        self.assertEqual(anomalias.marcar_casos(casos, r), 0)
        self.assertEqual(casos["Anomalia_Nivel"].iloc[0], "N/D")

    def test_metadata_trazabilidad(self):
        r = anomalias.calcular_anomalias(self.df, self.cfg, hash_lote="a" * 64)
        self.assertEqual(r.metadata["version_modelo"], anomalias.VERSION_MODELO)
        self.assertEqual(r.metadata["hash_lote"], "a" * 64)
        linea = anomalias.resumen_trazabilidad(r.metadata)
        self.assertIn(anomalias.VERSION_MODELO, linea)
        self.assertIn("semilla: 42", linea)
        self.assertIn(r.metadata["hash_parametros"], linea)

    def test_variables_transaccion_cerca_umbral_y_redondos(self):
        df = pd.DataFrame({"Cliente": ["A", "A", "B", "B"], "Monto": [9500, 12000, 100, 25000], "Perfil": [5000] * 4,
                           "Fecha": pd.to_datetime(["2026-01-03 22:00", "2026-01-05 10:00", "2026-01-06 00:00", "2026-01-07 00:00"])})
        tx = anomalias.variables_transaccion(df, self.cfg)
        self.assertEqual(tx["cerca_umbral"].tolist(), [1.0, 0.0, 0.0, 0.0])
        self.assertEqual(tx["monto_redondo"].tolist(), [0.0, 1.0, 0.0, 1.0])
        self.assertEqual(tx["fin_semana"].tolist(), [1.0, 0.0, 0.0, 0.0])
        self.assertEqual(tx["hora_atipica"].tolist(), [1.0, 0.0, 0.0, 0.0])

    def test_lote_real_de_ejemplo(self):
        df = pd.read_excel("Transacciones_AML_200.xlsx")
        df_p, casos, _m, _i = procesar_transacciones(df, dict(self.cfg))
        r = anomalias.calcular_anomalias(df_p, self.cfg)
        self.assertEqual(r.metadata["n_clientes"], casos["Cliente"].nunique())
        self.assertLess(r.metadata["duracion_s"], 5.0)
        self.assertEqual(anomalias.marcar_casos(casos, r), len(casos))


if __name__ == "__main__":
    unittest.main()
