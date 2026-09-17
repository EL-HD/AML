"""
mod_mfa.py: vista "Seguridad de la Cuenta" (Administración) y pantalla de
enrolamiento obligatorio del segundo factor (T6 Fase 2, OWASP A07).

- Enrolamiento TOTP (RFC 6238): URI otpauth, código QR si la librería `qrcode`
  está instalada (dependencia opcional) o, en su defecto, la clave en bloques
  para ingreso manual; confirmación con un código antes de activar; códigos de
  recuperación mostrados una sola vez.
- Restablecimiento propio con código y, para administradores, restablecimiento
  del MFA de otro usuario (auditado; nunca el propio por esta vía).
- La lógica y las validaciones viven en backend/mfa.py; aquí solo se presenta.
  Todo valor dinámico pasa por ui_safe.h o ui_components (escape OWASP A03).
"""
import base64
import io
import logging
from typing import Optional

import streamlit as st
from sqlalchemy.exc import SQLAlchemyError

from backend import crud, mfa
from backend.database import SessionLocal
from frontend import casos_persistencia, permisos, ui_components
from frontend.ui_safe import h, html_block

logger = logging.getLogger(__name__)

VISTA = "Seguridad de la Cuenta"
_CLAVE_MATERIAL = "mfa_material_enrolamiento"
_CLAVE_CODIGOS = "mfa_codigos_recuperacion"
_CLAVE_GATE = "mfa_gate"
_MENSAJE_BD = "No se pudo consultar el estado del MFA en la base de datos. Intente nuevamente."


# ── Acceso a datos ───────────────────────────────────────────────────────

def _licencia_sesion(db):
    """Licencia ORM del usuario autenticado; None si la sesión no coincide con la BD."""
    licenciaid, usuario, _rol = casos_persistencia.identidad_sesion()
    if not licenciaid:
        return None
    licencia = crud.get_licencia_by_user(db, usuario)
    if licencia is None or str(licencia.licence_id) != str(licenciaid):
        return None
    return licencia


def enrolamiento_obligatorio_pendiente() -> bool:
    """
    True si la política MFA_ENFORCE exige MFA al rol de la sesión y aún no está
    activo. Se memoriza por session_id para no consultar la BD en cada rerun;
    se invalida al confirmar el enrolamiento.
    """
    sid = str(st.session_state.get("session_id") or "")
    memo = st.session_state.get(_CLAVE_GATE)
    if memo and memo.get("sid") == sid:
        return bool(memo.get("pendiente"))
    if not mfa.mfa_obligatorio_para(permisos.rol_actual()):
        st.session_state[_CLAVE_GATE] = {"sid": sid, "pendiente": False}
        return False
    db = SessionLocal()
    try:
        licencia = _licencia_sesion(db)
        pendiente = licencia is not None and mfa.enrolamiento_pendiente(db, licencia)
    except SQLAlchemyError:
        logger.exception("No se pudo evaluar la política MFA; se exige enrolamiento por precaución.")
        pendiente = True
    finally:
        db.close()
    st.session_state[_CLAVE_GATE] = {"sid": sid, "pendiente": pendiente}
    return pendiente


def _invalidar_gate() -> None:
    st.session_state.pop(_CLAVE_GATE, None)


# ── QR opcional ──────────────────────────────────────────────────────────

def qr_png_base64(uri: str) -> Optional[str]:
    """PNG en base64 del QR de la URI otpauth, o None si `qrcode` no está instalado."""
    try:
        import qrcode  # dependencia opcional (requirements.txt); no existe en el contenedor de pruebas
    except ImportError:
        return None
    try:
        imagen = qrcode.make(uri, box_size=6, border=2)
        buf = io.BytesIO()
        imagen.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode("ascii")
    except (ValueError, OSError, AttributeError):
        logger.exception("No se pudo generar el código QR; se muestra la clave manual.")
        return None


# ── Vistas ───────────────────────────────────────────────────────────────

def mostrar() -> None:
    ui_components.page_header(
        VISTA,
        "Segundo factor de autenticación (MFA) con códigos temporales TOTP (RFC 6238) generados por una "
        "aplicación autenticadora. Obligatorio para Administradores y Oficiales de Cumplimiento cuando la "
        "política MFA_ENFORCE está activa.",
    )
    _seccion_propia(obligatorio=False)
    if permisos.puede("restablecer_mfa_usuarios"):
        st.markdown("---")
        _seccion_admin()


