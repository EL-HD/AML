"""Pruebas de frontend.permisos (S-04): matriz de autorización por rol.

Cubre la lógica pura (puede/rol_actual/exigir_o_avisar); no depende de un
servidor Streamlit real (los warnings de "missing ScriptRunContext" son
esperados y no afectan el resultado).
"""
import unittest

from frontend import permisos

ROLES_SIN_AUDITOR = {"admin", "oficial", "analista"}


class TestRolActual(unittest.TestCase):
    def test_rol_valido_se_respeta(self):
        self.assertEqual(permisos.rol_actual({"rol": "auditor"}), "auditor")

    def test_rol_ausente_o_invalido_cae_a_analista(self):
        self.assertEqual(permisos.rol_actual({}), "analista")
        self.assertEqual(permisos.rol_actual({"rol": "superadmin"}), "analista")
        self.assertEqual(permisos.rol_actual(None), "analista")


class TestMatrizPermisos(unittest.TestCase):
    def test_administrar_licencias_solo_admin(self):
        for rol in permisos.ROLES:
            esperado = rol == "admin"
            self.assertEqual(
                permisos.puede("administrar_licencias", {"rol": rol}), esperado, rol,
            )

    def test_accion_desconocida_se_niega_a_todos(self):
        for rol in permisos.ROLES:
            self.assertFalse(permisos.puede("accion_inexistente", {"rol": rol}))

    def test_auditor_es_de_solo_lectura_en_acciones_de_escritura(self):
        """El auditor nunca debe poder mutar ni exportar (S-04): solo observa."""
        acciones_de_escritura_o_exportacion = [
            "administrar_licencias", "configurar_parametros", "gestionar_catalogos",
            "gestionar_ubicaciones", "editar_riesgo_ldft", "gestionar_alertas",
            "exportar_datos", "proponer_caso_sospechoso", "aprobar_caso_sospechoso",
        ]
        for accion in acciones_de_escritura_o_exportacion:
            self.assertFalse(
                permisos.puede(accion, {"rol": "auditor"}),
                f"auditor no debería poder '{accion}'",
            )
        # Pero sí puede ver Configuración (lectura).
        self.assertTrue(permisos.puede("ver_configuracion", {"rol": "auditor"}))

    def test_gestionar_alertas_excluye_auditor_incluye_operativos(self):
        """Clasificar un caso (Art. 29-30 Ley 6593) requiere rol operativo."""
        for rol in ROLES_SIN_AUDITOR:
            self.assertTrue(permisos.puede("gestionar_alertas", {"rol": rol}), rol)
        self.assertFalse(permisos.puede("gestionar_alertas", {"rol": "auditor"}))

    def test_aprobar_caso_sospechoso_solo_oficial_o_admin(self):
        """Cuatro ojos (Art. 29-30 Ley 6593): el analista propone, no aprueba."""
        for rol in ROLES_SIN_AUDITOR:
            self.assertTrue(permisos.puede("proponer_caso_sospechoso", {"rol": rol}), rol)
        self.assertTrue(permisos.puede("aprobar_caso_sospechoso", {"rol": "admin"}))
        self.assertTrue(permisos.puede("aprobar_caso_sospechoso", {"rol": "oficial"}))
        self.assertFalse(permisos.puede("aprobar_caso_sospechoso", {"rol": "analista"}))
        self.assertFalse(permisos.puede("aprobar_caso_sospechoso", {"rol": "auditor"}))

    def test_exportar_datos_excluye_auditor_incluye_operativos(self):
        """Generar/descargar PDFs RTS/RTE y reportes exige rol operativo."""
        for rol in ROLES_SIN_AUDITOR:
            self.assertTrue(permisos.puede("exportar_datos", {"rol": rol}), rol)
        self.assertFalse(permisos.puede("exportar_datos", {"rol": "auditor"}))


class TestExigirOAvisar(unittest.TestCase):
    def tearDown(self):
        # Aislamiento: st.session_state es global en modo bare; sin limpiar,
        # el rol "admin" se filtra a TestRolActual (se ejecuta después).
        import streamlit as st
        st.session_state.pop("user_data", None)

    def test_devuelve_el_mismo_resultado_que_puede(self):
        import streamlit as st
        st.session_state["user_data"] = {"rol": "auditor"}
        self.assertFalse(permisos.exigir_o_avisar("exportar_datos"))
        st.session_state["user_data"] = {"rol": "admin"}
        self.assertTrue(permisos.exigir_o_avisar("exportar_datos"))


if __name__ == "__main__":
    unittest.main()
