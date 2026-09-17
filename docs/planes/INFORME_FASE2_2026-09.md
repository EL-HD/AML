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

---

## T2 CI en GitHub Actions

**Estado:** HECHO (validación local completa; la primera ejecución real en GitHub queda pendiente del push) · **Fecha:** 17/09/2026 · **Commit:** ver `git log` (commit `ci(t2): ...`).

### Qué se hizo
- **`.github/workflows/ci.yml`**: disparadores `push` y `pull_request` a `main` y `mejora/**`; `permissions: contents: read`; `concurrency` por rama con `cancel-in-progress`; `timeout-minutes` en cada trabajo; sin secretos (solo las variables ficticias de `tests/conftest.py`: `SECRET_KEY`, `SESSION_SIGN_KEY`, `JWT_ISSUER`, `JWT_AUDIENCE`, `CACHE_ENCRYPTION_SALT`, `DATABASE_URL=sqlite://`).
  - Trabajo **calidad**: `actions/setup-python` con Python 3.11 y caché de pip (`cache-dependency-path: requirements.txt`); `pip install -r requirements.txt bandit pip-audit`; `python -m unittest discover -s tests -v`; `bandit -c bandit.yaml -r backend frontend auth_api.py app.py scripts -ll`; `pip-audit -r requirements.txt --progress-spinner off`; `python scripts/medir_duplicacion.py --umbral 10 app.py auth_api.py backend frontend scripts` (sale con código 1 si supera 10 %).
  - Trabajo **migraciones**: servicio `postgres:16` con `pg_isready` como healthcheck y credenciales efímeras de CI; `scripts/db_migrate.py` dos veces sobre base vacía; la segunda ejecución debe imprimir "Sin migraciones SQL pendientes" (`set -o pipefail` para que un fallo en la tubería no quede oculto); luego `psql` verifica que `schema_migrations` tiene tantas filas como archivos en `migrations/`, que existe `Licencias.rol` y la restricción `licencias_rol_check`.
- **`bandit.yaml`**: excluye `tests/`, entornos locales y respaldos (evita falsos positivos por credenciales ficticias y `assert` en pruebas).
- **`.github/dependabot.yml`**: actualizaciones mensuales de las acciones del workflow.
- **`scripts/medir_duplicacion.py`**: la huella de ventanas pasa de `sha1` a `sha256`. No es un uso criptográfico, pero `bandit -ll` reporta B324 (severidad media) para `sha1`/`md5` y haría fallar el pipeline. Resultado idéntico (1.72 %).
- **README**, sección 7: descripción del pipeline y pasos para activar **Wait for CI** en Railway (Settings > Source > Wait for CI / Check Suites). No se tocó la configuración de Railway.

### Decisiones
- **Fijación de acciones a versión mayor** (`actions/checkout@v4`, `actions/setup-python@v5`) en lugar de SHA de commit: desde el entorno de desarrollo no hay acceso a `api.github.com` ni a `github.com` (proxy 403), por lo que no fue posible verificar los SHA; un SHA erróneo rompería todo el pipeline. La decisión y el procedimiento para migrar a SHA (aceptar el primer PR de Dependabot y usar `uses: owner/accion@<sha> # vX.Y.Z`) quedan documentados en la cabecera del workflow.
- **Orden del runner de migraciones**: se revisó `scripts/db_migrate.py`: `models.Base.metadata.create_all` corre antes que `migrations/*.sql`, de modo que `Licencias` (con `rol`) ya existe cuando se aplica `003_rol_licencias.sql`. El problema conocido ("003 falla en base vacía") solo ocurre al aplicar los `.sql` con `psql` sin pasar por el runner; con `db_migrate.py` no se reproduce, por lo que no hubo que corregir nada en el runner ni en las migraciones 001-003. El trabajo `migraciones` de CI cubre exactamente esa ruta.

