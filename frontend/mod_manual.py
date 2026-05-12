import streamlit as st

def mostrar():
    st.markdown("""
    <div class="info-box">
        <strong>Manual de Usuario — Versión 3.0</strong> — Documentación técnica integrada de ejecución y uso.
        Explica el funcionamiento de cada módulo, el modelo de Scoring IMPERATOR (ISO 31000) y las nuevas capacidades de Red Transaccional y Mitigación.
    </div>
    """, unsafe_allow_html=True)

    st.markdown("""
    ## 1. Introducción
    SOVEREIGN AML es una solución integral de **Business Intelligence (BI)** y cumplimiento normativo. A diferencia de las herramientas reactivas tradicionales, esta plataforma utiliza análisis de datos avanzado para transformar el monitoreo de riesgos en **oportunidades estratégicas de negocio**, integrando estándares internacionales de gestión de riesgos como **ISO 31000** y el enfoque basado en riesgo (**RBA**) del **GAFI**.

    ## 1.1. Marco Normativo y Tríada de Riesgo
    El motor **IMPERATOR** opera bajo una estructura de cumplimiento moderno basada en tres pilares fundamentales:
    * **RBA (GAFI) — Núcleo Operativo:** Define *cómo se evalúa el riesgo*. Es la base para clasificar clientes y transacciones mediante un Enfoque Basado en Riesgo.
    * **COSO ERM — Integración Estratégica:** Define *cómo se gobierna el riesgo*. Alinea la detección de alertas con los objetivos de negocio y la estrategia institucional.
    * **ISO 31000 — Metodología Estructural:** Define *cómo se implementa*. Proporciona el marco sistemático para identificar, analizar y tratar los riesgos detectados.

    Este rediseño v3.0 asegura que cada score generado tenga un respaldo metodológico internacional sólido.

    ### Dimensiones del Score IMPERATOR:
    1. **S_T (Riesgo Transaccional):** Basado en reglas de detección (montos, picos, smurfing).
    2. **S_C (Riesgo Contextual):** Evalúa la naturaleza del cliente (PEP, CPE, Ubicación).
    3. **S_B (Riesgo Conductual):** Mide desviaciones estadísticas respecto al perfil histórico del cliente.
    4. **S_N (Riesgo de Red):** Analiza la importancia del cliente dentro de la red de flujos monetarios.

    ## 2. Requisitos del Archivo de Entrada
    Para un análisis completo, el archivo Excel (`.xlsx`) debe incluir:
    * **Cliente**: Nombre o identificación del cliente origen.
    * **Monto**: Valor numérico de la operación.
    * **Perfil**: Límite de actividad mensual esperada.
    * **Fecha**: Fecha de registro (YYYY-MM-DD).
    * **EsPEP / EsCPE**: (Boleanos/Texto) Indica si es Persona Expuesta Políticamente o Contratista/Proveedor del Estado.
    * **TipoOperacion**: Canal usado (Transferencia, Efectivo, etc.).
    * **Cliente_Destino**: (Requerido para Red Transaccional) Identifica quién recibe los fondos.

    ## 3. Inteligencia de Red Transaccional
    El nuevo módulo de **Red Transaccional** permite visualizar el flujo de capital mediante grafos:
    * **Identificación de Estratificación (Layering):** Detecta automáticamente rutas "Multi-Hop" donde el dinero pasa por varios intermediarios antes de llegar a un destino final.
    * **Cuentas Puente:** Identifica nodos con alta "Centralidad de Intermediación" que podrían estar siendo usados para triangular fondos.
    * **Detección de Ciclos:** Localiza flujos circulares donde el dinero regresa al origen, señal común de esquemas de lavado.

    ## 4. Gestión de Acciones de Mitigación
    Basado en el **RBA (Risk-Based Approach)**, el sistema asigna automáticamente acciones según el nivel de alerta:
    * **Preventivas:** Bloqueos temporales o rechazos ante riesgos críticos inmediatos.
    * **Correctivas:** Requerimiento de Debida Diligencia Ampliada (EDD) y documentos de soporte.
    * **Regulatorias:** Generación de reportes obligatorios (ROS/SAR) ante la entidad reguladora.
    * **Estratégicas:** Ajustes preventivos en la segmentación y perfil del cliente.

    ## 5. Motor de Reglas de Detección
    El sistema mantiene sus reglas core para alimentar el score transaccional:
    1. **Monto Alto**: Supera umbrales individuales.
    2. **Acumulado**: El total mensual excede el perfil permitido.
    3. **Smurfing (Pitufeo)**: Multiplicidad de operaciones pequeñas en ventanas cortas de tiempo.
    4. **Pico Anómalo**: Salto estadístico inusual sobre la media del cliente.
    5. **Geografía de Riesgo**: Operaciones en zonas fronterizas o de alta sensibilidad.

    ## 6. Clasificación y Umbrales
    * **Crítico (Score ≥ 8.0)**: Requiere acción inmediata (P-01/R-01). Bloqueo y reporte.
    * **Alto (Score 5.0 - 7.9)**: Requiere investigación EDD mandatoria.
    * **Medio (Score 3.0 - 4.9)**: Vigilancia reforzada.
    * **Bajo (Score < 3.0)**: Sin alertas críticas detectadas.

    ## 7. Guía de Uso Estratégico
    1. **Resumen Ejecutivo**: Observe la distribución de asociados PEP/CPE para entender la exposición política de la cartera.
    2. **Análisis de Red**: Use los filtros de **Enfoque** y **Saltos (Hops)** para limpiar el mapa y seguir la ruta del dinero de un cliente sospechoso.
    3. **Protocolo de Mitigación**: Consulte el módulo de acciones para saber exactamente qué medida aplicar según la normativa internacional.
    4. **Configuración**: Personalice los umbrales de acuerdo con las políticas internas de cumplimiento de su institución.

    ---
    **SOVEREIGN AML v3.0 (Analytical Intelligence Platform)**  
    *Ing. Hobéd Díaz — Msc. M.A.F.I*
    """)