def mostrar_enrolamiento_obligatorio() -> None:
    """Pantalla única permitida cuando la política exige MFA y el usuario no está enrolado."""
    ui_components.page_header(
        "Enrolamiento obligatorio del segundo factor",
        "Su rol requiere MFA para operar en Sovereign AML (política MFA_ENFORCE). Complete el enrolamiento "
        "para continuar; hasta entonces no se habilita ninguna otra vista.",
    )
    col_izq, col_der = st.columns([3, 1])
    with col_der:
        if st.button("Cerrar sesión", use_container_width=True, key="mfa_gate_logout"):
            st.session_state["mfa_solicitar_logout"] = True
            st.rerun()
    with col_izq:
        _seccion_propia(obligatorio=True)


def _seccion_propia(obligatorio: bool) -> None:
    db = SessionLocal()
    try:
        licencia = _licencia_sesion(db)
        if licencia is None:
            st.error("No se pudo determinar la licencia de la sesión. Vuelva a iniciar sesión.")
            return
        estado = mfa.estado(db, licencia)
        _panel_estado(estado)
        if st.session_state.get(_CLAVE_CODIGOS):
            _mostrar_codigos_recuperacion()
            return
        if not estado.disponible:
            return
        if estado.activo:
            if not obligatorio:
                _formulario_restablecer_propio(db, licencia)
            return
        _flujo_enrolamiento(db, licencia)
    except SQLAlchemyError:
        logger.exception(_MENSAJE_BD)
        st.error(_MENSAJE_BD)
    finally:
        db.close()


def _panel_estado(estado: mfa.EstadoMfa) -> None:
    if not estado.disponible:
        detalle = (
            f"Defina la variable <code>{h(mfa.VARIABLE_CLAVE)}</code> (clave Fernet generada con "
            "<code>python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\"</code>) "
            "y reinicie el servicio."
            if permisos.rol_actual() == "admin" else "Contacte al administrador del sistema."
        )
        ui_components.info_panel(
            f"El enrolamiento MFA no está disponible porque falta la clave de cifrado del servidor. {detalle}",
            titulo="MFA no disponible", tipo="warning",
        )
    c1, c2, c3 = st.columns(3)
    with c1:
        ui_components.kpi("Estado del MFA", "Activo" if estado.activo else "No enrolado",
                          tone="green" if estado.activo else "amber")
    with c2:
        ui_components.kpi("Política para su rol", "Obligatorio" if estado.obligatorio else "Opcional",
                          tone="red" if estado.enrolamiento_pendiente else "blue")
    with c3:
        ui_components.kpi("Códigos de recuperación", estado.codigos_restantes if estado.activo else "-",
                          sub=("Enrolado el " + estado.enrolado_en[:10]) if estado.enrolado_en else None)


def _flujo_enrolamiento(db, licencia) -> None:
    ui_components.section_title("Enrolar aplicación autenticadora")
    material = st.session_state.get(_CLAVE_MATERIAL)
    if material and material.get("cuenta") != str(licencia.user):
        material = None
        st.session_state.pop(_CLAVE_MATERIAL, None)
    if material is None:
        st.markdown(
            "Necesitará una aplicación autenticadora (Google Authenticator, Microsoft Authenticator, Authy, "
            "1Password u otra compatible con TOTP). Al iniciar se genera un secreto nuevo; el MFA solo se "
            "activa cuando confirme un código válido."
        )
        if st.button("Iniciar enrolamiento", type="primary", key="mfa_iniciar"):
            try:
                st.session_state[_CLAVE_MATERIAL] = mfa.iniciar_enrolamiento(db, licencia)
            except mfa.MfaError as exc:
                st.error(str(exc))
                return
            st.rerun()
        return
    _mostrar_material(material)
    with st.form("mfa_confirmar_form"):
        codigo = st.text_input("Código de 6 dígitos del autenticador", max_chars=8, key="mfa_codigo_confirmar",
                               help="Ingrese el código vigente para confirmar que el dispositivo quedó configurado.")
        confirmar = st.form_submit_button("Confirmar y activar MFA", type="primary", use_container_width=True)
    if st.button("Cancelar y generar otro secreto", key="mfa_cancelar"):
        st.session_state.pop(_CLAVE_MATERIAL, None)
        st.rerun()
    if confirmar:
        try:
            codigos = mfa.confirmar_enrolamiento(db, licencia, codigo, session_id=st.session_state.get("session_id"))
        except mfa.MfaError as exc:
            st.error(str(exc))
            return
        st.session_state.pop(_CLAVE_MATERIAL, None)
        st.session_state[_CLAVE_CODIGOS] = codigos
        # El gate de la política se libera cuando el usuario confirma haber guardado los códigos
        st.rerun()


