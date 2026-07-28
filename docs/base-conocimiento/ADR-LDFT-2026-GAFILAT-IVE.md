# Administración de Riesgos de LD/FT — GAFILAT / IVE Guatemala (2026)

**Fuente:** `ADR LDFT 2026 POF.pdf` (25 láminas) — analizado 2026-07-27
**Emisor:** Intendencia de Verificación Especial (IVE), Guatemala
**Alcance:** Marco de Administración de Riesgos de Lavado de Dinero u Otros Activos y Financiamiento del Terrorismo (LD/FT) para Personas Obligadas (PO), y presentación de la herramienta **GERILAFT App**.

## 1. Marco normativo

- **GAFI/GAFILAT** — Recomendaciones relevantes: R.1 (evaluación de riesgo y enfoque basado en riesgo), R.10 (debida diligencia del cliente), R.11 (mantenimiento de registros), R.12 (PEP), R.15 (nuevas tecnologías), R.17 (dependencia de terceros), R.18 (controles internos), R.19 (países de mayor riesgo).
- **Guatemala — marco nacional:** Oficios IVE 4125-2015, 3-2016, 4282-2016, 4362-2016; **Decreto 15-2026** ("Ley Integral para la Prevención y Represión del Lavado de Dinero u Otros Activos y del Financiamiento del Terrorismo"), Capítulo III — Enfoque basado en riesgo:
  - Art. 8 — Proceso de administración del riesgo LD/FT/FPADM
  - Art. 9 — Identificación del riesgo LD/FT/FPADM
  - Art. 10 — Evaluación del riesgo LD/FT/FPADM
  - Art. 11 — Mitigación del riesgo LD/FT/FPADM

## 2. Definiciones clave

| Término | Definición |
|---|---|
| Riesgo de LD y FT | Posibilidad de pérdida, daño o consecuencia adversa por exposición de la PO a ser usada directa o indirectamente en LD/FT. |
| Riesgos asociados | Riesgos (operacional, legal, reputacional, contagio) mediante los cuales se materializa el impacto del riesgo de LD/FT. |
| Segmentos de riesgo | Grupos homogéneos de variables dentro de cada factor de riesgo. |
| Riesgo inherente | Riesgo intrínseco de LD/FT al que está expuesta la PO, sin controles. |
| Riesgo residual | Nivel de exposición después de aplicar mitigadores/controles. |

## 3. Etapas de la Administración de Riesgo de LD/FT

1. **Identificación** — Segmentar factores de riesgo e identificar variables y eventos de riesgo, usando fuentes internas/externas (ENR/ESR, informes de amenazas regionales) y monitoreando riesgos emergentes.
   - **Factores estándar:** Clientes, Productos y Servicios, Canales de Distribución, Ubicación Geográfica.
   - **Matriz:** Factor → Segmento → Variable → Evento de riesgo (incidente por el cual podría materializarse el LD/FT: ¿qué podría ocurrir? ¿por qué? ¿qué consecuencia generaría?).
2. **Medición** — Determinar **Probabilidad** (1-Poco probable a 4-Altamente probable) e **Impacto** (1-Menor a 4-Crítico) de cada evento; el cruce en matriz de calor produce el **Riesgo Inherente** (1-Bajo, 2-Medio Bajo, 3-Medio Alto, 4-Alto).
3. **Control** — Los **mitigadores** (programas, políticas, normas, procedimientos, controles internos) se ponderan con 5 atributos: documentado (10%), tipo de control (10%), ejecución (10%), nivel de cumplimiento (30%), nivel de efectividad (40%). El promedio de mitigadores por evento reduce el riesgo inherente al **Riesgo Residual**. Si el riesgo residual no es razonable, se requiere **plan de acción**.
4. **Monitoreo** — Seguimiento oportuno y permanente; **actualización** de la evaluación en un plazo no mayor a 12 meses (o antes, a criterio de la PO); **conservación** de evidencia y conclusiones, e informar al Oficial de Cumplimiento Designado ante la Superintendencia (ODS).

## 4. GERILAFT App (herramienta IVE)

Herramienta gratuita y opcional desarrollada por la IVE para automatizar el modelo GAFILAT, dirigida a PO sin capacidad adquisitiva para software de riesgos/AML. Disponible en el Portal de Personas Obligadas (PPO), Windows/macOS, con manual de usuario. Permite exportar/compartir un archivo **JSON** para atender requerimientos de información del regulador. Permite múltiples perfiles para distintas PO.

**Módulos operativos:**
- **Eventos** — Crear evento de riesgo; asignar probabilidad e impacto por tipo de riesgo asociado (Operacional, Legal, Reputacional, Contagio — el criterio "+" toma el valor predominante, no el promedio simple, cuando el riesgo legal es predominante); vincular controles mitigadores; validar riesgo residual; vincular plan de acción si el nivel residual es Medio Alto o Alto.
- **Controles** — Crear control (nombre + descripción); ingresar atributos (documentado, tipo: preventivo/detectivo/correctivo, ejecución: manual/semiautomático/automático, nivel de cumplimiento, nivel de efectividad — estos dos últimos definidos por la propia PO en su metodología); ponderación resultante 0-100 con semaforización. Requiere conservar evidencia de la evaluación (responsable y fecha).
- **Segmentación** — Definir factores → segmentos → variables (permite agregar variables nuevas); cada variable queda asociada a eventos de riesgo, con su riesgo inherente y residual visibles.
- **Plan de acción** — Medida propuesta, responsable, fecha de inicio/fin, % de avance; el módulo de Resultados muestra cuántos eventos están pendientes de plan de acción.

**Módulos administrativos:**
- **Resultados** — Panel de seguimiento: eventos sin control asignado, sin plan de acción, sin segmentar; controles sin evento vinculado; mapa de calor consolidado del riesgo inherente de la PO (probabilidad × impacto) con conteo de eventos por nivel.
- **Reportes** — Matriz de riesgo inherente y residual por factor (con iconografía por factor: clientes, productos/servicios, canales, ubicación, transaccional) y matriz consolidada a nivel de PO; resumen ejecutivo con resultado global de la gestión de riesgo (ej. "Adecuado").

## 5. Relevancia para Sovereign-AML

Ver análisis de integración en la conversación del 2026-07-27 (pendiente de convertir en historia técnica/backlog si se aprueba). Puntos centrales: el proyecto ya cuenta con scoring transaccional (IMPERATOR, `mod_matrices.py`) y catálogo de mitigación (`mod_mitigacion.py`), pero carece de un **módulo de Administración de Riesgo Institucional LD/FT** (nivel PO, no nivel cliente) que cubra Identificación→Medición→Control→Monitoreo conforme Art. 8-11 del Decreto 15-2026 y el modelo GAFILAT descrito arriba.
