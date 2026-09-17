"""
mod_screening.py: vista "Listas de Sanciones" (GAFI R.6 / R.7).

Pestañas:
  * Listas cargadas: versiones activas y carga de archivos (solo admin).
    Descarga oficial opcional (SCREENING_AUTO_DOWNLOAD) desde URLs fijas.
  * Ejecutar screening: clientes y Cliente_Destino del análisis cargado
    (admin/oficial), umbral configurable.
  * Bandeja de coincidencias: decisión Descartada/Confirmada con fundamento
    obligatorio (admin/oficial); analista y auditor solo lectura.

Todo valor dinámico se escapa con frontend/ui_safe.h; los componentes
provienen de frontend/ui_components.
"""
import logging

import pandas as pd
import streamlit as st
from sqlalchemy.exc import SQLAlchemyError

from backend import screening, screening_repo
from backend.database import SessionLocal
from frontend import casos_persistencia, permisos, ui_components
from frontend.mod_utils import render_html_table
from frontend.ui_safe import h

logger = logging.getLogger(__name__)

_EXTENSIONES = {screening.FUENTE_OFAC: ("csv",), screening.FUENTE_ONU: ("xml",)}
_ETIQUETA_FUENTE = {screening.FUENTE_OFAC: "OFAC SDN (Estados Unidos)", screening.FUENTE_ONU: "ONU lista consolidada"}
_TONO_SENAL = {"Confirmada": "critico", "Pendiente": "alerta"}


def mostrar() -> None:
    ui_components.page_header(
        "Listas de Sanciones",
        "Screening de clientes y contrapartes contra OFAC SDN y la lista consolidada del Consejo de Seguridad "
        "de la ONU (Recomendaciones 6 y 7 del GAFI). Toda coincidencia requiere revisión humana con fundamento.",
    )
    if not permisos.puede("ver_screening"):
        permisos.aviso_solo_lectura("ver_screening")
        return
    db = SessionLocal()
    try:
        tab_listas, tab_ejecutar, tab_bandeja = st.tabs(["Listas cargadas", "Ejecutar screening", "Bandeja de coincidencias"])
        with tab_listas:
            _tab_listas(db)
        with tab_ejecutar:
            _tab_ejecutar(db)
        with tab_bandeja:
            _tab_bandeja(db)
    except SQLAlchemyError:
        logger.exception("Error de base de datos en Listas de Sanciones.")
        st.error("No fue posible acceder a la base de datos de listas de sanciones. Intente de nuevo más tarde.")
    finally:
        db.close()


# ── Listas ───────────────────────────────────────────────────────────────

def _tab_listas(db) -> None:
    activas = screening_repo.listas_activas(db)
    cols = st.columns(2)
    for i, fuente in enumerate(screening.FUENTES):
        lista = next((l for l in activas if l.fuente == fuente), None)
        with cols[i]:
            if lista is None:
                ui_components.kpi(_ETIQUETA_FUENTE[fuente], "Sin cargar", "Un Administrador debe cargar la lista", tone="red")
            else:
                ui_components.kpi(_ETIQUETA_FUENTE[fuente], f"{lista.cantidad_entradas:,}",
                                  f"Versión {lista.version} · SHA-256 {lista.hash_sha256[:12]}", tone="green")
    historial = screening_repo.listar_listas(db, limite=20)
    if historial:
        ui_components.section_title("Versiones cargadas")
        tabla = pd.DataFrame([{
            "Fuente": l.fuente, "Versión": l.version, "Archivo": l.nombre_archivo, "Entradas": l.cantidad_entradas,
            "Rechazadas": l.filas_rechazadas, "Origen": l.origen, "Activa": "Sí" if l.activa else "No",
            "SHA-256": l.hash_sha256[:16], "Cargada por": l.cargada_por,
            "Fecha": screening_repo.formato_fecha(l.cargada_en),
        } for l in historial])
        st.markdown(render_html_table(tabla, max_height=300), unsafe_allow_html=True)
    if not permisos.puede("cargar_listas_sancion"):
        ui_components.info_panel("Solo un Administrador puede cargar o actualizar las listas.")
        return
    _formulario_carga(db)