def _mostrar_material(material: dict) -> None:
    col_qr, col_txt = st.columns([1, 2])
    qr = qr_png_base64(material["uri"])
    with col_qr:
        if qr:
            st.markdown(html_block(
                '<img src="data:image/png;base64,{qr}" alt="Código QR para el autenticador" '
                'style="width:100%;max-width:240px;border-radius:8px;">', qr=qr,
            ), unsafe_allow_html=True)
        else:
            ui_components.info_panel(
                "El código QR no está disponible en este servidor (librería opcional <code>qrcode</code> no "
                "instalada). Ingrese la clave manualmente en su autenticador.",
                titulo="Ingreso manual",
            )
    with col_txt:
        st.markdown("**1.** Escanee el QR o añada una cuenta manualmente con estos datos:")
        st.markdown(html_block(
            '<div class="info-box"><div><strong>Cuenta:</strong> {emisor} ({cuenta})</div>'
            '<div><strong>Clave (Base32):</strong> <code style="font-size:1.05rem;letter-spacing:0.08em;">{bloques}</code></div>'
            '<div><strong>Tipo:</strong> basado en tiempo (TOTP), SHA-1, 6 dígitos, 30 segundos</div></div>',
            emisor=material["emisor"], cuenta=material["cuenta"], bloques=material["secreto_bloques"],
        ), unsafe_allow_html=True)
        with st.expander("Ver URI otpauth (para importación manual)"):
            st.code(material["uri"], language=None)
        st.markdown("**2.** Ingrese el código que muestra la aplicación y confirme.")


def _mostrar_codigos_recuperacion() -> None:
    codigos = st.session_state.get(_CLAVE_CODIGOS) or []
    ui_components.info_panel(
        "MFA activado. Guarde estos códigos de recuperación en un lugar seguro: <strong>no volverán a "
        "mostrarse</strong> y cada uno sirve una sola vez para entrar si pierde el dispositivo.",
        titulo="Códigos de recuperación", tipo="warning",
    )
    filas = "".join(html_block('<div style="padding:4px 0;"><code>{c}</code></div>', c=c) for c in codigos)
    st.markdown(html_block(
        '<div class="info-box" style="columns:2;font-size:1.05rem;letter-spacing:0.05em;">{filas}</div>', filas=filas,
    ), unsafe_allow_html=True)
    st.download_button(
        "Descargar códigos (.txt)", data="\n".join(codigos).encode("utf-8"),
        file_name="sovereign_aml_codigos_recuperacion.txt", mime="text/plain", key="mfa_descargar_codigos",
    )
    if st.button("He guardado mis códigos", type="primary", key="mfa_codigos_ok"):
        st.session_state.pop(_CLAVE_CODIGOS, None)
        _invalidar_gate()
        st.rerun()


def _formulario_restablecer_propio(db, licencia) -> None:
    ui_components.section_title("Cambiar de dispositivo o desactivar")
    st.markdown(
        "Para volver a enrolar (nuevo teléfono) debe restablecer el MFA presentando un código vigente del "
        "autenticador o uno de recuperación. Si su rol lo exige, tendrá que enrolar de nuevo de inmediato."
    )
    with st.form("mfa_restablecer_form"):
        codigo = st.text_input("Código TOTP o de recuperación", max_chars=16, key="mfa_codigo_restablecer")
        enviar = st.form_submit_button("Restablecer mi MFA")
    if enviar:
        try:
            mfa.restablecer_propio(db, licencia, codigo)
        except mfa.MfaError as exc:
            st.error(str(exc))
            return
        _invalidar_gate()
        st.success("MFA restablecido. Puede enrolar un nuevo dispositivo.")
        st.rerun()


def _seccion_admin() -> None:
    ui_components.section_title("Restablecer el MFA de otro usuario (Administrador)")
    st.markdown(
        "Use esta opción cuando un usuario perdió su dispositivo y no conserva códigos de recuperación. "
        "La acción queda auditada en la bitácora del administrador y del usuario. No es posible restablecer "
        "el propio MFA por esta vía."
    )
    with st.form("mfa_admin_reset_form"):
        usuario = st.text_input("Nombre de usuario", max_chars=100, key="mfa_admin_usuario")
        confirmado = st.checkbox("Confirmo la identidad del usuario por un canal independiente", key="mfa_admin_confirma")
        enviar = st.form_submit_button("Restablecer MFA del usuario")
    if not enviar:
        return
    if not confirmado:
        st.error("Debe confirmar la verificación de identidad antes de restablecer.")
        return
    db = SessionLocal()
    try:
        admin = _licencia_sesion(db)
        objetivo = crud.get_licencia_by_user(db, (usuario or "").strip())
        if admin is None or objetivo is None:
            st.error("Usuario no encontrado.")
            return
        mfa.restablecer_por_admin(db, admin, objetivo)
        st.success(f"MFA restablecido para '{objetivo.user}'. El usuario deberá enrolar de nuevo.")
    except mfa.MfaError as exc:
        st.error(str(exc))
    except SQLAlchemyError:
        logger.exception("No se pudo restablecer el MFA del usuario.")
        st.error(_MENSAJE_BD)
    finally:
        db.close()
