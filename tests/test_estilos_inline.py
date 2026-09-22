"""
T9 Pendientes UI: estilos inline y moneda configurable.

1. Los atributos style= en bloques HTML del frontend quedan acotados (solo
   valores numéricos dinámicos: altura máxima de tabla y tamaño de KPI).
2. Toda clase CSS usada en HTML del código existe en styles.css o login.css.
3. tone_class solo emite clases definidas en el tema (nunca el color crudo).
4. La moneda de trabajo se aplica a etiquetas y formatos, mientras el umbral
   RTE del Art. 31 se mantiene como monto normativo en USD.
"""
import re
import unittest
from pathlib import Path

import tests.conftest  # noqa: F401

RAIZ = Path(__file__).resolve().parent.parent
ARCHIVOS_UI = [RAIZ / "app.py"] + sorted((RAIZ / "frontend").glob("*.py"))
CSS = (RAIZ / "frontend/theme/styles.css").read_text(encoding="utf-8") + \
      (RAIZ / "frontend/theme/login.css").read_text(encoding="utf-8")
CLASES_DEFINIDAS = set(re.findall(r"\.([a-zA-Z][\w-]*)", CSS))
# Ganchos semánticos sin regla propia (se usan como selector compuesto o futuro).
GANCHOS_SIN_REGLA = {"sidebar-license"}
PATRON_STYLE = re.compile(r"""[ ]style=["']""")
PATRON_CLASS = re.compile(r"""class=\\?["']([^"']*)\\?["']""")
# Antes de T9 había 156 atributos style= en HTML; el objetivo era reducirlos al
# menos a la mitad. Quedan solo los de valor numérico dinámico.
MAXIMO_STYLE_INLINE = 10


class TestEstilosInline(unittest.TestCase):
    def test_style_inline_acotado(self):
        total = 0
        detalle = []
        for ruta in ARCHIVOS_UI:
            for numero, linea in enumerate(ruta.read_text(encoding="utf-8").splitlines(), 1):
                if PATRON_STYLE.search(linea):
                    total += 1
                    detalle.append(f"{ruta.name}:{numero}")
        self.assertLessEqual(total, MAXIMO_STYLE_INLINE, "style= inline en:\n" + "\n".join(detalle))

    def test_clases_html_existen_en_el_tema(self):
        faltantes = {}
        for ruta in ARCHIVOS_UI:
            for coincidencia in PATRON_CLASS.finditer(ruta.read_text(encoding="utf-8")):
                for clase in coincidencia.group(1).split():
                    if "{" in clase or "}" in clase:
                        continue  # clase dinámica (tone_class), cubierta abajo
                    if clase not in CLASES_DEFINIDAS and clase not in GANCHOS_SIN_REGLA:
                        faltantes.setdefault(clase, set()).add(ruta.name)
        self.assertEqual(faltantes, {}, f"Clases usadas sin definir en el tema: {faltantes}")

    def test_tone_class_solo_emite_clases_del_tema(self):
        from frontend import ui_components
        from frontend.theme.tokens import COLORES, COLOR_NIVEL
        for color in list(COLORES.values()) + list(COLOR_NIVEL.values()) + ["#zzzzzz", None, "red;x"]:
            clase = ui_components.tone_class(color)
            self.assertTrue(clase.startswith("tone-"), clase)
            self.assertIn(clase, CLASES_DEFINIDAS, clase)
        self.assertEqual(ui_components.tone_class("#ef4444"), "tone-danger")
        self.assertEqual(ui_components.tone_class("#EF4444"), "tone-danger")
        self.assertEqual(ui_components.tone_class("#zzzzzz"), "tone-muted")
        self.assertEqual(ui_components.tone_nivel("Crítico"), "tone-danger")
        self.assertEqual(ui_components.tone_nivel("Bajo"), "tone-ok")

    def test_nivel_badge_sin_style_inline(self):
        from frontend.ui_components import nivel_badge
        salida = nivel_badge("Alto")
        self.assertNotIn("style=", salida)
        self.assertIn("badge-tone", salida)
        self.assertIn("tone-warn", salida)

    def test_tonos_definen_variable_css(self):
        for tono in ("danger", "warn", "yellow", "ok", "green", "info", "violet", "accent", "muted", "strong"):
            self.assertRegex(CSS, rf"\.tone-{tono}\s*\{{[^}}]*--sv-tone:", tono)


class TestMonedaConfigurable(unittest.TestCase):
    def _con_moneda(self, moneda):
        import streamlit as st
        st.session_state["aml_config"] = {"moneda": moneda}

    def tearDown(self):
        import streamlit as st
        st.session_state.pop("aml_config", None)

    def test_formato_y_etiquetas_siguen_la_moneda(self):
        from frontend import ui_components
        self._con_moneda("GTQ")
        self.assertEqual(ui_components.fmt_moneda(12345.678, 2), "Q12,345.68")
        self.assertEqual(ui_components.etiqueta_monto("Monto total"), "Monto total (Q)")
        self.assertEqual(ui_components.nombre_moneda(), "GTQ (Quetzales)")
        self._con_moneda("USD")
        self.assertEqual(ui_components.fmt_moneda(12345.678, 2), "US$12,345.68")
        self.assertEqual(ui_components.etiqueta_monto("Monto total"), "Monto total (US$)")
        self.assertEqual(ui_components.nombre_moneda(), "USD (Dólares)")
        self._con_moneda("XXX")  # valor no permitido: se cae a GTQ
        self.assertEqual(ui_components.simbolo_moneda(), "Q")

    def test_umbral_rte_es_normativo_en_usd(self):
        from frontend import ui_components
        self.assertEqual(ui_components.UMBRAL_RTE_USD, 10_000)
        for moneda in ("GTQ", "USD"):
            self._con_moneda(moneda)
            texto = ui_components.texto_moneda_normativa()
            self.assertIn("USD 10,000", texto)
            self.assertIn(ui_components.nombre_moneda(), texto)
            self.assertIn("normativo", texto)

    def test_anomalias_usa_simbolo_coherente(self):
        from backend import anomalias
        self.assertEqual(anomalias.formatear_valor(1500, "moneda", "US$"), "US$1,500")
        self.assertEqual(anomalias.formatear_valor(1500, "moneda", "Q"), "Q1,500")

    def test_sin_moneda_fija_en_ejes_y_pdf(self):
        """No quedan etiquetas '(Q)' ni 'Q{' fijas fuera de ui_components."""
        patron = re.compile(r"""\(Q\)|Q\{|Q%\{|"Q"|'Q'""")
        hallazgos = []
        for ruta in ARCHIVOS_UI:
            if ruta.name == "ui_components.py":
                continue
            for numero, linea in enumerate(ruta.read_text(encoding="utf-8").splitlines(), 1):
                if patron.search(linea):
                    hallazgos.append(f"{ruta.name}:{numero}: {linea.strip()[:100]}")
        self.assertEqual(hallazgos, [], "\n".join(hallazgos))


if __name__ == "__main__":
    unittest.main()
