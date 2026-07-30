# Propuesta: captura de datos para el RTS (Oficio IVE 19-2025)

**Contexto:** análisis de `Oficio-IVE-19-2025-RTS.md`. Objetivo: definir cómo capturar, dentro de Sovereign AML, la información que exigen los Módulos 1-4 del RTS **sin** pedirla en el Excel de transacciones (es demasiada información y no aplica a todas las transacciones).

## 0. Hallazgo importante antes de la propuesta

El instructivo **no pide un JSON ni una API**: el Módulo 4 (detalle transaccional) se envía como **archivo CSV** cargado manualmente en el Portal Personas Obligadas; los Módulos 1-3 se llenan en formularios web del mismo portal. Es decir, el trabajo real de Sovereign AML no es "integrarse" con la IVE, sino **generar un CSV con el formato exacto del Anexo 2** más un narrativo (Módulo 3): algo mucho más acotado que una integración API. Esto no cambia la decisión de dejarlo en **BETA** por ahora (aún no se ha empezado), pero sí cambia el tamaño real del esfuerzo: es alcanzable, no hay que "esperar a ver si la IVE publica un webservice".

## 1. Principio de diseño: captura progresiva, no retroactiva

No se debe pedir información FEIC/producto/canal para el 100% de clientes y transacciones: eso resucita el problema de "demasiada info". Se pide **solo cuando un caso pasa a `Sospechosa_Confirmada`** (el punto en el que hoy el sistema ya avisa "requiere RTS ante la IVE", en `mod_alertas.py` / `mod_resumen.py`). En la práctica esto son pocos casos al mes, no miles de transacciones.

## 2. Diagnóstico: qué existe hoy vs. qué exige el RTS

| Módulo RTS | Dato exigido | ¿Existe en Sovereign hoy? | Gap |
|---|---|---|---|
| 1: Información general | Fechas, tipo de reporte, período, monto | Se deriva del caso/alerta ya clasificado | Ninguno: es 100% autogenerable |
| 2: Personas involucradas | Identificación, PEP/CPE, Beneficiario Final | Parcial: `mod_cliente.py` ya tiene PEP/CPE y UBO | Faltan: OFAC/ONU, fecha nacimiento/constitución, motivo de involucramiento, carga de archivos de verificación |
| 2: Productos y servicios | Identificador, tipo, moneda, estado, saldo | No existe como catálogo propio del cliente | Gap completo: es justo lo que no está en el Excel |
| 3: Descripción | Resumen narrativo, señales de alerta | Parcial: `mod_reportes.py` ya redacta narrativa en el PDF | Falta modelarlo como campos estructurados reutilizables (no solo texto libre en el PDF) |
| 4: Detalle transaccional | Canal, geolocalización, instrumento, contraparte | Parcial: fecha/monto/tipo ya están en el Excel importado | Gap principal: canal, instrumento e integración no existen en ningún lado hoy |

## 3. Qué construir (3 piezas de datos + 1 flujo guiado)

**a) Extensión de Ficha de Cliente: "Datos FEIC complementarios"**
Un bloque adicional, opcional, en `mod_cliente.py`, que solo se marca como obligatorio cuando el cliente queda vinculado a un caso `Sospechosa_Confirmada`. Campos nuevos: OFAC (sí/no), ONU (sí/no), fecha nacimiento/constitución, lugar, nacionalidad/país de constitución, motivo de involucramiento (catálogo: titular/firmante/representante legal/beneficiario de fondos/otro), y carga de archivo de verificación.

**b) Catálogo "Productos y Servicios del Cliente"**
Tabla nueva (`ClienteProductoServicio`), un registro por producto que el cliente tiene con la PO (cuenta, tarjeta, póliza, etc.), independiente de las transacciones. Campos: identificador, tipo (catálogo oficial del Anexo 2), moneda, estado, saldo, archivo de respaldo. Se llena una vez por producto, no por transacción: bajo volumen.

