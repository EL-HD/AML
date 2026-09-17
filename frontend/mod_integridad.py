"""
mod_integridad.py: vista "Integridad de Bitácora" (Administración).

Permite a un Administrador o Auditor verificar la cadena de hashes de
public."BitacoraAuditoria" de su propia licencia (T4 Fase 2): resumen
íntegra/rota, primer eslabón roto con su motivo, detalle por eslabón y
exportación del reporte de verificación (CSV saneado contra fórmulas).

La verificación queda registrada en la propia bitácora
(VERIFICACION_BITACORA:<resultado>) como evidencia de la revisión.
Todo valor dinámico pasa por render_html_table o ui_components (escape OWASP A03).
"""
import logging
from datetime import datetime, timezone

import pandas as pd
import streamlit as st
from sqlalchemy.exc import SQLAlchemyError

from backend import auditoria
from backend.database import SessionLocal
from frontend import casos_persistencia, exportacion, permisos, ui_components
from frontend.mod_utils import render_html_table

logger = logging.getLogger(__name__)

_CLAVE_RESULTADO = "integridad_resultado"
_FILAS_VISIBLES = 200
_COLUMNAS_DETALLE = ["seq", "timestamp", "usuario", "modulo", "accion", "hash_alg", "hash_prev", "hash", "estado", "motivo"]


def mostrar() -> None:
    ui_components.page_header(
        "Integridad de Bitácora",
        "Verificación de la cadena de hashes de la bitácora de auditoría (Art. 19 Ley 6593, GAFI R.11). "
        "Cada registro enlaza con el anterior; cualquier alteración, borrado o inserción fuera de orden rompe la cadena.",
    )
    if not permisos.puede("verificar_bitacora"):
        permisos.aviso_solo_lectura("verificar_bitacora")
        return
    licenciaid, usuario, _rol = casos_persistencia.identidad_sesion()
    if not licenciaid:
        st.error("No se pudo determinar la licencia de la sesión. Vuelva a iniciar sesión.")
        return
    _panel_configuracion()
    if st.button("Verificar cadena ahora", type="primary", key="integridad_verificar"):
        _ejecutar_verificacion(licenciaid, usuario)
    resultado = st.session_state.get(_CLAVE_RESULTADO)
    if resultado is None or resultado.get("licenciaid") != str(licenciaid):
        ui_components.empty_state(
            "Sin verificación en esta sesión",
            "Pulse 'Verificar cadena ahora' para recorrer la bitácora de su licencia y comprobar cada eslabón.",
        )
        return
    _mostrar_resultado(resultado)


def _panel_configuracion() -> None:
    if auditoria.clave_hmac():
        ui_components.info_panel(
            "Los eslabones nuevos se firman con HMAC-SHA256 usando la clave de la aplicación: "
            "quien acceda a la base de datos no puede recalcular la cadena sin ese secreto.",
            "HMAC activo",
        )
    else:
        ui_components.info_panel(
            f"La cadena usa SHA-256 sin clave. Defina {auditoria.VARIABLE_HMAC} en el entorno para que un "
            "atacante con acceso a la base de datos no pueda recalcular la cadena. Los eslabones ya "
            "existentes seguirán verificándose con SHA-256.",
            "HMAC no configurado", tipo="warning",
        )


def _ejecutar_verificacion(licenciaid, usuario: str) -> None:
    db = SessionLocal()
    try:
        resultado = auditoria.verificar_cadena(db, licenciaid)
        veredicto = "INTEGRA" if resultado.integra else f"ROTA:{resultado.primer_seq_roto}"
        # La verificación se registra en la propia bitácora (nuevo eslabón) sin afectar el resultado mostrado.
        auditoria.registrar_evento(db, licenciaid, usuario, auditoria.MODULO_INTEGRIDAD,
                                   f"{auditoria.VERIFICACION_BITACORA}:{veredicto}")
        st.session_state[_CLAVE_RESULTADO] = {
            "licenciaid": str(licenciaid),
            "verificado_en": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
            "verificado_por": usuario,
            "integra": resultado.integra,
            "resumen": resultado.resumen(),
            "detalle": pd.DataFrame(resultado.detalle, columns=_COLUMNAS_DETALLE),
        }
    except SQLAlchemyError:
        logger.exception("Error de base de datos al verificar la bitácora.")
        st.error("No fue posible verificar la bitácora. Intente de nuevo más tarde.")
    finally:
        db.close()


def _mostrar_resultado(resultado: dict) -> None:
    resumen = resultado["resumen"]
    cols = st.columns(4)
    with cols[0]:
        ui_components.kpi("Resultado", resumen["Resultado"],
                          f"Verificada el {resultado['verificado_en']}",
                          tone="green" if resultado["integra"] else "red")
    with cols[1]:
        ui_components.kpi("Eslabones verificados", resumen["Eslabones verificados"],
                          f"de {resumen['Eslabones encadenados']} encadenados", tone="amber")
    with cols[2]:
        ui_components.kpi("Registros pre-cadena", resumen["Registros pre-cadena (anteriores a la migración 006)"],
                          "Anteriores a la cadena; protegidos sin UPDATE ni DELETE", tone="amber")
    with cols[3]:
        ui_components.kpi("Primer seq roto", resumen["Primer seq roto"] or "Ninguno",
                          resumen["Motivo"][:80], tone="green" if resultado["integra"] else "red")
    if resultado["integra"]:
        st.success(f"{resumen['Motivo']}: {resumen['Eslabones verificados']} eslabones verificados sin alteraciones.")
    else:
        st.error(f"Cadena rota en el eslabón {resumen['Primer seq roto']}: {resumen['Motivo']}")
    ui_components.section_title("Resumen de la verificación")
    st.markdown(render_html_table(
        pd.DataFrame({"Indicador": list(resumen.keys()), "Valor": list(resumen.values())}), max_height=380,
    ), unsafe_allow_html=True)
    detalle: pd.DataFrame = resultado["detalle"]
    ui_components.section_title("Detalle por eslabón")
    if detalle.empty:
        ui_components.info_panel("La licencia todavía no tiene eslabones encadenados.")
    else:
        rotos = detalle[detalle["estado"] != auditoria.ESTADO_OK]
        visibles = pd.concat([rotos, detalle.tail(_FILAS_VISIBLES)]).drop_duplicates("seq").sort_values("seq")
        st.caption(
            f"Se muestran {len(visibles)} de {len(detalle)} eslabones (los rotos y los {_FILAS_VISIBLES} más recientes). "
            "El reporte exportable incluye todos."
        )
        st.markdown(render_html_table(visibles, max_height=420), unsafe_allow_html=True)
    _exportar(resultado)


def _exportar(resultado: dict) -> None:
    resumen = resultado["resumen"]
    encabezado = pd.DataFrame({
        "seq": [""] * (len(resumen) + 2), "timestamp": [""] * (len(resumen) + 2),
        "usuario": ["Verificado por", "Verificado en"] + list(resumen.keys()),
        "modulo": [resultado["verificado_por"], resultado["verificado_en"]] + list(resumen.values()),
    })
    reporte = pd.concat([encabezado, resultado["detalle"]], ignore_index=True)
    nombre = f"verificacion_bitacora_{resultado['verificado_en'][:10]}.csv"
    exportacion.boton_descarga(
        "Exportar reporte de verificación (CSV)", exportacion.csv_bytes(reporte), nombre, "text/csv",
        modulo=auditoria.MODULO_INTEGRIDAD, key="integridad_exportar",
    )
    st.caption("El CSV se sanea contra inyección de fórmulas y la descarga queda registrada en la bitácora.")
