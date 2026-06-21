import streamlit as st

def mostrar():
    st.markdown("""
    <div class="info-box">
        <strong>Manual de Prevención LD/FT/FPADM — Versión 3.1</strong> — Documentación técnica integrada de ejecución y uso. (Art. 12 Ley 6593)
        Explica el funcionamiento de cada módulo, el modelo de Scoring IMPERATOR (ISO 31000), la gestión de sesión y las capacidades de análisis transaccional.
    </div>
    """, unsafe_allow_html=True)

    st.markdown("""
    ## 1. Introducción
    SOVEREIGN AML es una solución integral de **Business Intelligence (BI)** y cumplimiento normativo, alineada con la **Iniciativa de Ley 6593** de Guatemala (*Ley Integral contra el Lavado de Dinero u Otros Activos y el Financiamiento del Terrorismo*) y las **40 Recomendaciones del GAFI**. La plataforma utiliza análisis de datos avanzado para transformar el monitoreo de riesgos en oportunidades estratégicas, integrando estándares internacionales: **ISO 31000**, **COSO ERM** y el enfoque basado en riesgo (**RBA**) del GAFI.

    ## 1.1. Marco Normativo y Tríada de Riesgo
    El motor **IMPERATOR** opera bajo una cuádruple referencia normativa:
    * **RBA (GAFI) — Núcleo Operativo:** Define *cómo se evalúa el riesgo*. Clasifica clientes y transacciones con enfoque proporcional.
    * **COSO ERM — Integración Estratégica:** Define *cómo se gobierna el riesgo*. Alinea detección de alertas con objetivos institucionales.
    * **ISO 31000 — Metodología Estructural:** Define *cómo se implementa*. Marco sistemático para identificar, analizar y tratar riesgos.
    * **Ley 6593 (Guatemala) — Trazabilidad IVE:** Provee la base legal nacional para los reportes RTS, RTE y el ciclo Inusual → Sospechosa.

    ### Dimensiones del Score IMPERATOR:
    1. **S_T (Riesgo Transaccional):** Reglas de detección — montos, picos, smurfing, frecuencia.
    2. **S_C (Riesgo Contextual):** Naturaleza del cliente — PEP, CPE, Ubicación de Riesgo, **Beneficiario Final (UBO)**.
    3. **S_B (Riesgo Conductual):** Desviaciones estadísticas sobre el perfil histórico del cliente.
    4. **S_N (Riesgo de Red):** Importancia del cliente en la red de flujos monetarios.

    ## 2. Requisitos del Archivo de Entrada
    Para un análisis completo, el archivo Excel (`.xlsx`) debe incluir las columnas base:
    * **Cliente**: Nombre o identificación del cliente origen.
    * **Monto**: Valor numérico de la operación.
    * **Perfil**: Límite de actividad mensual esperada.
    * **Fecha**: Fecha de registro (YYYY-MM-DD).
    * **EsPEP / EsCPE**: (Booleanos) Persona Expuesta Políticamente o Contratista/Proveedor del Estado.
    * **TipoOperacion**: Canal usado (Transferencia, Efectivo, etc.).
    * **Cliente_Destino**: (Requerido para Red Transaccional) Receptor de los fondos.

    ### Columnas opcionales para cumplimiento Ley 6593:
    * **Tipo_Instrumento**: Instrumento de pago (Efectivo, Transferencia, Cheque…). Activa la detección automática de **RTE** (Art. 31) cuando el valor es `EFECTIVO` y el monto ≥ USD 10,000.
    * **Beneficiario_Final / EsPEP_UBO / Porcentaje_Participacion**: Datos del titular real (UBO). Activan penalización de SC y alerta de DDA Obligatoria (Art. 21 Ley 6593 / GAFI Rec. 12).
    * **Tipo_Cliente**: Categoría jurídica del cliente — `Persona Individual`, `Persona Jurídica`, `Estructura Jurídica` (Art. 3 Ley 6593).
    * **EsFPADM**: (Booleano) Marca al cliente con riesgo de Financiamiento de Proliferación de Armas de Destrucción Masiva. Activa la acción **R-03** (GAFI Rec. 7 / Art. 2 Ley 6593).

    ## 2.1. Inicio, Sesión y Persistencia Temporal
    La plataforma mantiene una sesión operativa diseñada para reducir fricción sin comprometer el control:
    * **Cierre por inactividad:** Si el usuario no interactúa durante 30 minutos, la sesión se cierra automáticamente.
    * **Recarga accidental:** Si la página se refresca antes de que expire la sesión, el sistema restaura el acceso sin solicitar nuevamente credenciales.
    * **Análisis temporal:** El Excel cargado se conserva en caché temporal. Al refrescar la vista, el análisis se restaura sin volver a subir el archivo.
    * **Limpieza segura:** Al cerrar sesión, iniciar un nuevo análisis o expirar por inactividad, la caché temporal se elimina.
    * **Sesiones guardadas (.saml):** El usuario puede exportar una sesión `.saml` para retomarla manualmente en sesiones futuras.
    * **Auditoría de accesos (Art. 19 Ley 6593):** Cada acceso a módulos sensibles queda registrado en la bitácora de sesión (`auditoria_sesion`).

    ## 3. Ciclo de Vida de Alertas — Inusual → Sospechosa (Arts. 28-30 Ley 6593)
    El módulo **Casos de Alerta** implementa el flujo legal de dos fases:

    | Estado | Significado |
    |--------|-------------|
    | `Inusual_Pendiente` | Detectado por IMPERATOR, pendiente de revisión del analista |
    | `Inusual_Examinada` | Analista revisó y descartó escalamiento |
    | `Sospechosa_Confirmada` | Analista confirmó — **requiere RTS ante la IVE (Art. 30)** |
    | `Descartada` | Falso positivo documentado |

    El analista selecciona el caso, registra el **Fundamento del Examen** (Art. 29) y guarda la clasificación. Al marcar `Sospechosa_Confirmada`, el sistema activa el generador de **RTS** en el módulo de Reportes.

    ## 4. Reportes Regulatorios IVE (Ley 6593)
    El módulo **Reportes** incluye una pestaña dedicada **RTS / RTE — IVE**:

    * **RTS — Reporte de Transacción Sospechosa (Art. 30):** Se genera para casos clasificados como `Sospechosa_Confirmada`. Incluye datos del sujeto obligado, cliente, score IMPERATOR y fundamento del examen. Formato compatible con la IVE-SIB.
    * **RTE — Reporte de Transacción en Efectivo (Art. 31):** Se genera automáticamente para transacciones con `Tipo_Instrumento = EFECTIVO` y `Monto ≥ USD 10,000`. El sistema alerta en el módulo de Transacciones cuando existen casos pendientes.

    ## 5. Inteligencia de Red Transaccional
    El módulo de **Red Transaccional** visualiza el flujo de capital mediante grafos. Patrones detectados:
    * **Layering (Estratificación LD/FT/FPADM):** Rutas "Multi-Hop" donde el dinero pasa por múltiples intermediarios.
    * **Cuentas Puente:** Nodos con alta "Centralidad de Intermediación" (posible triangulación de fondos).
    * **Ciclos:** Flujos circulares donde el dinero regresa al origen.
    * **Trazabilidad tabular:** Tablas de relaciones, rutas y centralidad en render HTML nítido.

    ## 5.1. Imperator Diagnostics
    * **Dominancia de reglas:** ¿Alguna regla genera exceso de alertas?
    * **Explicabilidad:** Composición del score por pilares S_T, S_C, S_B y S_N.
    * **Falsos positivos:** Ruido analítico en clientes de bajo riesgo.
    * **Pruebas de estrés:** Simula cambios de parámetros antes de aplicarlos.
    * **Densidad de riesgo:** Concentración del riesgo en la cartera.

    ## 6. Acciones de Mitigación (RBA / GAFI / ISO 31000)
    El sistema asigna automáticamente acciones proporcionales al nivel de alerta:
    * **Preventivas (P):** Bloqueo temporal (P-01), Rechazo de operación (P-02), Limitación de montos (P-03).
    * **Correctivas (C):** DDA Ampliada (C-01), Documentación (C-02), Revisión manual (C-03).
    * **Regulatorias (R):**
        * **R-01** — Generación de RTS (GAFI Rec. 20 / Art. 30 Ley 6593)
        * **R-02** — Escalamiento a Cumplimiento (ISO 31000 §6.6)
        * **R-03** — Verificación sanciones FPADM / proliferación (GAFI Rec. 7 / Art. 2 Ley 6593) — se activa en nivel Crítico o cuando `EsFPADM = True`
    * **Estratégicas (E):** Ajuste de perfil (E-01), Reclasificación de segmento (E-02), Restricción de productos (E-03).
    * **Formularios KYC (F):** Actualización de FEIS a FEIC (F-01 / GAFI Rec. 10).

    ## 7. Motor de Reglas de Detección
    1. **Monto Alto (Alerta_Absoluto):** Supera umbrales individuales configurados.
    2. **Acumulado (Alerta_Acumulado):** Total mensual excede el multiplicador del perfil.
    3. **Desviación de Perfil (Alerta_15):** Monto supera el porcentaje de tolerancia del perfil esperado.
    4. **Smurfing / Pitufeo:** Múltiples operaciones pequeñas en ventanas cortas de tiempo.
    5. **Pico Anómalo:** Salto estadístico sobre la media histórica del cliente (+2 Std).
    6. **Frecuencia (Alerta_Frecuencia):** Densidad operativa superior al umbral.
    7. **Geografía de Riesgo:** Operaciones en zonas fronterizas o de alta sensibilidad.

    ## 8. Clasificación y Umbrales
    * **Crítico (Score ≥ umbral configurado):** Acción inmediata (P-01 + R-01 + R-03). Bloqueo y generación de RTS.
    * **Alto (Score intermedio):** Investigación EDD mandatoria. RTS si hay smurfing o pico.
    * **Medio:** Vigilancia reforzada. Revisión manual (C-03).
    * **Bajo:** Sin alertas críticas. Diligencia estándar.

    ## 9. Beneficiario Final (UBO) — Art. 21 Ley 6593
    El módulo **Análisis por Cliente** incluye un panel expandible de **Beneficiario Final (UBO)**:
    * Muestra el nombre del titular real, porcentaje de participación y fuente de verificación.
    * Si el UBO tiene perfil PEP (`EsPEP_UBO = True`), se activa una alerta de **DDA Obligatoria** (GAFI Rec. 12 / Art. 25a Ley 6593) y se aplica un incremento al Score Contextual (S_C).
    * Tipos de cliente soportados: `Persona Individual`, `Persona Jurídica`, `Estructura Jurídica` (trusts, fundaciones).
    * Personas Obligadas incluyen: Bancos, Cooperativas, Casas de Cambio, Aseguradoras, Emisoras de Tarjetas y **PSAV** (Proveedores de Servicios de Activos Virtuales — Art. 3 c)1 vii) Ley 6593).

    ## 10. Retención de Datos — Art. 34 Ley 6593
    La plataforma fuerza un **mínimo de 5 años** de retención de registros. Esta política está visible y configurable en el módulo de **Configuración** (sección Política de Retención de Datos):
    * La retención mínima legal es **5 años** (no reducible).
    * La institución puede configurar un período mayor (hasta 20 años).
    * La función `_validar_retencion()` bloquea la eliminación de registros que aún están dentro del período obligatorio.

    ## 11. KPIs de Cumplimiento en el Resumen Ejecutivo
    El **Resumen Ejecutivo** incluye dos indicadores de gestión de casos (Arts. 28-30 Ley 6593):
    * **Inusuales pendientes de examen:** Transacciones detectadas por IMPERATOR sin clasificación del analista.
    * **Sospechosas sin RTS generado:** Casos confirmados que requieren envío urgente del RTS a la IVE.
    Un indicador en rojo aparece cuando hay sospechosas sin resolver.

    ## 12. Guía de Uso Estratégico
    1. **Resumen Ejecutivo:** Revise los KPIs de alerta y distribución PEP/CPE para priorizar la jornada.
    2. **Casos de Alerta:** Clasifique cada caso (Inusual → Sospechosa → Descartada) y registre el fundamento.
    3. **Transacciones:** Identifique los RTE pendientes (efectivo ≥ USD 10,000) con la columna `RTE (Art.31)`.
    4. **Análisis de Red:** Use filtros de Enfoque y Hops para rastrear la ruta del dinero en esquemas LD/FT/FPADM.
    5. **Mitigación:** Consulte las acciones R-01, R-02 y R-03 para saber qué reporte corresponde por norma.
    6. **Reportes → RTS/RTE:** Genere el PDF formal para la IVE directamente desde la plataforma.
    7. **Diagnostics:** Calibre reglas y umbrales antes de cerrar el período de análisis.
    8. **Configuración:** Ajuste parámetros y verifique la política de retención de datos.

    ## 13. Recomendaciones de Seguridad Operativa (OWASP / Art. 19 Ley 6593)
    * Cierre sesión al terminar el análisis, especialmente en equipos compartidos.
    * Use la exportación `.saml` solo cuando necesite conservar el análisis fuera de la sesión.
    * Proteja los archivos `.saml`; contienen transacciones originales y configuración.
    * Los `Fundamento_Examen` y datos UBO son campos sensibles — trátelos con confidencialidad.
    * El acceso a módulos de Reportes y Alertas queda registrado en la bitácora de sesión.
    * Revise periódicamente dependencias del entorno Python y mantenga versiones fijadas.

    ---
    **SOVEREIGN AML v3.1 — Adecuado a Ley 6593 / GAFI 40 Recomendaciones**
    *Ing. Hobéd Díaz — Msc. M.A.F.I | 2026*
    """)