**c) Detalle de canal e integración: solo para transacciones incluidas en un RTS**
Tabla nueva (`TransaccionRTSDetalle`) vinculada 1:1 a las transacciones que el analista selecciona para el reporte (no todas las transacciones del Excel). Fecha/hora/monto/tipo se copian automáticamente de la transacción ya importada; lo que se pide manualmente es: canal (catálogo), latitud/longitud, municipio/departamento/país, instrumento de integración, contraparte (titular, entidad financiera), montos de integración. El sistema valida en vivo que la suma de integración cuadre con el monto de la transacción (regla obligatoria del instructivo).

**d) Módulo 3 estructurado: Señales de Alerta**
En vez de un solo campo de texto libre, una lista repetible (enunciado + descripción), reutilizando el patrón ya usado en `mod_riesgo_ldft.py` para eventos/controles. El resumen narrativo sigue siendo texto libre, con soporte para insertar palabras clave `||*[palabra_clave]` si la IVE las comunica.

## 4. Flujo propuesto: asistente "Preparar RTS" (wizard)

Se activa desde `mod_alertas.py` cuando un caso pasa a `Sospechosa_Confirmada`: no antes.

1. **Información general** (automático): se muestra para revisión, no se vuelve a capturar.
2. **Personas involucradas**: lista los clientes ya vinculados al caso; por cada uno, si falta algún campo FEIC complementario, lo pide ahí mismo (no antes).
3. **Productos y servicios**: selecciona del catálogo de productos del cliente (punto 3b); si falta uno, se agrega en el momento.
4. **Descripción**: redacta resumen y señales de alerta (punto 3d).
5. **Detalle transaccional**: lista las transacciones candidatas (ya filtradas por el caso), el analista marca cuáles van al reporte y completa canal/instrumento/integración de cada una (punto 3c). Autocompletado de fecha/monto/tipo.
6. **Validación y exportación**: el sistema valida montos, fechas y campos obligatorios según el Grupo de PO (1, 2 u Otras: un dato de configuración a definir una sola vez), y genera dos archivos: el PDF narrativo (ya existe) y el CSV DTE/DTA con el formato exacto del Anexo 2, listo para subir manualmente al Portal Personas Obligadas.

## 5. Fases sugeridas de entrega

| Fase | Contenido | Esfuerzo | Valor |
|---|---|---|---|
| A | Módulo 3 estructurado (señales de alerta como lista + resumen) | Bajo: ya existe la base narrativa en `mod_reportes.py` | Alto: mejora inmediata de lo que hoy se redacta a mano |
| B | Catálogo de Productos y Servicios por cliente + campos FEIC complementarios bajo demanda | Medio | Alto: cierra el gap de "no va en el Excel" |
| C | Detalle transaccional + integración (wizard paso 5) + validación cruzada | Alto: es el módulo más granular | Medio-alto, pero es el corazón del CSV DTE/DTA |
| D | Exportación CSV DTE/DTA con catálogos oficiales embebidos, validado contra Anexo 2 | Medio (depende de C) | Es el entregable final que se sube al portal |

Con A+B ya se cubre casi todo lo narrativo y de personas/productos. C+D es lo que decide si realmente "se llega" a la exportación completa: pero al no ser una integración API sino un CSV con reglas fijas, es un alcance medible y acotado, no un desarrollo abierto.

## 6. Seguridad (OWASP)

Los nuevos datos (identificaciones, PEP, beneficiario final, geolocalización) son altamente sensibles y CONFIDENCIALES por instrucción expresa de la IVE (prohibición de tipping-off). Aplican los mismos controles ya vigentes en el proyecto: filtrado estricto por `licenciaid` (A01), sin exponer si un cliente tiene un RTS en curso a roles sin permiso explícito, registro en `BitacoraAuditoria` de cada acceso/edición a estos módulos (A09), y carga de archivos con validación de tipo/tamaño (A03/A05) dado que se subirán documentos de verificación (RENAP, escrituras).