### Evidencia (contenedor cloud, Python 3.11, PostgreSQL 16)
- YAML de los tres archivos cargado con `yaml.safe_load` sin errores; estructura verificada (2 trabajos, 7 y 6 pasos, disparadores y permisos correctos).
- `python3 -m unittest discover -s tests`: 89 pruebas en verde.
- `scripts/medir_duplicacion.py --umbral 10 app.py auth_api.py backend frontend scripts`: 9073 líneas, 156 duplicadas, 1.72 % (código de salida 0).
- Emulación del trabajo `migraciones` con `psql` (sin `psycopg2` en el contenedor): DDL del ORM generado con el dialecto PostgreSQL y aplicado a una base vacía, después `001` a `004` dos veces seguidas sin error; comprobaciones finales del paso "Verificar esquema resultante" (4 = 4 migraciones registradas, columna `rol` presente, CHECK presente) satisfechas.
- Revisión estática previa a bandit sobre los mismos patrones que reporta con severidad media (`requests` sin `timeout`, `/tmp` literal, `0.0.0.0`, `yaml.load`, `pickle`, `eval/exec`, `shell=True`, SQL por f-string, `md5/sha1`): único hallazgo el `sha1` de `medir_duplicacion.py`, corregido.

### Variables nuevas
Ninguna en producción. En CI solo valores ficticios definidos en el propio workflow.

### Pasos de despliegue
1. Al hacer push de la rama, GitHub ejecutará el workflow automáticamente (el push queda fuera del alcance de esta fase, según las reglas comunes).
2. Activar **Wait for CI** en Railway (Settings > Source) para que `main` solo despliegue con CI en verde.

### Pendientes y motivo
- `bandit` y `pip-audit` no pudieron ejecutarse localmente (PyPI bloqueado en ambos entornos); la primera corrida en GitHub puede revelar hallazgos. Opciones si ocurre: corregir el código (preferible), o añadir `# nosec Bxxx` con justificación puntual; para `pip-audit`, actualizar la versión afectada en `requirements.txt` o, si no existe parche, `--ignore-vuln <id>` documentado.
- Fijación a SHA de commit: pendiente hasta el primer PR de Dependabot (ver Decisiones).

---

## T3 Screening de listas de sanciones (GAFI R.6 / R.7)

**Estado:** HECHO · **Fecha:** 17/09/2026 · **Commit:** `dc66328` (código) y el commit de este informe.

### Qué se hizo
- **Motor puro** (`backend/screening.py`, sin Streamlit ni base de datos):
  - Normalización: NFKD sin acentos, minúsculas, puntuación a espacio, tokens ordenados, eliminación de formas jurídicas y partículas (S.A., LTD, de, la...) y de siglas de una letra, salvo que no quede ningún token.
  - Jaro-Winkler implementado con biblioteca estándar (p = 0.1, prefijo máximo 4) y verificado contra valores de referencia (MARTHA/MARHTA 0.9611, DWAYNE/DUANE 0.8400, DIXON/DICKSONX 0.8133).
  - Puntaje = máximo entre Jaro-Winkler del nombre completo normalizado y una similitud por tokens (promedio del mejor Jaro-Winkler por token, atenuado por la diferencia de cantidad de tokens: 0.8 + 0.2 × corto/largo). Umbral configurable entre 0.70 y 1.00, por defecto **0.88**. Resultado explicable: fuente, referencia, nombre de la entrada, alias coincidente, puntaje y motivo ("Coincidencia exacta del nombre normalizado", "Jaro-Winkler 0.914 sobre el nombre completo", "Similitud por tokens 0.900 (tokens comunes: juan, perez)").
  - `IndiceScreening`: índice invertido por token y por prefijo de 3 caracteres sobre nombres y alias; cada consulta solo se compara contra los candidatos que comparten token o prefijo.
  - Parsers con validación de filas: OFAC SDN (`sdn.csv` de 12 columnas y `alt.csv` de 5, sin encabezado, `-0-` como nulo, alias `aka/fka/nka`, filas inválidas o duplicadas contadas como rechazadas) y ONU consolidada (XML: `INDIVIDUAL`/`ENTITY`, `DATAID`, nombres `FIRST_NAME..FOURTH_NAME`, `UN_LIST_TYPE`, `NATIONALITY`, alias separados por `;`).
  - Endurecimiento XML: tamaño máximo 50 MB y rechazo de cualquier `<!DOCTYPE` o `<!ENTITY` (XXE y "billion laughs") **antes** de llamar a `xml.etree`. Los `# nosec` puntuales (B405/B314) quedan justificados en el código.
  - Descarga oficial opcional: solo desde las constantes `URL_OFAC_SDN`, `URL_OFAC_ALT` y `URL_ONU_CONSOLIDADA` (hosts `www.treasury.gov` y `scsanctions.un.org`), HTTPS, `allow_redirects=False`, timeout 60 s, lectura por trozos con corte al superar 50 MB. Desactivada por defecto; se habilita con `SCREENING_AUTO_DOWNLOAD=true`. Nunca se acepta una URL del usuario (anti SSRF). El contenedor de pruebas no tiene red: la ruta real no se ejercita; se prueba con un doble de `requests.get`.