def _formulario_carga(db) -> None:
    ui_components.section_title("Cargar nueva versión")
    ui_components.info_panel(
        "OFAC: archivos oficiales sdn.csv y alt.csv (sin encabezado). ONU: consolidated.xml. "
        f"Tamaño máximo {screening.MAX_BYTES_ARCHIVO // (1024 * 1024)} MB por archivo; se rechazan XML con DOCTYPE o ENTITY.",
    )
    fuente = st.selectbox("Fuente", list(screening.FUENTES), format_func=lambda f: _ETIQUETA_FUENTE[f], key="scr_fuente")
    version = st.text_input("Versión o fecha de publicación (opcional)", max_chars=60, key="scr_version")
    if fuente == screening.FUENTE_OFAC:
        principal = st.file_uploader("sdn.csv", type=["csv"], key="scr_sdn")
        secundario = st.file_uploader("alt.csv (alias, opcional)", type=["csv"], key="scr_alt")
    else:
        principal = st.file_uploader("consolidated.xml", type=["xml"], key="scr_xml")
        secundario = None
    if st.button("Cargar lista", key="btn_cargar_lista") and principal is not None:
        licenciaid, usuario, rol = casos_persistencia.identidad_sesion()
        try:
            nombre = screening.validar_extension(principal.name, _EXTENSIONES[fuente])
            datos = screening.validar_tamano(principal.getvalue())
            datos_alt = None
            if secundario is not None:
                screening.validar_extension(secundario.name, _EXTENSIONES[fuente])
                datos_alt = screening.validar_tamano(secundario.getvalue())
            with st.spinner("Validando y cargando la lista..."):
                lista = screening_repo.cargar_lista(
                    db, fuente, nombre, datos, usuario, rol, licenciaid=licenciaid,
                    secundario=datos_alt, version=version or None,
                )
        except (screening.ErrorScreening, screening_repo.ErrorScreeningRepo) as exc:
            st.error(str(exc))
            return
        st.success(f"Lista {lista.fuente} cargada: {lista.cantidad_entradas:,} entradas "
                   f"({lista.filas_rechazadas} filas rechazadas).")
        st.rerun()
    _panel_descarga_oficial()


def _panel_descarga_oficial() -> None:
    with st.expander("Descarga automática desde fuentes oficiales"):
        st.markdown(
            "La descarga se realiza únicamente desde las URLs fijas definidas en el código "
            "(`www.treasury.gov` y `scsanctions.un.org`), por HTTPS, sin redirecciones, con tiempo máximo "
            f"de {screening.TIMEOUT_DESCARGA} s y tamaño máximo de {screening.MAX_BYTES_ARCHIVO // (1024 * 1024)} MB. "
            f"Está desactivada por defecto: defina `{screening.VARIABLE_AUTO_DESCARGA}=true` en el entorno para habilitarla."
        )
        if not screening.auto_descarga_habilitada():
            st.caption("Descarga automática desactivada en este entorno.")
            return
        fuente_dl = st.selectbox("Fuente a descargar", list(screening.FUENTES),
                                 format_func=lambda f: _ETIQUETA_FUENTE[f], key="scr_fuente_dl")
        if st.button("Descargar y cargar", key="btn_descargar_lista"):
            _descargar_y_cargar(fuente_dl)


def _descargar_y_cargar(fuente: str) -> None:
    licenciaid, usuario, rol = casos_persistencia.identidad_sesion()
    db = SessionLocal()
    try:
        with st.spinner("Descargando desde la fuente oficial..."):
            if fuente == screening.FUENTE_OFAC:
                principal = screening.descargar_oficial(screening.URL_OFAC_SDN)
                secundario = screening.descargar_oficial(screening.URL_OFAC_ALT)
                nombre = "sdn.csv"
            else:
                principal = screening.descargar_oficial(screening.URL_ONU_CONSOLIDADA)
                secundario = None
                nombre = "consolidated.xml"
            lista = screening_repo.cargar_lista(db, fuente, nombre, principal, usuario, rol, licenciaid=licenciaid,
                                                secundario=secundario, origen="descarga_oficial")
        st.success(f"Lista {lista.fuente} descargada y cargada: {lista.cantidad_entradas:,} entradas.")
        st.rerun()
    except (screening.ErrorScreening, screening_repo.ErrorScreeningRepo) as exc:
        st.error(str(exc))
    except OSError as exc:
        logger.warning("Fallo de red al descargar la lista %s: %s", fuente, exc)
        st.error("No fue posible completar la descarga (red o tiempo de espera). Cargue el archivo manualmente.")
    finally:
        db.close()


# ── Ejecución ────────────────────────────────────────────────────────────

def _consultas_del_analisis() -> list:
    """(nombre, origen) desde el DataFrame cargado: columnas Cliente y Cliente_Destino."""
    datos = st.session_state.get("data")
    if not datos:
        return []
    df = datos[0]
    consultas = []
    for columna, origen in (("Cliente", screening_repo.ORIGEN_CLIENTE),
                            ("Cliente_Destino", screening_repo.ORIGEN_DESTINO)):
        if columna in df.columns:
            consultas.extend((valor, origen) for valor in df[columna].dropna().unique())
    return consultas


