"""Regresión U-05 / login engañoso.

frontend/login.html era un mockup estático (Tailwind CDN) nunca importado ni
servido por el proyecto (Streamlit corre con enableStaticServing=false); el
login real vive en app.py::login_flow(). Contenía "ACCESO RESTRINGIDO - NIVEL
4 CID", "NORMATIVA SOVEREIGN-V3" y un enlace muerto de recuperación de
contraseña que ya se habían retirado del login real pero seguían en el
mockup. Se eliminó el archivo; esta prueba evita que el texto vuelva a
colarse en el login que sí se sirve (app.py).
"""
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
_TEXTOS_ENGANOSOS = ("NIVEL 4 CID", "SOVEREIGN-V3", 'href="#"')


class TestLoginSinResiduos(unittest.TestCase):
    def test_login_html_residual_fue_eliminado(self):
        self.assertFalse(
            (RAIZ / "frontend" / "login.html").exists(),
            "frontend/login.html era un mockup residual (no importado/servido "
            "por nada); debe permanecer eliminado.",
        )

    def test_app_py_no_contiene_textos_enganosos_del_login_viejo(self):
        fuente = (RAIZ / "app.py").read_text(encoding="utf-8")
        encontrados = [t for t in _TEXTOS_ENGANOSOS if t in fuente]
        self.assertEqual(
            encontrados, [],
            f"El login real (app.py) no debe contener: {encontrados}",
        )


if __name__ == "__main__":
    unittest.main()