- **Persistencia** (`migrations/005_screening.sql`, `backend/models.py`, `backend/screening_repo.py`):
  - `ListasSancion` (global): fuente (CHECK `OFAC_SDN`/`ONU`), versión, archivo, `hash_sha256`, cantidad de entradas, filas rechazadas, origen (`carga_manual`/`descarga_oficial`), activa, quién y cuándo. Solo una versión activa por fuente; una versión con el mismo SHA-256 activo se rechaza.
  - `ListasSancionEntradas` (global): referencia, nombre, nombre normalizado, tipo, programa, nacionalidad y alias en JSON. Inserción por lotes de 2000.
  - `ScreeningCoincidencias` (por `licenciaid`): cliente, origen (`Cliente`/`Cliente_Destino`), `hash_lote`, lista, entrada, fuente, referencia, nombre de lista, alias, puntaje, motivo, estado (CHECK `Pendiente`/`Descartada`/`Confirmada`), fundamento, revisor, fecha, `caso_id`. `UNIQUE (licenciaid, cliente_normalizado, entrada_id)`: repetir el screening no duplica ni pisa decisiones.
  - `ScreeningDecisiones` (por `licenciaid`): historial append-only de cada decisión (trigger PostgreSQL y listeners ORM que rechazan UPDATE/DELETE, misma función `fn_casos_alerta_inmutable` de la migración 004).
  - Decisión (`decidir`): solo admin/oficial; fundamento obligatorio (10 a 4000 caracteres); `Descartada` o `Confirmada`; al confirmar un cliente del lote se obtiene o crea su Caso de Alerta (T1) y se guarda `caso_id`; para contrapartes (`Cliente_Destino`) queda la señal sin caso. Cada decisión registra `DECISION_SCREENING:<anterior>-><nuevo>` en `BitacoraAuditoria`; la carga registra `CARGA_LISTA_SANCION:<fuente>:<n>` y la ejecución `EJECUCION_SCREENING:<nuevas>`.
  - Índice cacheado por proceso mientras no cambie el conjunto de listas activas (se invalida en cada carga).
- **Permisos** (`frontend/permisos.py`): `cargar_listas_sancion` (admin), `gestionar_screening` (admin, oficial), `ver_screening` (todos). La autoridad real está en `screening_repo` (`ROLES_CARGA`, `ROLES_REVISION`).
- **UI** (`frontend/mod_screening.py`, `frontend/navegacion.py`, `app.py`, `frontend/mod_cliente.py`):
  - Vista **Investigación > Listas de Sanciones** (no requiere análisis cargado) con tres pestañas: listas cargadas y carga (extensión, tamaño y contenido validados; panel de descarga oficial visible solo si la variable está activa), ejecución sobre `Cliente` y `Cliente_Destino` del análisis con umbral ajustable, y bandeja con KPIs, tabla, detalle explicable, historial y formulario de decisión. Analista y auditor ven todo en solo lectura (`exigir_o_avisar`).
  - `app.py` añade la columna `Screening_Sanciones` al DataFrame de casos en cada ejecución (`marcar_casos`, señales cacheadas en sesión y refrescadas tras ejecutar o decidir).
  - Ficha del cliente: insignia "Screening de sanciones: Pendiente/Confirmada (n)" o "Sin coincidencias en listas de sanciones" y resumen de coincidencias.
  - Todo valor dinámico pasa por `ui_safe.h`, `html_block` o `render_html_table`; se reutilizan `page_header`, `kpi`, `info_panel`, `status_badge`, `empty_state`.