def _tab_ejecutar(db) -> None:
    if not permisos.exigir_o_avisar("gestionar_screening"):
        return
    consultas = _consultas_del_analisis()
    if not consultas:
        ui_components.empty_state(
            "Sin análisis cargado",
            "El screening se ejecuta sobre los clientes y contrapartes (Cliente_Destino) del archivo analizado.",
            "Vaya a Monitoreo > Resumen Ejecutivo para cargar un archivo.",
        )
        return
    n_cli = sum(1 for _n, o in consultas if o == screening_repo.ORIGEN_CLIENTE)
    n_dest = len(consultas) - n_cli
    c1, c2, c3 = st.columns(3)
    with c1:
        ui_components.kpi("Clientes", n_cli, tone="blue")
    with c2:
        ui_components.kpi("Contrapartes (Cliente_Destino)", n_dest, tone="violet")
    with c3:
        ui_components.kpi("Listas activas", len(screening_repo.listas_activas(db)), tone="amber")
    umbral = st.slider("Umbral de similitud", min_value=screening.UMBRAL_MINIMO, max_value=screening.UMBRAL_MAXIMO,
                       value=screening.UMBRAL_POR_DEFECTO, step=0.01, key="scr_umbral",
                       help="Puntaje mínimo (Jaro-Winkler o comparación por tokens) para registrar una coincidencia.")
    if st.button("Ejecutar screening", key="btn_ejecutar_screening"):
        licenciaid, usuario, rol = casos_persistencia.identidad_sesion()
        try:
            with st.spinner("Comparando nombres contra las listas activas..."):
                resumen = screening_repo.ejecutar_screening(
                    db, licenciaid, consultas, usuario, rol, umbral=umbral,
                    hash_lote=casos_persistencia.hash_lote_sesion(),
                )
        except (screening.ErrorScreening, screening_repo.ErrorScreeningRepo) as exc:
            st.error(str(exc))
            return
        st.success(
            f"Screening completado en {resumen['segundos']} s: {resumen['consultas']} nombres evaluados, "
            f"{resumen['coincidencias']} coincidencias ({resumen['nuevas']} nuevas, {resumen['existentes']} ya registradas)."
        )
        st.session_state.pop("screening_senales", None)


# ── Bandeja ──────────────────────────────────────────────────────────────

def _tab_bandeja(db) -> None:
    licenciaid, usuario, rol = casos_persistencia.identidad_sesion()
    if not licenciaid:
        st.error("No se pudo determinar la licencia de la sesión. Vuelva a iniciar sesión.")
        return
    conteo = screening_repo.resumen_estados(db, licenciaid)
    cols = st.columns(3)
    for col, (estado, tono) in zip(cols, (("Pendiente", "amber"), ("Confirmada", "red"), ("Descartada", "green"))):
        with col:
            ui_components.kpi(estado, conteo.get(estado, 0), tone=tono)
    estado_filtro = st.selectbox("Estado", ["Pendiente", "Confirmada", "Descartada", "Todos"], key="scr_estado")
    coincidencias = screening_repo.listar_coincidencias(db, licenciaid, None if estado_filtro == "Todos" else estado_filtro)
    if not coincidencias:
        ui_components.empty_state("Sin coincidencias en este estado",
                                  "Ejecute el screening o cambie el filtro de estado.")
        return
    tabla = pd.DataFrame([{
        "Cliente": c.cliente, "Origen": c.origen, "Lista": c.fuente, "Entrada": c.nombre_lista,
        "Alias": c.alias_coincidente or "--", "Puntaje": f"{c.puntaje:.3f}", "Motivo": c.motivo,
        "Estado": c.estado, "Revisor": c.revisor or "--",
    } for c in coincidencias])
    st.markdown(render_html_table(tabla, max_height=360), unsafe_allow_html=True)

    opciones = {f"{c.cliente} -> {c.nombre_lista} ({c.fuente}, {c.puntaje:.3f})": c for c in coincidencias}
    etiqueta = st.selectbox("Coincidencia a revisar", list(opciones.keys()), key="scr_seleccion")
    coincidencia = opciones[etiqueta]
    _detalle_coincidencia(coincidencia)
    _historial_decisiones(db, licenciaid, coincidencia)
    if not permisos.puede("gestionar_screening"):
        permisos.aviso_solo_lectura("gestionar_screening")
        return
    destinos = [e for e in (screening_repo.ESTADO_DESCARTADA, screening_repo.ESTADO_CONFIRMADA) if e != coincidencia.estado]
    nuevo_estado = st.selectbox("Decisión", destinos, key="scr_decision")
    fundamento = st.text_area("Fundamento de la decisión (obligatorio)", key="scr_fundamento",
                              max_chars=screening_repo.MAX_CARACTERES_FUNDAMENTO,
                              help="Documente la verificación de identidad (fecha de nacimiento, nacionalidad, documento) que sustenta la decisión.")
    if st.button("Guardar decisión", key="btn_decidir_screening"):
        try:
            resultado = screening_repo.decidir(db, licenciaid, coincidencia.id, nuevo_estado, fundamento, usuario, rol,
                                               hash_lote=casos_persistencia.hash_lote_sesion())
        except (screening.ErrorScreening, screening_repo.ErrorScreeningRepo) as exc:
            st.error(str(exc))
            return
        if resultado.estado == screening_repo.ESTADO_CONFIRMADA:
            st.warning("Coincidencia CONFIRMADA: aplique las medidas de congelamiento y reporte inmediato conforme a "
                       "las Recomendaciones 6 y 7 del GAFI y la normativa de la IVE.")
        st.success("Decisión guardada con fundamento y trazabilidad.")
        st.session_state.pop("screening_senales", None)
        st.rerun()


