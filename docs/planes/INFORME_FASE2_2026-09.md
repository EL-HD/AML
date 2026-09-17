# Informe de Ejecución: Fase 2 Cumplimiento, Seguridad y Analítica · Sovereign AML

**Plan de referencia:** `docs/planes/PLAN_FASE2_2026-09.md` · **Rama:** `mejora/fase2-cumplimiento-2026-09` (sin push, sin merge).
Cada tarea añade su sección al terminar (estado, commit, evidencia, variables nuevas y pasos de despliegue).

---

## T1 Persistencia de casos (Art. 29, 30 y 34 Ley 6593)

**Estado:** HECHO · **Fecha:** 17/09/2026 · **Commit:** `fbab9e9` (código) y el commit de este informe.

### Qué se hizo
- **Modelo de datos** (`backend/models.py`, `migrations/004_casos_alerta.sql`):
  - `public."CasosAlerta"`: estado vigente por caso con `licenciaid`, `clave_caso`, `hash_lote`, `cliente`, `nombre_archivo`, `estado` (CHECK con los cinco estados), `fundamento`, `score_max`, `nivel_riesgo`, `propuesto_por/en`, `aprobado_por/en`, `fecha_clasificacion_sospechosa`, trazas de creación y actualización. `UNIQUE (licenciaid, clave_caso)` e índice `(licenciaid, hash_lote)`.
  - `public."CasosAlertaHistorial"`: historial append-only de transiciones (`estado_anterior`, `estado_nuevo`, `accion`, `fundamento`, `usuario`, `rol`, `registrado_en`), con FK a `CasosAlerta`.
  - Retención (Art. 34): triggers PostgreSQL que rechazan `DELETE` en ambas tablas y `UPDATE` en el historial; en el ORM, listeners `before_delete`/`before_update` lanzan `HistorialInmutableError` (también efectivos en SQLite). No existe ninguna función ni control de UI que borre casos.
  - La migración es idempotente (`IF NOT EXISTS`, `CREATE OR REPLACE FUNCTION`, `DROP TRIGGER IF EXISTS`) y los nombres de índice coinciden con los que genera `create_all`, por lo que la ruta real de `scripts/db_migrate.py` (ORM primero, SQL después) no crea índices duplicados.
- **Clave estable del caso** (documentada en `backend/casos_alerta.py` y en la cabecera de la migración):
  - `hash_lote` = SHA-256 del lote canónico de transacciones (columnas ordenadas, filas ordenadas, todo como texto, CSV UTF-8). No depende del nombre del archivo ni del orden de filas.
  - `clave_caso` = SHA-256 de `licenciaid|hash_lote|cliente_normalizado` (cliente recortado, sin espacios repetidos, en mayúsculas).
  - El hash se calcula una vez por lote cargado y se memoriza en la sesión (`frontend/casos_persistencia.py`); se olvida con "Nuevo análisis".
- **Flujo de cuatro ojos** (`backend/casos_alerta.py`, tabla `TRANSICIONES`):
  - Roles operativos (admin, oficial, analista) examinan, descartan o proponen `Sospechosa_Propuesta` (nuevo estado intermedio) con fundamento obligatorio (mínimo 10 caracteres, Art. 29).
  - Solo admin u oficial aprueban `Sospechosa_Confirmada`, y nunca quien propuso (comparación de usuario normalizado). `Sospechosa_Confirmada` es terminal; el RTS se emite en Reportes.
  - Una propuesta puede retirarla el proponente o rechazarla un oficial/admin. El auditor solo observa.
  - `permisos.py`: acciones nuevas `proponer_caso_sospechoso` (admin, oficial, analista) y `aprobar_caso_sospechoso` (admin, oficial). La autoridad real está en el backend (`_validar_transicion`), que recibe rol y usuario desde la sesión autenticada.