- Manual de usuario (sección 5.3) y README (variable nueva) actualizados.

### Evidencia (contenedor cloud, Python 3.11, PostgreSQL 16)
- `python3 -m unittest discover -s tests`: **121 pruebas en verde** (89 previas + 32 nuevas en `tests/test_screening.py`): normalización; Jaro-Winkler contra valores conocidos; índice por token/prefijo y mejor variante por entrada; parsers OFAC y ONU con fixtures ficticios (alias, tipos, nacionalidad, filas rechazadas); rechazo XXE/DOCTYPE, XML mal formado, vacío, tamaño y extensión; descarga desactivada por defecto, solo URLs fijas HTTPS, sin redirecciones y con límite; solo admin carga; versión/hash/cantidad y desactivación de la anterior; auditoría de carga; solo admin/oficial ejecuta; coincidencias explicables e idempotencia; aislamiento por tenant (otra licencia no lista, no obtiene, no decide ni ve historial); fundamento obligatorio y roles (analista y auditor no deciden); confirmación vincula caso y audita; historial append-only; señal en el DataFrame.
- Rendimiento con datos sintéticos: 15.000 entradas con 2 alias cada una (45.000 variantes): construcción del índice 0.43 s; 250 consultas 0.45 s (unas 550 consultas/s). En la prueba de humo real: 130 nombres del Excel de ejemplo en 0.009 s.
- Prueba de humo (`apptest_smoke.py` y un guion extendido con `AppTest`): vistas "Listas de Sanciones" (admin y auditor), "Análisis por Cliente", "Casos de Alerta", "Resumen Ejecutivo", "Manual de Usuario" y sin datos: 0 excepciones y sin XSS. Flujo completo en la UI: carga de lista ficticia, clic en "Ejecutar screening" (4 coincidencias), decisión "Confirmada" con fundamento y verificación de `caso_id` vinculado; el auditor ve el aviso de solo lectura.
- Migración validada con `psql`: (a) DDL del ORM + `001` a `005` dos veces seguidas sin error y sin índices duplicados (14 índices esperados en las cuatro tablas); (b) `001`, `004` y `005` dos veces sin ORM. Con datos de prueba, el trigger rechazó `UPDATE` y `DELETE` en `ScreeningDecisiones` y el CHECK rechazó un estado inválido.
- Duplicación: 10.270 líneas, 180 duplicadas, **1.75 %** (umbral 10 %).

### Variables nuevas
- `SCREENING_AUTO_DOWNLOAD` (opcional, por defecto `false`): habilita la descarga desde las URLs oficiales fijas. La carga manual funciona siempre.

### Pasos de despliegue
1. `scripts/db_migrate.py` aplica `005_screening.sql` al arrancar (ORM primero, SQL después).
2. Un Administrador descarga `sdn.csv` y `alt.csv` (OFAC) y `consolidated.xml` (ONU) desde los sitios oficiales y los carga en Investigación > Listas de Sanciones. Opcional: `SCREENING_AUTO_DOWNLOAD=true` si la red de Railway alcanza `www.treasury.gov` y `scsanctions.un.org`.
3. Ejecutar el screening tras cada carga de análisis y revisar la bandeja.

### Pendientes y motivo
- Los archivos reales de OFAC y ONU no pudieron descargarse (sin red en ambos entornos): los parsers siguen el formato documentado y se probaron con fixtures ficticios. Opciones: validar con los archivos reales en el primer despliegue; si la ONU cambia etiquetas, ajustar `parsear_onu_consolidada`.
- No hay programación automática (cron) de la descarga: la constante y la variable dejan lista la función `descargar_oficial`; se puede invocar desde un servicio cron de Railway (T7 documentará el patrón) o desde la UI.
- La comparación no usa fecha de nacimiento ni documento para reducir falsos positivos (el Excel de entrada no los trae); el fundamento de la decisión exige documentar esa verificación manual.
