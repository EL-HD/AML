import streamlit as st

def mostrar():
    st.markdown("""
    <div class="info-box">
        <strong>Manual de Usuario</strong> — Documentación técnica integrada de ejecución y uso.
        Explica el funcionamiento de cada módulo, reglas, y la fórmula de Scoring de la plataforma AML.
    </div>
    """, unsafe_allow_html=True)

    st.markdown("""
    ## 1. Introducción
    AML Intelligence Platform es una solución integral de **Business Intelligence (BI)** y cumplimiento normativo. A diferencia de las herramientas reactivas tradicionales, esta plataforma utiliza análisis de datos avanzado para transformar el monitoreo de riesgos en **oportunidades estratégicas de negocio**, permitiendo identificar tendencias de mercado y proyecciones de crecimiento mientras se mantiene una postura de seguridad impecable.

    ## 1.1. ¿Qué es IMPERATOR?
    **IMPERATOR** es el motor de análisis de **SOVEREIGN AML**. Es la capa central que ejecuta las reglas, calcula el score de riesgo, consolida señales de alerta, clasifica clientes y produce la lógica analítica que alimenta tableros, matrices, reportes y expedientes.

    En términos simples:
    * **SOVEREIGN AML** es la plataforma completa.
    * **IMPERATOR** es el motor analítico que interpreta los datos y convierte transacciones en inteligencia operativa.

    ## 2. Requisitos del Archivo de Entrada
    La plataforma requiere un archivo Excel (`.xlsx`) con las siguientes columnas obligatorias:
    * **Cliente**: Identificador único del cliente (Texto / ID).
    * **Monto**: Monto de la transacción en quetzales (Numérico).
    * **Perfil**: Límite esperado de actividad del cliente (Numérico).
    * **Fecha**: Fecha de la transacción (Formato compatible con pandas, ej. YYYY-MM-DD).
    * **TipoOperacion**: (Opcional pero recomendado) Canal o medio usado (e.g., Transferencia, Efectivo).

    ## 3. Inteligencia Estratégica y BI
    La plataforma incluye un motor de **Business Intelligence** en tiempo real:
    * **Cuadros de Interpretación**: Todas las gráficas incluyen un bloque descriptivo que explica el valor del dato para la toma de decisiones.
    * **Matriz de Oportunidad**: Cruza el *Volumen Económico* vs. *Alcance de Clientes*. Identifica **Canales de Alto Rendimiento** (Bajo riesgo, alto flujo) ideales para expansión comercial.
    * **Densidad de Riesgo Agrupada**: Visualización side-by-side que compara la concentración de niveles Crítico/Alto entre canales para priorizar auditorías.
    * **Proyección de Tendencias**: Genera sugerencias dinámicas de productos (Banca VIP, Micro-créditos, Seguros) basadas en el ticket promedio y volumen por canal.

    ## 4. Motor de Reglas AML
    El sistema evalúa 6 reglas independientes sobre cada transacción:
    1. **Monto Alto Absoluto**: Supera el umbral configurado (ej. Q20,000).
    2. **Acumulado Mensual**: Total período > Perfil × Factor.
    3. **Exceso sobre Perfil**: Operación individual > Perfil × Factor.
    4. **Frecuencia Alta**: Conteo de transacciones inusual.
    5. **Smurfing (pitufeo)**: >5 ingresos fraccionados en el mismo día.
    6. **Pico Anómalo**: Anomalías estadísticas (Media + n Desviaciones Estándar).

    ## 5. Clasificación de Riesgo por Cliente
    * **Crítico** (Foco en Seguridad): Score_Max >= 8 o Volumen masivo. Requiere un RTS a la SIB (mediante la IVE).
    * **Alto** (Investigación Mandatoria): Score_Max >= 5. Requiere Debida Diligencia Ampliada (EDD).
    * **Medio** (Vigilancia Reforzada): Score_Max >= 3. Monitoreo regular.
    * **Bajo** (Operación Estándar): Actividad alineada al perfil.

    ## 6. Guía de Uso Estratégico
    1. **Resumen Ejecutivo**: Revise la **Salud de Cartera** y los **Insights de BI** para detectar tendencias de crecimiento.
    2. **Optimización de Canales**: Use la Matriz de Oportunidad para decidir en qué canales lanzar nuevos productos o dónde fortalecer la seguridad física (si predomina el efectivo).
    3. **Auditoría Específica**: Use *Análisis por Cliente* para ver tendencias temporales y picos estadísticos antes de generar el reporte final.
    4. **Sintonía Fina**: Ajuste pesos y umbrales en *Configuración* para reducir falsos positivos según el apetito de riesgo institucional.

    ---
    **AML Intelligence Platform v2.5 (BI Edition)**  
    *Ing. Hobéd Díaz — Msc. M.A.F.I*
    """)
