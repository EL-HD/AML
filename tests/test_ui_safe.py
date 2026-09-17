"""
Pruebas de frontend/ui_safe (S-06) y verificación estática de que ningún
bloque unsafe_allow_html=True interpola valores sin escapar.
"""
import ast
import re
import unittest
from pathlib import Path

import tests.conftest  # noqa: F401
from frontend.ui_safe import attr_css_color, h, html_block

RAIZ = Path(__file__).resolve().parent.parent
# rglob (recursivo): glob("*.py") dejaba fuera frontend/theme/*.py sin que
# ninguna prueba lo notara (bug de cobertura encontrado en la auditoría S-06).
ARCHIVOS = [RAIZ / "app.py"] + sorted((RAIZ / "frontend").rglob("*.py"))

# Heurística documentada: todo f-string que contenga etiquetas HTML (texto con
# "<letra" o "</") debe interpolar sus valores mediante una llamada segura
# (h, html_block, attr_css_color, escape o componentes propios) o mediante un
# nombre *_html (HTML ya construido de forma segura). Se exceptúan los bloques
# <script> de app.py, cuyos valores son constantes internas validadas
# (token firmado con alfabeto base64url y cache_id con forma de UUID).
PREFIJOS_SEGUROS = ("h(", "html_block(", "attr_css_color(", "escape(", "_badge_nivel(", "_texto_seguro(")
PATRON_HTML = re.compile(r"<[a-zA-Z/]")


def _fstrings_peligrosas(ruta: Path):
    arbol = ast.parse(ruta.read_text(encoding="utf-8"))
    hallazgos = []
    for nodo in ast.walk(arbol):
        if not isinstance(nodo, ast.JoinedStr):
            continue
        texto = "".join(v.value for v in nodo.values if isinstance(v, ast.Constant))
        if not PATRON_HTML.search(texto) or texto.lstrip().startswith("<script>"):
            continue
        for valor in nodo.values:
            if not isinstance(valor, ast.FormattedValue):
                continue
            expr = ast.unparse(valor.value).strip()
            if expr.startswith(PREFIJOS_SEGUROS) or expr.endswith("_html"):
                continue
            hallazgos.append(f"{ruta.name}:{nodo.lineno}: {expr}")
    return hallazgos


class TestUiSafe(unittest.TestCase):
    def test_h_escapa_script_y_atributos(self):
        self.assertEqual(h("<script>alert(1)</script>"), "&lt;script&gt;alert(1)&lt;/script&gt;")
        self.assertEqual(h('" onmouseover="x'), "&quot; onmouseover=&quot;x")
        self.assertEqual(h(None), "")
        self.assertEqual(h(1234), "1234")

    def test_html_block_escapa_todo_salvo_sufijo_html(self):
        salida = html_block("<b>{nombre}</b>{cuerpo_html}", nombre="<i>x</i>", cuerpo_html="<u>ok</u>")
        self.assertEqual(salida, "<b>&lt;i&gt;x&lt;/i&gt;</b><u>ok</u>")

    def test_attr_css_color(self):
        self.assertEqual(attr_css_color("#f59e0b"), "#f59e0b")
        self.assertEqual(attr_css_color("red"), "red")
        self.assertEqual(attr_css_color("red;background:url(x)"), "#8b949e")

    def test_nombre_de_cliente_con_script_sale_escapado(self):
        from frontend.mod_utils import render_html_table
        import pandas as pd
        tabla = render_html_table(pd.DataFrame({"Cliente": ["<script>alert(1)</script>"]}))
        self.assertNotIn("<script>alert(1)</script>", tabla)
        self.assertIn("&lt;script&gt;", tabla)

    def test_kpi_card_escapa_valores_maliciosos(self):
        from frontend.ui_components import kpi_card
        salida = kpi_card("<b>label</b>", "<script>alert(1)</script>", sub="<img src=x onerror=alert(2)>")
        self.assertNotIn("<script>alert(1)</script>", salida)
        self.assertNotIn("<img src=x onerror=alert(2)>", salida)
        self.assertIn("&lt;script&gt;", salida)
        self.assertIn("&lt;img", salida)

    def test_no_hay_fstrings_html_sin_escapar(self):
        hallazgos = []
        for ruta in ARCHIVOS:
            hallazgos += _fstrings_peligrosas(ruta)
        self.assertEqual(hallazgos, [], "Valores sin h() en bloques HTML:\n" + "\n".join(hallazgos))


if __name__ == "__main__":
    unittest.main()