- **Auditoría:** cada transición registra `CAMBIO_ESTADO_CASO:<anterior>-><nuevo>` en `BitacoraAuditoria` (módulo "Casos de Alerta") además del historial propio del caso.
- **UI** (`frontend/mod_alertas.py`, `app.py`):
  - Al haber un análisis cargado, `app.py` rehidrata in situ el DataFrame `casos` con los estados guardados para (licencia, lote); así Casos de Alerta, Resumen Ejecutivo (KPIs) y Reportes (RTS) ven el mismo estado sin pasar por la vista de alertas.
  - El panel de gestión crea el caso persistido al seleccionarlo, muestra clave, estado, proponente y aprobador, ofrece únicamente las transiciones autorizadas para el rol y usuario actuales, y lista el historial inmutable.
  - Manual de usuario actualizado con el estado `Sospechosa_Propuesta`, la regla de cuatro ojos y la retención.

### Evidencia de pruebas (contenedor cloud, Python 3.11)
- `python3 -m unittest discover -s tests`: **89 pruebas en verde** (70 previas + 19 nuevas en `tests/test_casos_alerta.py`, más una en `test_permisos.py`). Cobren: hash de lote estable ante reorden de filas y columnas y sensible a cambios de datos; idempotencia de `obtener_o_crear_caso`; aislamiento por tenant (otra licencia no lee, no muta ni ve historial); analista propone pero no confirma; el proponente no aprueba aunque sea oficial; oficial distinto aprueba y queda trazado; no se confirma sin propuesta; auditor sin transiciones; fundamento obligatorio; historial append-only (UPDATE y DELETE rechazados); caso no borrable; auditoría `CAMBIO_ESTADO_CASO`; rehidratación sobre el DataFrame sin mezclar tenants.
- Migración validada con `psql` (PostgreSQL 16) en dos rutas: (a) base con 001-002 aplicadas y 004 dos veces seguidas (idempotente, sin error); (b) DDL generado por el ORM y luego 004 (sin índices duplicados: 8 índices esperados). Con datos de prueba, los triggers rechazaron `UPDATE`/`DELETE` del historial y `DELETE` del caso, y el CHECK rechazó un estado inválido. Nota: 003 falla en una base vacía porque `Licencias` la crea el ORM; es comportamiento previo y no afecta a T1.
- Prueba de humo `apptest_smoke.py` en "Casos de Alerta", "Resumen Ejecutivo", "Reportes" y "SIN_DATOS": 0 excepciones, 0 errores, sin XSS. Prueba de humo adicional end-to-end con `AppTest` (sesión analista propone, nueva sesión del mismo analista no ve `Sospechosa_Confirmada`, sesión de oficial distinto la ve y confirma): estado rehidratado en la tabla de la segunda sesión, historial `CREAR -> PROPONER_SOSPECHOSA -> APROBAR_SOSPECHOSA` y dos eventos de auditoría.
- Duplicación de código: 1.97 % (umbral 10 %).

### Variables nuevas
Ninguna.

### Pasos de despliegue
1. `scripts/db_migrate.py` se ejecuta al arrancar y aplica `004_casos_alerta.sql` (requiere `pgcrypto`, ya usado por 001).
2. No se requiere acción manual. Si la base ya tenía las tablas creadas por `create_all` (arranque previo con este código), la migración solo añade triggers y comentarios.

### Pendientes y decisiones
- `Sospechosa_Confirmada` es terminal por diseño: revertir una confirmación exigiría un flujo de anulación con doble aprobación que no está en el alcance de T1. Opción: tarea futura "anulación de RTS" con fundamento y aprobación cruzada.
- Purga por retención (más de 5 años) queda fuera del alcance: la aplicación no borra; una eventual purga debe hacerse por procedimiento del administrador de base de datos deshabilitando temporalmente el trigger.
- La rehidratación filtra por `hash_lote`: si el lote cambia (una fila más), los casos previos no se recuperan por diseño (la evidencia del examen corresponde a un lote concreto). Los casos anteriores siguen consultables en la base de datos.
