"""
Verificación de contraste WCAG 2.1 AA (ratio >= 4.5:1) entre los tokens de texto
y las superficies del tema (U-04). Se ejecuta como prueba para que un cambio de
paleta que rompa la accesibilidad falle en CI.
"""
import unittest

import tests.conftest  # noqa: F401
from frontend.theme.tokens import COLORES

SUPERFICIES = ("fondo", "superficie", "superficie_alta", "superficie_form")
TEXTOS = (
    "texto", "texto_fuerte", "texto_secundario", "texto_terciario", "texto_tenue",
    "acento", "acento_claro", "info_claro", "exito_texto", "peligro_suave", "amarillo",
    "advertencia_suave", "violeta",
)
MINIMO_AA = 4.5


def _lineal(canal: int) -> float:
    c = canal / 255
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def luminancia(hex_color: str) -> float:
    valor = hex_color.lstrip("#")
    r, g, b = (int(valor[i:i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * _lineal(r) + 0.7152 * _lineal(g) + 0.0722 * _lineal(b)


def ratio_contraste(primero: str, segundo: str) -> float:
    l1, l2 = sorted((luminancia(primero), luminancia(segundo)), reverse=True)
    return (l1 + 0.05) / (l2 + 0.05)


class TestContraste(unittest.TestCase):
    def test_texto_sobre_superficies_cumple_aa(self):
        fallos = []
        for texto in TEXTOS:
            for superficie in SUPERFICIES:
                ratio = ratio_contraste(COLORES[texto], COLORES[superficie])
                if ratio < MINIMO_AA:
                    fallos.append(f"{texto} sobre {superficie}: {ratio:.2f}")
        self.assertEqual(fallos, [], "Pares con contraste insuficiente:\n" + "\n".join(fallos))

    def test_ratio_conocido(self):
        self.assertAlmostEqual(ratio_contraste("#ffffff", "#000000"), 21.0, places=1)


if __name__ == "__main__":
    unittest.main()