def _detalle_coincidencia(c) -> None:
    detalle = [
        ("Cliente evaluado", c.cliente), ("Origen", c.origen), ("Lista", c.fuente), ("Referencia", c.referencia),
        ("Entrada de la lista", c.nombre_lista), ("Alias coincidente", c.alias_coincidente or "--"),
        ("Puntaje", f"{c.puntaje:.3f}"), ("Motivo", c.motivo), ("Estado", c.estado),
        ("Revisor", c.revisor or "--"), ("Revisado", screening_repo.formato_fecha(c.revisado_en)),
        ("Caso vinculado", str(c.caso_id)[:16] if c.caso_id else "--"),
    ]
    celdas_html = "".join(
        f'<div class="glossary-item"><span class="glossary-key">{h(k)}</span><span>{h(v)}</span></div>'
        for k, v in detalle
    )
    st.markdown(f'<div class="glossary">{celdas_html}</div>', unsafe_allow_html=True)
    if c.fundamento:
        ui_components.info_panel(c.fundamento, titulo="Fundamento registrado")


def _historial_decisiones(db, licenciaid, c) -> None:
    historial = screening_repo.historial_decisiones(db, licenciaid, c.id)
    if not historial:
        return
    tabla = pd.DataFrame([{
        "Fecha": screening_repo.formato_fecha(d.registrado_en), "De": d.estado_anterior, "A": d.estado_nuevo,
        "Revisor": d.revisor, "Rol": d.rol, "Fundamento": d.fundamento,
    } for d in historial])
    ui_components.section_title("Historial de decisiones")
    st.markdown(render_html_table(tabla, max_height=200), unsafe_allow_html=True)


# ── Integración con otras vistas ─────────────────────────────────────────

def marcar_casos(casos) -> int:
    """Añade la columna Screening_Sanciones al DataFrame de casos (señal por cliente)."""
    licenciaid, _usuario, _rol = casos_persistencia.identidad_sesion()
    if not licenciaid:
        return screening_repo.marcar_dataframe(casos, {})
    senales = st.session_state.get("screening_senales")
    if senales is None:
        db = SessionLocal()
        try:
            senales = screening_repo.senales_por_cliente(db, licenciaid)
        except SQLAlchemyError:
            logger.exception("No se pudieron cargar las señales de screening.")
            senales = {}
        finally:
            db.close()
        st.session_state["screening_senales"] = senales
    return screening_repo.marcar_dataframe(casos, senales)


def senal_cliente(cliente) -> None:
    """Insignia de screening en la ficha del cliente (mod_cliente)."""
    licenciaid, _usuario, _rol = casos_persistencia.identidad_sesion()
    if not licenciaid:
        return
    db = SessionLocal()
    try:
        coincidencias = screening_repo.coincidencias_cliente(db, licenciaid, cliente)
    except SQLAlchemyError:
        logger.exception("No se pudo consultar el screening del cliente.")
        return
    finally:
        db.close()
    vigentes = [c for c in coincidencias if c.estado != screening_repo.ESTADO_DESCARTADA]
    if not vigentes:
        badge = ui_components.status_badge("ok", "Sin coincidencias en listas de sanciones")
        st.markdown(badge, unsafe_allow_html=True)
        return
    estado = "Confirmada" if any(c.estado == screening_repo.ESTADO_CONFIRMADA for c in vigentes) else "Pendiente"
    badge = ui_components.status_badge(_TONO_SENAL[estado], f"Screening de sanciones: {estado} ({len(vigentes)})")
    st.markdown(badge, unsafe_allow_html=True)
    detalle = "; ".join(f"{c.fuente} {c.nombre_lista} ({c.puntaje:.2f})" for c in vigentes[:3])
    ui_components.info_panel(detalle, titulo="Coincidencias", tipo="warning")
