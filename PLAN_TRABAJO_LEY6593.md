# PLAN DE TRABAJO — SOVEREIGN AML: Adecuación Ley 6593
**Fecha:** 2026-06-08  
**Referencia legal:** Iniciativa de Ley 6593 — *Ley Integral contra el Lavado de Dinero u Otros Activos y el Financiamiento del Terrorismo* (Guatemala)  
**Marco internacional:** GAFI 40 Recomendaciones (convergente con Ley 6593)  
**Estrategia de etiquetado:** doble referencia `GAFI Rec. X / Art. Y Ley 6593` para credibilidad internacional + trazabilidad IVE

---

## ÍNDICE
- [FASE 1 — Terminología (Search & Replace)](#fase-1)
- [FASE 2 — Datos y Flujos](#fase-2)
- [FASE 3 — Nuevos Módulos / Secciones](#fase-3)
- [PENDIENTE — Listas de Sanciones](#pendiente)

---

## FASE 1 — Terminología (Search & Replace) {#fase-1}

> **Instrucción a Claude Code:** Ejecutar los reemplazos exactos indicados. No modificar lógica ni estructura. Solo texto.

---

### T-01 · `frontend/mod_mitigacion.py` — Eliminar "RTI" del catálogo

**Línea 24** — Catálogo de acciones de mitigación:
```python
# ANTES:
{"accion": "Generación de RTS/RTI",  "codigo": "R-01", "norma": "GAFI Rec. 20"},

# DESPUÉS:
{"accion": "Generación de RTS",      "codigo": "R-01", "norma": "GAFI Rec. 20 / Art. 30 Ley 6593"},
```

**Línea 74** — Comentario en lógica de nivel CRÍTICO:
```python
# ANTES:
acciones += ["R-01", "R-02"]          # RTS/RTI + Escalamiento

# DESPUÉS:
acciones += ["R-01", "R-02"]          # RTS + Escalamiento
```

---

### T-02 · `frontend/mod_configuracion.py` — Eliminar "RTI" de etiqueta UI

**Línea 548** — Etiqueta de reportes:
```python
# ANTES:
"Reporte RTI/RTS a la SIB (mediante la IVE)"

# DESPUÉS:
"Reporte RTS a la IVE (Art. 30 Ley 6593)"
```

---

### T-03 · `frontend/mod_reportes.py` — Eliminar "RTI" del docstring

**Línea 876** — Docstring de función:
```python
# ANTES:
"... reporte regulatorio (RTI/RTS a la SIB)."

# DESPUÉS:
"... reporte regulatorio (RTS a la IVE — Art. 30 Ley 6593)."
```

---

### T-04 · `frontend/mod_red_transaccional.py` — Actualizar acrónimo LD/FT

**Línea 378** — Texto HTML:
```python
# ANTES:
"Patrón típico de <em>layering</em> (estratificación) en esquemas de LD/FT."

# DESPUÉS:
"Patrón típico de <em>layering</em> (estratificación) en esquemas de LD/FT/FPADM."
```

---

### T-05 · `frontend/mod_matrices.py` — Actualizar glosario SC_Max

**Línea 15** — Descripción del score contextual:
```python
# ANTES:
"<span class='glossary-key'>ST_Max / SC_Max</span><span>Riesgo Transaccional (Reglas) y Contextual (PEP, CPE, Geo).</span>"

# DESPUÉS:
"<span class='glossary-key'>ST_Max / SC_Max</span><span>Riesgo Transaccional (Reglas) y Contextual (PEP, CPE, Geo, Beneficiario Final).</span>"
```

---

### T-06 · `frontend/mod_manual.py` — Título del manual de plataforma

**Línea 6** — Título de la sección de documentación técnica:
```python
# ANTES:
"<strong>Manual de Usuario — Versión 3.1</strong> — Documentación técnica integrada de ejecución y uso."

# DESPUÉS:
"<strong>Manual de Prevención LD/FT/FPADM — Versión 3.1</strong> — Documentación técnica integrada de ejecución y uso. (Art. 12 Ley 6593)"
```

---

## FASE 2 — Datos y Flujos {#fase-2}

> **Instrucción a Claude Code:** Para cada sección, agregar campos y lógica nueva. No eliminar campos existentes. Mantener compatibilidad con DataFrames de entrada que pueden no traer las columnas nuevas (usar `.get()` o `if col in df.columns`).

---

### D-01 · `frontend/mod_alertas.py` — Ciclo de vida Inusual → Sospechosa

**Propósito:** Implementar el flujo legal de dos fases: detección de Transacción Inusual → examen analista → clasificación como Sospechosa → generación de RTS. (Arts. 28-30 Ley 6593)

**Campos nuevos a agregar en el DataFrame de casos (si no existen, inicializar con valor default):**

```python
# Agregar al inicializar / filtrar el DataFrame de casos:
if "Estado_Alerta" not in casos.columns:
    casos["Estado_Alerta"] = "Inusual_Pendiente"

if "Fundamento_Examen" not in casos.columns:
    casos["Fundamento_Examen"] = ""

if "Fecha_Clasificacion_Sospechosa" not in casos.columns:
    casos["Fecha_Clasificacion_Sospechosa"] = None
```

**Valores válidos para `Estado_Alerta`:**
```python
ESTADOS_ALERTA = [
    "Inusual_Pendiente",       # Detectado por IMPERATOR, sin examinar
    "Inusual_Examinada",       # Analista revisó, no escaló
    "Sospechosa_Confirmada",   # Analista confirmó — requiere RTS (Art. 30)
    "Descartada",              # Falso positivo documentado
]
```

**Filtro UI a agregar (después del slider de Score mínimo):**
```python
estado_filtro = st.selectbox(
    "Filtrar por estado",
    ["Todos"] + ESTADOS_ALERTA,
    key="filtro_estado_alerta"
)
if estado_filtro != "Todos":
    casos = casos[casos["Estado_Alerta"] == estado_filtro]
```

**Panel de acción por fila (expandible por caso seleccionado):**
```python
# Agregar después de la tabla principal de casos:
caso_idx = st.selectbox("Seleccionar caso para gestionar", casos.index.tolist(), key="sel_caso")
if caso_idx is not None:
    with st.expander("Gestión del caso", expanded=False):
        nuevo_estado = st.selectbox("Clasificar como", ESTADOS_ALERTA, key="nuevo_estado")
        fundamento = st.text_area(
            "Fundamento del examen (Art. 29 Ley 6593)",
            value=str(casos.at[caso_idx, "Fundamento_Examen"]),
            key="fundamento_examen",
            help="Describe la base legal/económica que justifica o descarta la operación sospechosa."
        )
        if st.button("💾 Guardar clasificación", key="btn_clasificar"):
            casos.at[caso_idx, "Estado_Alerta"] = nuevo_estado
            casos.at[caso_idx, "Fundamento_Examen"] = fundamento
            if nuevo_estado == "Sospechosa_Confirmada":
                casos.at[caso_idx, "Fecha_Clasificacion_Sospechosa"] = datetime.now().date()
                st.warning("⚠️ Caso clasificado como SOSPECHOSO. Proceder a generar RTS ante la IVE (Art. 30 Ley 6593).")
            st.success("Clasificación guardada.")
```

**Importación requerida** (verificar que exista en el archivo):
```python
from datetime import datetime
```

---

### D-02 · `frontend/mod_transacciones.py` — Tipo de instrumento y detección RTE

**Propósito:** Identificar transacciones en efectivo ≥ USD 10,000 para Reporte de Transacción en Efectivo (RTE) ante la IVE. (Art. 31 Ley 6593)

**Agregar columna de visualización con guard de existencia:**
```python
# Dentro del bloque que construye columnas_mostrar:
if "Tipo_Instrumento" in df_view.columns:
    columnas_mostrar.insert(columnas_mostrar.index("Monto") + 1, "Tipo_Instrumento")

if "Es_RTE" in df_view.columns:
    columnas_mostrar.append("Es_RTE")
```

**Agregar lógica de detección RTE** (ejecutar sobre el DataFrame antes de visualización):
```python
UMBRAL_RTE_USD = 10_000  # Art. 31 Ley 6593

def _detectar_rte(df: pd.DataFrame, col_monto: str = "Monto", col_tipo: str = "Tipo_Instrumento") -> pd.DataFrame:
    """Marca transacciones en efectivo >= USD 10,000 para RTE (Art. 31 Ley 6593)."""
    if col_tipo not in df.columns or col_monto not in df.columns:
        return df
    df["Es_RTE"] = (
        (df[col_tipo].str.upper() == "EFECTIVO") &
        (df[col_monto] >= UMBRAL_RTE_USD)
    )
    return df

df_view = _detectar_rte(df_view)
```

**Agregar al `rename_cols` de la tabla:**
```python
rename_cols["Tipo_Instrumento"] = "Instrumento"
rename_cols["Es_RTE"] = "RTE (Art.31)"
```

**Agregar indicador de alerta RTE encima de la tabla:**
```python
if "Es_RTE" in df_view.columns:
    n_rte = df_view["Es_RTE"].sum()
    if n_rte > 0:
        st.warning(f"⚠️ {n_rte} transacción(es) en efectivo ≥ USD {UMBRAL_RTE_USD:,} — Requieren RTE ante la IVE (Art. 31 Ley 6593)")
```

---

### D-03 · `frontend/mod_cliente.py` — Beneficiario Final (UBO) y nuevos tipos

**Propósito:** Registrar y visualizar el Beneficiario Final (UBO) conforme Art. 21 num. 2 Ley 6593. Agregar `Estructura_Jurídica` como tipo de cliente y `PSAV` como categoría de Persona Obligada.

**A. Nuevos campos UBO** — Agregar en la sección de datos del cliente (donde aparecen `EsPEP`, `EsCPE`):
```python
# --- BENEFICIARIO FINAL (UBO) — Art. 21 num. 2 Ley 6593 ---
with st.expander("Beneficiario Final (UBO)", expanded=False):
    col_u1, col_u2 = st.columns(2)
    with col_u1:
        benef_final = info_cliente.get("Beneficiario_Final", "No registrado")
        st.markdown(f"**Beneficiario Final:** {benef_final}")
        
        pct_participacion = info_cliente.get("Porcentaje_Participacion", None)
        if pct_participacion is not None:
            st.markdown(f"**Participación:** {pct_participacion:.1f}%")
    
    with col_u2:
        es_pep_ubo = info_cliente.get("EsPEP_UBO", False)
        if es_pep_ubo:
            st.error("🔴 UBO es PEP — DDA Obligatoria (GAFI Rec. 12 / Art. 25a Ley 6593)")
        
        fuente_ubo = info_cliente.get("Fuente_Verificacion_UBO", "—")
        st.markdown(f"**Fuente de verificación:** {fuente_ubo}")
```

**B. Impacto UBO-PEP en SC_Max** — Agregar en la función/bloque que calcula o muestra el Score Contextual:
```python
# Incremento de SC por UBO-PEP (Art. 25a Ley 6593 / GAFI Rec. 12)
if info_cliente.get("EsPEP_UBO", False):
    sc_ajuste = 1.0  # Penalización SC por UBO con perfil PEP
    st.caption(f"⚠️ SC incluye +{sc_ajuste:.1f} pts por Beneficiario Final PEP (Art. 25a)")
```

**C. Tipos de cliente extendidos** — Agregar `Estructura_Jurídica` donde se muestra/filtra el tipo de cliente:
```python
TIPOS_CLIENTE = [
    "Persona Individual",
    "Persona Jurídica",
    "Estructura Jurídica",   # NUEVO — trusts, fundaciones (Art. 3 Ley 6593)
]
```

**D. Persona Obligada — agregar PSAV** — Donde se muestra la categoría de sujeto obligado:
```python
TIPOS_PERSONA_OBLIGADA = [
    # ... tipos existentes ...
    "PSAV",  # NUEVO — Proveedor de Servicios de Activos Virtuales (Art. 3 c)1 vii) Ley 6593)
]
```

---

### D-04 · `frontend/mod_resumen.py` — KPIs de cumplimiento obligatorio

**Propósito:** Agregar indicadores de gestión de casos conforme al ciclo Inusual → Sospechosa → RTS. (Arts. 28-30 Ley 6593)

**Agregar en el bloque de KPIs principales** (donde aparecen conteos de `Nivel_Riesgo`):
```python
# --- KPIs de gestión de alertas (Arts. 28-30 Ley 6593) ---
if "Estado_Alerta" in df_casos.columns:
    kpi_inusuales_pendientes = (df_casos["Estado_Alerta"] == "Inusual_Pendiente").sum()
    kpi_sospechosas_sin_rts  = (df_casos["Estado_Alerta"] == "Sospechosa_Confirmada").sum()
    
    col_kpi_a, col_kpi_b = st.columns(2)
    with col_kpi_a:
        color_a = "red" if kpi_inusuales_pendientes > 0 else "green"
        st.metric(
            label="Inusuales pendientes de examen",
            value=kpi_inusuales_pendientes,
            help="Transacciones inusuales detectadas por IMPERATOR sin clasificación del analista (Art. 29 Ley 6593)"
        )
    with col_kpi_b:
        color_b = "red" if kpi_sospechosas_sin_rts > 0 else "green"
        st.metric(
            label="Sospechosas sin RTS generado",
            value=kpi_sospechosas_sin_rts,
            help="Casos confirmados como sospechosos que aún no tienen RTS enviado a la IVE (Art. 30 Ley 6593)"
        )
    
    if kpi_sospechosas_sin_rts > 0:
        st.error(f"🚨 {kpi_sospechosas_sin_rts} caso(s) sospechoso(s) requieren generación urgente de RTS ante la IVE.")
```

---

## FASE 3 — Nuevos Módulos / Secciones {#fase-3}

---

### N-01 · `frontend/mod_reportes.py` — RTS formal y nuevo tipo RTE

**Propósito:** Agregar generadores de reportes en formato estructurado para la IVE.

**A. Agregar tipo de reporte RTE** — En la lógica de selección de tipo de reporte:
```python
# Agregar "RTE" a las opciones de tipo de reporte disponibles:
TIPOS_REPORTE = {
    # ... tipos existentes ...
    "RTE": "Reporte de Transacción en Efectivo (Art. 31 Ley 6593)",
}
```

**B. Función generadora de RTS** — Agregar función de generación con estructura IVE:
```python
def _generar_bloque_rts(canvas_obj, cliente_info: dict, caso_info: dict, y_pos: int) -> int:
    """
    Genera el bloque formal de RTS con estructura compatible IVE.
    Referencia: Art. 30 Ley 6593 / GAFI Rec. 20.
    Retorna la nueva posición Y en el canvas PDF.
    """
    # Encabezado del reporte
    canvas_obj.setFont("Helvetica-Bold", 11)
    canvas_obj.drawString(72, y_pos, "REPORTE DE TRANSACCIÓN SOSPECHOSA (RTS)")
    canvas_obj.setFont("Helvetica", 9)
    canvas_obj.drawString(72, y_pos - 15, "Dirigido a: Intendencia de Verificación Especial (IVE) — SIB")
    canvas_obj.drawString(72, y_pos - 28, f"Base legal: Art. 30 Ley Integral contra LD/FT/FPADM (Ley 6593)")
    
    y_pos -= 50
    
    # Sección I: Datos del sujeto obligado
    canvas_obj.setFont("Helvetica-Bold", 10)
    canvas_obj.drawString(72, y_pos, "I. SUJETO OBLIGADO")
    canvas_obj.setFont("Helvetica", 9)
    y_pos -= 15
    canvas_obj.drawString(90, y_pos, f"Institución: {cliente_info.get('Institucion', '—')}")
    y_pos -= 12
    canvas_obj.drawString(90, y_pos, f"Oficial de Cumplimiento: {cliente_info.get('Oficial_Cumplimiento', '—')}")
    
    y_pos -= 30
    
    # Sección II: Datos del cliente / operación
    canvas_obj.setFont("Helvetica-Bold", 10)
    canvas_obj.drawString(72, y_pos, "II. DATOS DE LA OPERACIÓN SOSPECHOSA")
    canvas_obj.setFont("Helvetica", 9)
    y_pos -= 15
    canvas_obj.drawString(90, y_pos, f"Cliente: {cliente_info.get('Nombre', '—')}")
    y_pos -= 12
    canvas_obj.drawString(90, y_pos, f"NIT/DPI: {cliente_info.get('Identificacion', '—')}")
    y_pos -= 12
    canvas_obj.drawString(90, y_pos, f"Fecha clasificación sospechosa: {caso_info.get('Fecha_Clasificacion_Sospechosa', '—')}")
    y_pos -= 12
    canvas_obj.drawString(90, y_pos, f"Score IMPERATOR: {caso_info.get('Score_Max', '—')}")
    
    y_pos -= 30
    
    # Sección III: Fundamento
    canvas_obj.setFont("Helvetica-Bold", 10)
    canvas_obj.drawString(72, y_pos, "III. FUNDAMENTO DEL REPORTE")
    canvas_obj.setFont("Helvetica", 9)
    y_pos -= 15
    fundamento = caso_info.get("Fundamento_Examen", "Sin fundamento registrado.")
    # Wrap texto largo
    from reportlab.lib.utils import simpleSplit
    lines = simpleSplit(fundamento, "Helvetica", 9, 450)
    for line in lines:
        canvas_obj.drawString(90, y_pos, line)
        y_pos -= 12
    
    return y_pos - 20
```

**C. Función generadora de RTE** — Agregar función paralela para efectivo:
```python
def _generar_bloque_rte(canvas_obj, transacciones_efectivo: list, y_pos: int) -> int:
    """
    Genera el bloque de RTE para transacciones en efectivo >= USD 10,000.
    Referencia: Art. 31 Ley 6593.
    """
    canvas_obj.setFont("Helvetica-Bold", 11)
    canvas_obj.drawString(72, y_pos, "REPORTE DE TRANSACCIÓN EN EFECTIVO (RTE)")
    canvas_obj.setFont("Helvetica", 9)
    canvas_obj.drawString(72, y_pos - 15, "Base legal: Art. 31 Ley Integral contra LD/FT/FPADM (Ley 6593)")
    canvas_obj.drawString(72, y_pos - 28, f"Umbral de reporte: USD {10_000:,} o equivalente")
    
    y_pos -= 50
    canvas_obj.setFont("Helvetica-Bold", 10)
    canvas_obj.drawString(72, y_pos, "TRANSACCIONES INCLUIDAS")
    y_pos -= 15
    
    for tx in transacciones_efectivo:
        canvas_obj.setFont("Helvetica", 9)
        canvas_obj.drawString(90, y_pos,
            f"Cliente: {tx.get('Cliente','—')} | Fecha: {tx.get('Fecha','—')} | "
            f"Monto: USD {tx.get('Monto',0):,.2f}")
        y_pos -= 12
    
    return y_pos - 20
```

---

### N-02 · `frontend/mod_configuracion.py` — Política de retención 5 años

**Propósito:** Configurar y forzar retención mínima de datos por 5 años. (Art. 34 Ley 6593)

**Agregar nueva sección en el módulo de configuración** (al final o en sección "Seguridad/Cumplimiento"):
```python
# ── POLÍTICA DE RETENCIÓN DE DATOS (Art. 34 Ley 6593) ─────────────────────
st.markdown("---")
st.markdown("### 🗄️ Política de Retención de Datos")
st.markdown(
    "**Art. 34 Ley 6593:** Los sujetos obligados deben conservar todos los registros y documentos "
    "por un mínimo de **5 años** desde la fecha de la transacción o finalización de la relación comercial."
)

RETENCION_MINIMA_ANOS = 5  # Art. 34 — no modificable por el usuario

col_ret1, col_ret2 = st.columns(2)
with col_ret1:
    st.metric("Retención mínima obligatoria", f"{RETENCION_MINIMA_ANOS} años", help="Art. 34 Ley 6593 — no configurable")
with col_ret2:
    retencion_config = st.number_input(
        "Retención configurada por la institución (años)",
        min_value=RETENCION_MINIMA_ANOS,
        max_value=20,
        value=RETENCION_MINIMA_ANOS,
        step=1,
        help="No puede ser inferior al mínimo legal de 5 años."
    )

st.info(f"ℹ️ El sistema bloqueará cualquier eliminación de registros con antigüedad inferior a {retencion_config} años.")

# Guard de retención — función reutilizable a usar en cualquier operación de borrado:
def _validar_retencion(fecha_registro, anos_retencion: int = RETENCION_MINIMA_ANOS) -> bool:
    """
    Retorna True si el registro puede eliminarse (superó el período de retención).
    Retorna False + lanza advertencia si está dentro del período de retención.
    Referencia: Art. 34 Ley 6593.
    """
    from datetime import date
    if fecha_registro is None:
        return False
    fecha_limite = date.today().replace(year=date.today().year - anos_retencion)
    puede_eliminar = fecha_registro < fecha_limite
    if not puede_eliminar:
        st.error(
            f"🚫 No se puede eliminar este registro. "
            f"La Ley 6593 (Art. 34) exige conservarlo hasta {fecha_registro.replace(year=fecha_registro.year + anos_retencion)}."
        )
    return puede_eliminar
```

---

### N-03 · `frontend/mod_mitigacion.py` — Agregar GAFI Rec. 7 (FPADM)

**Propósito:** Incluir acciones de mitigación específicas para el riesgo de Financiamiento de Proliferación de Armas de Destrucción Masiva. (Art. 2 Ley 6593 / GAFI Rec. 7)

**Agregar entrada en `ACCIONES_MITIGACION["Regulatorias"]`** (después del entry R-02):
```python
# ANTES del cierre del dict Regulatorias, agregar:
{"accion": "Verificación sanciones FPADM (proliferación)",
 "codigo": "R-03",
 "norma": "GAFI Rec. 7 / Art. 2 Ley 6593"},
```

**Agregar en la lógica `_determinar_acciones`** para nivel CRÍTICO con factor FPADM:
```python
# Dentro del bloque CRÍTICO, después de la línea R-01/R-02:
if row.get("EsFPADM", False) or row.get("Nivel_Riesgo") == "Crítico":
    acciones += ["R-03"]  # Verificación FPADM / sanciones proliferación
```

**Actualizar el glosario de acciones** donde se describe R-01/R-02:
```python
# En el bloque de st.markdown del glosario RBA, agregar:
"<div class='glossary-item'><span class='glossary-key'>R-03</span>"
"<span>Verificación en listas de sanciones por proliferación (GAFI Rec. 7 / Art. 2 Ley 6593).</span></div>"
```

---

### N-04 · `frontend/mod_sesion.py` — Verificar auditoría de accesos

**Propósito:** Garantizar que cada acceso quede registrado para cumplir el deber de confidencialidad y trazabilidad del Oficial de Cumplimiento. (Art. 19 Ley 6593)

**Verificar si existe este bloque. Si NO existe, agregar al inicio de la función principal del módulo:**
```python
def _registrar_acceso_auditoria(usuario: str, modulo: str, accion: str = "VISUALIZACION") -> None:
    """
    Registra acceso en bitácora para cumplimiento Art. 19 Ley 6593.
    Almacena: usuario, timestamp, módulo accedido, acción realizada.
    """
    import streamlit as st
    if "auditoria_sesion" not in st.session_state:
        st.session_state["auditoria_sesion"] = []
    
    st.session_state["auditoria_sesion"].append({
        "timestamp": datetime.now().isoformat(),
        "usuario": usuario,
        "modulo": modulo,
        "accion": accion,
    })

# Invocar al cargar cada módulo sensible (alertas, reportes, configuración):
_registrar_acceso_auditoria(
    usuario=st.session_state.get("username", "desconocido"),
    modulo="mod_sesion",
    accion="ACCESO_MODULO"
)
```

> **Nota para Claude Code:** Verificar si `BitacoraSesions` en `backend/models.py` ya persiste estos datos en DB. Si no tiene columna `modulo_accedido` ni `accion`, agregar esos campos al modelo SQLAlchemy y la migración correspondiente.

---

## ⏳ PENDIENTE — Listas de Sanciones {#pendiente}

> **`frontend/mod_listas_sanciones.py`** — **NO IMPLEMENTAR en este ciclo.**

**Estado:** En evaluación. El equipo está analizando la compra de una API externa (OFAC/ONU) para consultas de listas de sanciones en lugar de desarrollo in-house.

**Decisión requerida antes de continuar:**
- [ ] Evaluar proveedores: Dow Jones Risk & Compliance, LexisNexis WorldCompliance, ComplyAdvantage, OFAC SDN API directa
- [ ] Comparar costo por consulta vs. volumen mensual estimado
- [ ] Definir si la integración será sincrónica (en tiempo real al crear cliente) o asincrónica (batch nocturno)
- [ ] Verificar si el proveedor cubre listas ONU, OFAC, UE y listas nacionales guatemaltecas (CONAPLAFT)

**Cuando se retome**, la integración debe cubrir: GAFI Rec. 6 (PEP y sanciones específicas) + GAFI Rec. 7 (proliferación) + Art. 25 Ley 6593.

---

## CHECKLIST DE EJECUCIÓN

```
FASE 1 — Terminología
[ ] T-01 · mod_mitigacion.py — Eliminar RTI del catálogo (líneas 24, 74)
[ ] T-02 · mod_configuracion.py — Eliminar RTI de etiqueta UI (línea 548)
[ ] T-03 · mod_reportes.py — Eliminar RTI del docstring (línea 876)
[ ] T-04 · mod_red_transaccional.py — LD/FT → LD/FT/FPADM (línea 378)
[ ] T-05 · mod_matrices.py — Actualizar glosario SC_Max (línea 15)
[ ] T-06 · mod_manual.py — Actualizar título del manual (línea 6)

FASE 2 — Datos y Flujos
[ ] D-01 · mod_alertas.py — Ciclo Inusual → Sospechosa (Estado_Alerta, Fundamento_Examen, botón)
[ ] D-02 · mod_transacciones.py — Tipo_Instrumento visible + detección RTE efectivo ≥ USD 10,000
[ ] D-03 · mod_cliente.py — UBO (Beneficiario_Final, EsPEP_UBO, Fuente) + SC ajuste + PSAV + Estructura_Jurídica
[ ] D-04 · mod_resumen.py — KPIs: inusuales pendientes + sospechosas sin RTS

FASE 3 — Nuevos Módulos / Secciones
[ ] N-01 · mod_reportes.py — Generadores RTS (Art. 30) y RTE (Art. 31) con estructura IVE
[ ] N-02 · mod_configuracion.py — Sección retención 5 años + función guard _validar_retencion()
[ ] N-03 · mod_mitigacion.py — Entrada R-03 GAFI Rec. 7 / FPADM en catálogo
[ ] N-04 · mod_sesion.py — Función _registrar_acceso_auditoria() + verificar BitacoraSesions

PENDIENTE
[ ] ⏳ mod_listas_sanciones.py — En espera de decisión API externa (OFAC/ONU)
```

---

## NOTAS DE SEGURIDAD (OWASP Top 10)

| Control | Aplicación en este plan |
|---------|------------------------|
| A01 — Broken Access Control | Verificar que `mod_sesion.py` restrinja acceso a módulos de RTS/reportes solo a usuarios con rol Oficial de Cumplimiento |
| A02 — Cryptographic Failures | Los `Fundamento_Examen` y datos UBO deben almacenarse cifrados en reposo si se persisten en DB |
| A03 — Injection | Los campos de texto libre (`Fundamento_Examen`, `Fuente_Verificacion_UBO`) deben sanitizarse antes de incluirse en PDFs generados con ReportLab |
| A09 — Security Logging | La función `_registrar_acceso_auditoria()` es el punto central — no condicionar su ejecución a flags de debug |
| A10 — SSRF | Cuando se integre la API externa de sanciones, validar que las URLs de consulta sean solo las del proveedor configurado |

---

*Plan generado: 2026-06-08 | Referencia: Iniciativa Ley 6593 Guatemala | Análisis de brechas: `Analisis_Brechas_SOVEREIGN_Ley6593.docx`*
