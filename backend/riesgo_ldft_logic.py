"""
riesgo_ldft_logic.py — Motor de cálculo puro para la Administración de Riesgo
Institucional de LD/FT (Lavado de Dinero y Financiamiento del Terrorismo).

Basado en el modelo GAFILAT / IVE Guatemala (Decreto 15-2026, Art. 8-11) y en
los ejemplos numéricos de la guía "Administración de Riesgos de LD/FT 2026"
(GERILAFT App) publicada por la Intendencia de Verificación Especial (IVE).

Supuestos de ingeniería explícitos — la norma deja la metodología concreta a
criterio de cada Persona Obligada (la propia guía lo indica: "La PO debe
definir en su metodología los criterios..."). Estos supuestos fueron
reconstruidos y validados exactamente contra los ejemplos numéricos de la
lámina "Etapa de Control" del documento fuente:

  1. Impacto por riesgos asociados = MÁXIMO entre Operacional/Legal/
     Reputacional/Contagio (criterio prudencial, ISO 31000 §6.4: el escenario
     más adverso determina el impacto final del evento).
  2. Bandas de la matriz de calor (probabilidad x impacto, escala 1-4 cada
     una) replican exactamente los colores de la lámina "Etapa de Medición".
  3. Ponderación de controles (0-100) usa los pesos textuales del documento
     (documentado 10% + tipo 10% + ejecución 10% + cumplimiento 30% +
     efectividad 40%); los puntos por cada opción de "tipo de control" y
     "ejecución" fueron interpolados a partir de los únicos valores visibles
     en el ejemplo (Preventivo/Detectivo, Automático/Manual) y son ajustables
     en este módulo si la PO documenta otra escala en su metodología propia.
  4. Riesgo residual = min(riesgo inherente, promedio redondeado del nivel de
     ponderación de los controles vinculados). Validado exactamente contra
     los 3 casos (Evento A/B/C) de la lámina "Etapa de Control".

Este módulo es puro: no importa Streamlit ni SQLAlchemy, para poder probarse
de forma aislada (ver tests si se agregan más adelante).
"""
from __future__ import annotations

NIVELES_RIESGO = {1: "Bajo", 2: "Medio Bajo", 3: "Medio Alto", 4: "Alto"}

# Paleta fiel a la semaforización del documento fuente GAFILAT/IVE
# (distinta de la paleta IMPERATOR usada en el resto de Sovereign-AML,
# para que un revisor de la IVE reconozca el mismo código de colores).
COLOR_NIVEL = {1: "#3b82f6", 2: "#22c55e", 3: "#eab308", 4: "#ef4444"}

NIVELES_CONTROL = {1: "Bueno", 2: "Adecuado", 3: "Mejorable", 4: "Deficiente"}

_PESO_TIPO_CONTROL = {"Preventivo": 10, "Detectivo": 8, "Correctivo": 6}
_PESO_EJECUCION = {"Automático": 10, "Semiautomático": 7, "Manual": 5}
_ORDEN_NIVEL_CUALITATIVO = {"Bueno": 0, "Adecuado": 1, "Mejorable": 2, "Deficiente": 3}

FACTORES_LDFT = (
    "Clientes", "Productos y Servicios", "Canales de Distribución", "Ubicación Geográfica"
)
TIPOS_CONTROL = ("Preventivo", "Detectivo", "Correctivo")
EJECUCIONES_CONTROL = ("Automático", "Semiautomático", "Manual")
NIVELES_CUALITATIVOS = ("Bueno", "Adecuado", "Mejorable", "Deficiente")


def calcular_impacto(
    riesgo_operacional: int, riesgo_legal: int, riesgo_reputacional: int, riesgo_contagio: int
) -> int:
    """Impacto final del evento = el escenario más adverso entre los 4 riesgos asociados."""
    return max(riesgo_operacional, riesgo_legal, riesgo_reputacional, riesgo_contagio)


def nivel_desde_producto(probabilidad: int, impacto: int) -> int:
    """
    Traduce probabilidad x impacto (cada uno 1-4) al nivel de riesgo LD/FT (1-4),
    replicando la matriz de calor GAFILAT: {1,2}->1 Bajo | {3,4}->2 Medio Bajo |
    {6,8,9}->3 Medio Alto | {12,16}->4 Alto.
    """
    producto = probabilidad * impacto
    if producto <= 2:
        return 1
    if producto <= 4:
        return 2
    if producto <= 9:
        return 3
    return 4


def descripcion_nivel(nivel: int) -> str:
    return NIVELES_RIESGO.get(nivel, "Desconocido")


def color_nivel(nivel: int) -> str:
    return COLOR_NIVEL.get(nivel, "#8b949e")


def _puntos_nivel_cualitativo(nivel: str, maximo: int) -> int:
    idx = _ORDEN_NIVEL_CUALITATIVO.get(nivel, 3)
    # Redondeo "media hacia arriba" (no bankers' rounding de round()) para que
    # los .5 (ej. 30*3/4=22.5) coincidan con los valores de referencia del
    # documento fuente (C2: Adecuado/30 -> 23, no 22).
    return int((maximo * (4 - idx) / 4) + 0.5)


def calcular_ponderacion_control(
    documentado: bool,
    tipo_control: str,
    ejecucion: str,
    nivel_cumplimiento: str,
    nivel_efectividad: str,
) -> int:
    """
    Ponderación 0-100 del control/mitigador según los pesos del modelo GAFILAT:
    documentado (10%) + tipo de control (10%) + ejecución (10%) +
    cumplimiento (30%) + efectividad (40%).
    """
    pts_documentado = 10 if documentado else 0
    pts_tipo = _PESO_TIPO_CONTROL.get(tipo_control, 0)
    pts_ejecucion = _PESO_EJECUCION.get(ejecucion, 0)
    pts_cumplimiento = _puntos_nivel_cualitativo(nivel_cumplimiento, maximo=30)
    pts_efectividad = _puntos_nivel_cualitativo(nivel_efectividad, maximo=40)
    total = pts_documentado + pts_tipo + pts_ejecucion + pts_cumplimiento + pts_efectividad
    return max(0, min(100, round(total)))


def nivel_desde_ponderacion(ponderacion: int) -> int:
    """0-100 -> nivel 1-4 (1=Bueno/mejor control ... 4=Deficiente/peor control)."""
    if ponderacion >= 90:
        return 1
    if ponderacion >= 75:
        return 2
    if ponderacion >= 50:
        return 3
    return 4


def calcular_riesgo_residual(nivel_inherente: int, niveles_controles: list) -> int:
    """
    Riesgo residual = min(riesgo inherente, promedio redondeado de la
    ponderación de los controles vinculados al evento). Sin controles
    vinculados, el residual equivale al inherente (sin mitigación aplicada).
    """
    if not niveles_controles:
        return nivel_inherente
    promedio = round(sum(niveles_controles) / len(niveles_controles))
    promedio = max(1, min(4, promedio))
    return min(nivel_inherente, promedio)


def requiere_plan_de_accion(nivel_residual: int) -> bool:
    """Se exige plan de acción cuando el riesgo residual es Medio Alto (3) o Alto (4)."""
    return nivel_residual >= 3


def estado_plan_accion(porcentaje_avance: int) -> str:
    if porcentaje_avance >= 100:
        return "Completado"
    if porcentaje_avance > 0:
        return "En progreso"
    return "Pendiente"
