# Oficio IVE Núm. 19-2025: Nuevo mecanismo de envío del RTS

**Fuente:** `_FIRMADO_OF.19.2025.0.000.pdf` + `Anexo 1` (23 hojas) + `Anexo 2` (36 hojas): analizado 2026-07-29
**Emisor:** Intendencia de Verificación Especial (IVE), Superintendencia de Bancos, Guatemala
**Vigencia:** Obligatorio desde el 3 de julio de 2025 (reemplaza el mecanismo anterior de "e-RTS" y el formulario electrónico previo, dejando sin efecto 18 oficios IVE anteriores sobre el tema).
**Canal de envío:** **Portal Personas Obligadas (PPO)**: plataforma web de la IVE. No se describe una API/webservice de integración directa; el envío del detalle transaccional es mediante **carga manual de un archivo CSV** al portal, no JSON.

## 1. Estructura del RTS: 4 módulos (Anexo 1)

**Módulo 1: Información general del RTS** (mayormente derivable del caso ya trabajado en el sistema)
Código/Nombre PO (auto), fecha de detección de la transacción inusual, fecha de conocimiento del Oficial de Cumplimiento, tipo de reporte (Lavado de dinero / Financiamiento del terrorismo), fecha de creación del RTS, número de reporte (auto, formato `BA000-0001-2025`), jurisdicción origen/destino (Nacional/Extranjera/Mixta), período reportado (fecha inicial/final: si excede 90 días calendario o la confirmación tarda más de 45 días desde el cierre del período, requiere justificación), monto de la transacción sospechosa.

**Módulo 2: Personas involucradas, productos y servicios analizados**
- *Personas involucradas*: se nutre del **FEIC** (Formulario Electrónico de Información del Cliente) ya verificado por la PO: identificación, tipo de persona, motivo de involucramiento (titular/firmante/representante/beneficiario de fondos/etc.), fecha nacimiento/constitución, OFAC, ONU, PEP, CPE, **Beneficiario Final** (con medida de identificación: participación de propiedad / control / administración) y carga de archivos de verificación (RENAP, escrituras, etc.).
- *Productos o servicios analizados*: identificador, tipo (catálogo oficial), moneda, estado, fecha de cancelación, saldo, carga de archivos (expediente de cuenta, contratos), y carga del **Estado de Cuenta** en la estructura instruida por la IVE.
- Excepcionalmente permite carga manual cuando no se puede vincular vía FEIC.

**Módulo 3: Descripción del RTS** (100% narrativo/cualitativo)
Resumen de la transacción sospechosa (texto libre, admite **Palabras Clave** con sintaxis `||*[palabra_clave]`), especificaciones cualitativas (transacción no concluida, relación con publicación en medios, involucra fondos públicos, involucra activos virtuales, relación con amenaza interna/externa), listado de **Señales de Alerta** (enunciado + descripción detallada de cada hallazgo) y carga de archivos de respaldo (informe ampliado, opcional si el detalle en el sistema ya es suficiente).

**Módulo 4: Detalle transaccional** (el más técnico: formato **CSV**, campos fijos, sin JSON)
Dos modalidades según tipo de PO:
- **DTE (Detalle Transaccional Estructurado)**: obligatorio para **Grupo 1** (bancos excepto BANGUAT, sociedades financieras, offshore, emisores/operadores de tarjeta de crédito) y **Grupo 2** (BANGUAT, cooperativas de ahorro y crédito, empresas de transferencias de fondos). Columnas fijas, no se pueden agregar/quitar.
- **DTA (Detalle Transaccional Adaptativo)**: obligatorio para el resto de PO ("Otras PO"); tiene un núcleo de "Estructurados Mínimos" + columnas "Adaptativas" opcionales.

Por cada transacción (~13 campos): tipo (ingreso/egreso), identificación, fecha, hora, canal (código + tipo + nombre: catálogo AGE/AGT/MOV/WEB/BIL/CAJ/CEE/POS/OTR), latitud/longitud, municipio/departamento/país, descripción, monto.

Por cada integración de esa transacción (~15 campos): instrumento (catálogo ACT/CHG/EFE/GIR/TPF/TPD/TIN/TFB/TFI/OTR), identificación de la integración, tipo de producto/servicio de la contraparte, identificador de origen/destino, titular, nombre de la entidad financiera contraparte, ubicación, moneda, monto de respaldo, monto, monto equivalente en la moneda del producto analizado, observación.

**Validación cruzada obligatoria:** la suma de los "montos de integración en moneda del producto analizado" debe ser igual al "monto de la transacción" correspondiente.

## 2. Catálogos oficiales referenciados (Anexo 2, hojas 11-36)

Tipo de canal (9 valores), tipo de producto o servicio (10 valores), tipo de instrumento (10 valores), 22 departamentos y sus municipios (cientos de registros), catálogo de países, catálogo de moneda. No se transcriben aquí en su totalidad: ver el PDF fuente para el listado completo; son tablas de referencia estáticas, ideales para precargar como catálogos internos del sistema.

## 3. Reglas operativas relevantes

- **Ampliación de RTS**: se permite ampliar un RTS ya enviado (agregar info faltante) sin extender el período, transacciones, involucrados o productos ya reportados; si se excede ese alcance, debe enviarse un **nuevo RTS**.
- **Confidencialidad (tipping-off)**: prohibido revelar al cliente, directa o indirectamente, que se generó o notificó un RTS (alineado a Recomendaciones GAFI).
- Las PO deben conservar todos los registros físicos/digitales que respalden transacciones e integraciones reportadas, a disposición de la IVE.

## 4. Relevancia para Sovereign AML

El instructivo confirma que **no existe hoy una integración API/JSON con la IVE**: el mecanismo es un portal web con carga de CSV y formularios. Esto reduce el alcance real de "integración" a: (a) generar un CSV con el formato exacto del Anexo 2, y (b) capturar dentro del sistema los datos de los Módulos 1-3 que hoy no existen (FEIC completo, productos/servicios del cliente, señales de alerta estructuradas). Ver propuesta de captura en [`PROPUESTA-Captura-Datos-RTS.md`](PROPUESTA-Captura-Datos-RTS.md).
