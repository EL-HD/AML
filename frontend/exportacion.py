"""
Exportación segura de datos (S-09) y auditoría de descargas (S-10).

- sanitizar_celda: neutraliza la inyección de fórmulas CSV/Excel (= + - @ y
  caracteres de control de tabulación/retorno) anteponiendo un apóstrofo.
- csv_bytes / xlsx_bytes: única vía para generar archivos tabulares descargables.
- boton_descarga: envuelve st.download_button registrando EXPORTACION en la bitácora
  solo cuando el usuario pulsa el botón.
"""
import io
from typing import Any, Callable, Optional

import pandas as pd
import streamlit as st

from backend import auditoria

_PREFIJOS_FORMULA = ("=", "+", "-", "@", "\t", "\r")


def sanitizar_celda(valor: Any) -> Any:
    """Devuelve el valor con apóstrofo inicial si Excel/Sheets lo interpretaría como fórmula."""
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return valor
    if isinstance(valor, (int, float, bool)):
        return valor
    texto = str(valor)
    if texto.startswith(_PREFIJOS_FORMULA):
        return "'" + texto
    return texto


def df_seguro(df: pd.DataFrame) -> pd.DataFrame:
    """Copia del DataFrame con todas las celdas de texto saneadas."""
    salida = df.copy()
    for col in salida.columns:
        tipo = salida[col].dtype
        if pd.api.types.is_object_dtype(tipo) or pd.api.types.is_string_dtype(tipo):
            salida[col] = salida[col].map(sanitizar_celda)
    salida.columns = [str(sanitizar_celda(c)) for c in salida.columns]
    return salida


def csv_bytes(df: pd.DataFrame) -> bytes:
    return df_seguro(df).to_csv(index=False).encode("utf-8-sig")


def xlsx_bytes(df: pd.DataFrame, hoja: str = "Datos") -> bytes:
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df_seguro(df).to_excel(writer, index=False, sheet_name=hoja)
    return buffer.getvalue()


def auditar_exportacion(nombre_archivo: str, modulo: str = "Exportación") -> None:
    """Registra una descarga en la bitácora (Art. 19 Ley 6593)."""
    from frontend.mod_sesion import _registrar_acceso_auditoria

    datos = st.session_state.get("user_data") or {}
    _registrar_acceso_auditoria(
        datos.get("user", "desconocido"), datos.get("licence_id"),
        modulo, f"{auditoria.EXPORTACION}:{str(nombre_archivo)[:60]}",
    )


def boton_descarga(label: str, data: Any, file_name: str, mime: str,
                   modulo: str = "Exportación", key: Optional[str] = None,
                   help: Optional[str] = None, use_container_width: bool = False,
                   on_click: Optional[Callable] = None, type: str = "secondary") -> bool:
    """st.download_button con auditoría de la descarga."""
    def _al_pulsar():
        auditar_exportacion(file_name, modulo)
        if on_click is not None:
            on_click()

    return st.download_button(
        label=label, data=data, file_name=file_name, mime=mime, key=key, help=help,
        use_container_width=use_container_width, on_click=_al_pulsar, type=type,
    )
