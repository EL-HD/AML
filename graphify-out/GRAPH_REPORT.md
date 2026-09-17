# Graph Report - AML  (2026-09-16)

## Corpus Check
- 70 files · ~61,549 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 8 file(s) not represented in the graph (top: (none) 4, .toml 2, .example 1)

## Summary
- 723 nodes · 1603 edges · 33 communities (26 shown, 7 thin omitted)
- Extraction: 98% EXTRACTED · 2% INFERRED · 0% AMBIGUOUS · INFERRED: 27 edges (avg confidence: 0.85)
- Token cost: 209,583 input · 0 output

## Community Hubs (Navigation)
- Gestión de Riesgos y Planes de Acción
- Auditoría y Bitácora de Sesión
- Configuración del Motor AML
- Tokens Firmados de Restauración de Sesión
- Marco Normativo LD/FT (Ley 6593 / GAFILAT)
- Autenticación y Restauración de Sesión API
- Catálogos y Modelos de Auditoría ORM
- CLI de Administración del Proyecto
- Generación de Reportes Streamlit
- Fixtures de Pruebas de Backend
- Módulos de Visualización Streamlit
- Autenticación y Gestión de Licencias
- Middleware de Autenticación y RBAC
- Limitador de Intentos de Login
- Flujo de Login en app.py
- Generación de Documentos Word
- Utilidades HTML Seguras
- Motor de Procesamiento de Transacciones
- Seed de Licencias y Contraseñas
- Script de Seed para Producción
- Diagnóstico Imperator y Falsos Positivos
- Visualización de Red Transaccional
- CRUD de Licencias y Modelos
- Tests de Caché de Análisis Cifrada
- Tests de Tokens de Sesión
- Tests de Control de Acceso RBAC
- Seed de Catálogos Globales
- Módulo de Mitigación de Riesgo
- Tests de Límite de Intentos API
- Runner de Migraciones SQL
- Módulos Streamlit Misceláneos
- Logo AML (Imagen)

## God Nodes (most connected - your core abstractions)
1. `h()` - 44 edges
2. `_as_uuid()` - 25 edges
3. `render_html_table()` - 24 edges
4. `Plan de Trabajo: Adecuación Ley 6593` - 17 edges
5. `_tab_eventos()` - 15 edges
6. `Plan de Trabajo UI/UX y Seguridad · Sovereign AML (2026-09)` - 15 edges
7. `plotly_dark_layout()` - 14 edges
8. `generar_informe_general()` - 13 edges
9. `CatalogoActivoMixin` - 12 edges
10. `LimitadorIntentos` - 12 edges

## Surprising Connections (you probably didn't know these)
- `Principio Fail-closed (sin clave de firma → restauración deshabilitada)` --semantically_similar_to--> `_validar_retencion()`  [INFERRED] [semantically similar]
  docs/planes/PLAN_UIUX_SEGURIDAD_2026-09.md → frontend/mod_configuracion.py
- `Sovereign AML — Carta de Presentación (one-pager v3.0)` --conceptually_related_to--> `Hallazgo: no existe integración API/JSON con la IVE, solo CSV/portal manual`  [AMBIGUOUS]
  Sovereign_AML_Presentacion.pdf → docs/base-conocimiento/Oficio-IVE-19-2025-RTS.md
- `Sovereign AML — Carta de Presentación (one-pager v3.0)` --conceptually_related_to--> `S-01: Bypass de autenticación por restauración de sesión sin firma`  [AMBIGUOUS]
  Sovereign_AML_Presentacion.pdf → docs/planes/PLAN_UIUX_SEGURIDAD_2026-09.md
- `Sovereign AML — Carta de Presentación (one-pager v3.0)` --conceptually_related_to--> `S-04: Sin control de acceso por rol (RBAC)`  [AMBIGUOUS]
  Sovereign_AML_Presentacion.pdf → docs/planes/PLAN_UIUX_SEGURIDAD_2026-09.md
- `S-06: XSS almacenado/reflejado (339 usos de unsafe_allow_html sin escape)` --rationale_for--> `h()`  [EXTRACTED]
  docs/planes/PLAN_UIUX_SEGURIDAD_2026-09.md → frontend/ui_safe.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Endurecimiento de restauración de sesión (S-01/S-02, fail-closed)** — docs_planes_plan_uiux_seguridad_2026_09_s01_bypass_sesion, docs_planes_plan_uiux_seguridad_2026_09_s02_replay_payload, backend_session_token_firmar_restauracion, backend_session_token_verificar_restauracion, docs_planes_plan_uiux_seguridad_2026_09_fail_closed_principle [INFERRED 0.85]
- **Cadena de reporte regulatorio RTS a la IVE** — plan_trabajo_ley6593_rts, docs_base_conocimiento_oficio_ive_19_2025_rts_doc, docs_base_conocimiento_propuesta_captura_datos_rts_doc, frontend_mod_reportes_generar_bloque_rts [INFERRED 0.85]
- **Hallazgos de seguridad alineados a OWASP Top 10** — readme_owasp_mitigaciones, docs_planes_plan_uiux_seguridad_2026_09_s04_rbac_ausente, docs_planes_plan_uiux_seguridad_2026_09_s06_xss, docs_planes_plan_uiux_seguridad_2026_09_s01_bypass_sesion [INFERRED 0.75]

## Communities (33 total, 7 thin omitted)

### Community 0 - "Gestión de Riesgos y Planes de Acción"
Cohesion: 0.08
Nodes (71): actualizar_avance_plan(), _as_uuid(), controles_de_evento(), controles_sin_evento(), crear_control(), crear_evento(), crear_plan_accion(), crear_segmento() (+63 more)

### Community 1 - "Auditoría y Bitácora de Sesión"
Cohesion: 0.05
Nodes (52): _auditar(), Registra acceso de sesión activa: Art. 19 Ley 6593., ahora_utc(), _normalizar_uuid(), datetime, UUID, Bitácora de auditoría (Art. 19 Ley 6593, OWASP A09). Punto único para registrar…, Inserta un evento usando la sesión db recibida. Devuelve True si se persistió. (+44 more)

### Community 2 - "Configuración del Motor AML"
Cohesion: 0.06
Nodes (37): AmlConfig, config_por_defecto(), _mensaje_validacion(), BaseModel, Configuración del motor AML: valores por defecto y validación con lista blanca.…, Valida un diccionario contra AmlConfig. Claves desconocidas y valores fuera de…, validar_config(), field_validator (+29 more)

### Community 3 - "Tokens Firmados de Restauración de Sesión"
Cohesion: 0.06
Nodes (45): session_timeout_guard(), _b64d(), _b64e(), clave_firma(), _firma(), firmar_restauracion(), Tokens firmados para restaurar la sesión de Streamlit tras una recarga del…, Devuelve la clave de firma o None si no está configurada o es débil. (+37 more)

### Community 4 - "Marco Normativo LD/FT (Ley 6593 / GAFILAT)"
Cohesion: 0.06
Nodes (47): Decreto 15-2026 (Ley Integral para la Prevención y Represión del LD/FT), ADR: Administración de Riesgos LD/FT GAFILAT/IVE Guatemala (2026), Etapas de Administración de Riesgo: Identificación→Medición→Control→Monitoreo, GERILAFT App (herramienta gratuita IVE para riesgo institucional), Riesgo Inherente / Riesgo Residual (matriz de calor, mitigadores ponderados), Detalle Transaccional CSV: DTE/DTA (Anexo 2, catálogos oficiales), Oficio IVE 19-2025: Nuevo mecanismo de envío del RTS, FEIC: Formulario Electrónico de Información del Cliente (+39 more)

### Community 5 - "Autenticación y Restauración de Sesión API"
Cohesion: 0.09
Nodes (29): Serializa una Licencia ORM con la misma forma que devuelve la API de…, Restaura la sesión únicamente si el token está firmado, vigente y su session_id…, _restaurar_desde_token(), _usuario_a_dict(), get_current_user(), update_licencia(), update_perfil(), Devuelve la Licencia asociada a session_id solo si esa sesión es la más… (+21 more)

### Community 6 - "Catálogos y Modelos de Auditoría ORM"
Cohesion: 0.08
Nodes (31): BitacoraAuditoria, CatalogoActivoMixin, CatDepartamento, CatMoneda, CatMotivoInvolucramiento, CatMunicipio, CatPais, CatTipoCanal (+23 more)

### Community 7 - "CLI de Administración del Proyecto"
Cohesion: 0.18
Nodes (28): aml script, activate_venv(), cmd_down(), cmd_dump(), cmd_logs(), cmd_migrate(), cmd_railway_pull(), cmd_restore() (+20 more)

### Community 8 - "Generación de Reportes Streamlit"
Cohesion: 0.15
Nodes (27): dark_fig(), df_to_table(), fig_to_image(), header_band(), kpi_row(), make_styles(), mostrar(), generar_informe_general() (+19 more)

### Community 9 - "Fixtures de Pruebas de Backend"
Cohesion: 0.14
Nodes (11): backend, datetime, fastapi_testclient, requests, crear_engine_pruebas(), crear_session_factory(), Utilidades de base de datos para pruebas. Reutiliza el motor de…, Pruebas de la API de autenticación: RBAC (S-04), sesión única y perfil. (+3 more)

### Community 10 - "Módulos de Visualización Streamlit"
Cohesion: 0.21
Nodes (16): mostrar(), mostrar(), mostrar(), mostrar(), _detectar_rte(), mostrar(), Marca transacciones en efectivo >= USD 10,000 para RTE (Art. 31 Ley 6593)., plotly_dark_layout() (+8 more)

### Community 11 - "Autenticación y Gestión de Licencias"
Cohesion: 0.15
Nodes (23): _autenticar(), _claves_limite(), create_access_token(), delete_licencia(), _exigir_no_bloqueado(), login_for_access_token(), logout(), Session (+15 more)

### Community 12 - "Middleware de Autenticación y RBAC"
Cohesion: 0.10
Nodes (14): log_requests(), Dependencia FastAPI: exige que el usuario autenticado tenga uno de los roles…, require_role(), _crear_engine(), get_db(), PostgreSQL es el motor de producción. SQLite solo se admite para pruebas…, fastapi, fastapi_middleware_cors (+6 more)

### Community 13 - "Limitador de Intentos de Login"
Cohesion: 0.12
Nodes (11): ip_cliente(), ip_valida(), LimitadorIntentos, Limitación de intentos de autenticación (OWASP A07, hallazgo S-07). -…, 0 si la clave puede intentar; si no, segundos restantes de bloqueo., Resuelve la IP real: X-Forwarded-For solo se confía desde loopback., collections, ipaddress (+3 more)

### Community 14 - "Flujo de Login en app.py"
Cohesion: 0.16
Nodes (15): _cabeceras_origen(), clear_analysis_cache(), clear_browser_session(), _licence_id_actual(), login_flow(), _logout_session(), _procesar_login(), Propaga la IP real del navegador a la API (X-Forwarded-For) para el límite de… (+7 more)

### Community 15 - "Generación de Documentos Word"
Cohesion: 0.15
Nodes (18): Document, docx, docx_enum_table, docx_enum_text, docx_oxml, docx_oxml_ns, docx_shared, add_table() (+10 more)

### Community 16 - "Utilidades HTML Seguras"
Cohesion: 0.15
Nodes (11): ast, attr_css_color(), html_block(), Any, Rellena una plantilla str.format escapando todos los valores. Los argumentos…, Valida un color CSS (hex o nombre simple) antes de usarlo en style=., re, _fstrings_peligrosas() (+3 more)

### Community 17 - "Motor de Procesamiento de Transacciones"
Cohesion: 0.16
Nodes (15): _calcular_sb(), _calcular_sc(), _calcular_sn(), _calcular_st(), _convertir_a_bool(), _detectar_columnas_pep_cpe(), procesar_transacciones(), S_N = Riesgo de Red (normalizado 0–10) Basado en: riesgo promedio vecinos,… (+7 more)

### Community 18 - "Seed de Licencias y Contraseñas"
Cohesion: 0.21
Nodes (13): create_licencia(), create_licencia(), get_licencia_by_mail(), get_password_hash(), Licencia, LicenciaCreate, _leer_password(), main() (+5 more)

### Community 19 - "Script de Seed para Producción"
Cohesion: 0.18
Nodes (11): bcrypt, os, pathlib, Licencia, Base, Script de seed para produccion. Ejecutar una sola vez via Render Jobs. Crea los…, sqlalchemy_dialects_postgresql, sys (+3 more)

### Community 20 - "Diagnóstico Imperator y Falsos Positivos"
Cohesion: 0.22
Nodes (13): _calcular_dominancia(), _calcular_fp_estimado(), _card(), mostrar(), Retorna DataFrame con conteo de alertas por regla., Estima falsos positivos: alertas generadas en clientes con nivel Bajo.…, Media de cada componente de puntaje por nivel de riesgo., Simula cambios en un parámetro y retorna el nº de alertas para cada valor. Sólo… (+5 more)

### Community 21 - "Visualización de Red Transaccional"
Cohesion: 0.23
Nodes (11): _color_por_score(), _layout_circular(), mostrar(), _nodos_en_hops(), _normalizar_cliente(), Retorna color hex según score normalizado., Genera coordenadas circulares para los nodos., Normaliza nombres de cliente para evitar nodos duplicados por espacios. (+3 more)

### Community 22 - "CRUD de Licencias y Modelos"
Cohesion: 0.31
Nodes (9): get_licencia(), get_licencias(), Session, search_users(), validate_auth(), verify_password(), BitacoraSesions, sqlalchemy (+1 more)

### Community 26 - "Seed de Catálogos Globales"
Cohesion: 0.32
Nodes (7): csv, main(), _parse_csv(), scripts/seed_catalogos_globales.py Seed idempotente de los catalogos GLOBALES…, Inserta o actualiza filas de un catalogo por su clave primaria `codigo`.…, Parsea un bloque CSV embebido (codigo,nombre[,extra]) ignorando lineas vacias., _upsert_catalogo()

### Community 27 - "Módulo de Mitigación de Riesgo"
Cohesion: 0.36
Nodes (7): _buscar_accion(), _determinar_acciones(), mostrar(), Retorna el dict de acción dado su código., Escapa texto dinámico para evitar que el HTML se renderice como contenido., Determina las acciones de mitigación según el nivel de riesgo, score y factores…, _texto_seguro()

### Community 29 - "Runner de Migraciones SQL"
Cohesion: 0.53
Nodes (5): applied_migrations(), apply_sql_migrations(), ensure_tracking_table(), main(), Runner de migraciones — idempotente. 1) Crea las tablas ORM (backend/models.py)…

## Ambiguous Edges - Review These
- `Arquitectura: supervisord + FastAPI (auth_api.py) + Streamlit (app.py) + PostgreSQL en un contenedor Railway` → `render.yaml (manifiesto de despliegue Render.com, 2 servicios)`  [AMBIGUOUS]
  render.yaml · relation: conceptually_related_to
- `Hallazgo: no existe integración API/JSON con la IVE, solo CSV/portal manual` → `Sovereign AML — Carta de Presentación (one-pager v3.0)`  [AMBIGUOUS]
  Sovereign_AML_Presentacion.pdf · relation: conceptually_related_to
- `S-01: Bypass de autenticación por restauración de sesión sin firma` → `Sovereign AML — Carta de Presentación (one-pager v3.0)`  [AMBIGUOUS]
  Sovereign_AML_Presentacion.pdf · relation: conceptually_related_to
- `S-04: Sin control de acceso por rol (RBAC)` → `Sovereign AML — Carta de Presentación (one-pager v3.0)`  [AMBIGUOUS]
  Sovereign_AML_Presentacion.pdf · relation: conceptually_related_to
- `requirements.txt (dependencias fijadas, S-12)` → `runtime.txt (pin de versión de Python 3.10)`  [AMBIGUOUS]
  requirements.txt · relation: conceptually_related_to

## Knowledge Gaps
- **13 isolated node(s):** `Intendencia de Verificación Especial (IVE)`, `PSAV: Proveedor de Servicios de Activos Virtuales`, `Estructura Jurídica (tipo de cliente nuevo, Art. 3 Ley 6593)`, `Comando `aml` (orquestador local: up/migrate/seed/dump/restore/status)`, `GERILAFT App (herramienta gratuita IVE para riesgo institucional)` (+8 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 242 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **7 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **What is the exact relationship between `Arquitectura: supervisord + FastAPI (auth_api.py) + Streamlit (app.py) + PostgreSQL en un contenedor Railway` and `render.yaml (manifiesto de despliegue Render.com, 2 servicios)`?**
  _Edge tagged AMBIGUOUS (relation: conceptually_related_to) - confidence is low._
- **What is the exact relationship between `Hallazgo: no existe integración API/JSON con la IVE, solo CSV/portal manual` and `Sovereign AML — Carta de Presentación (one-pager v3.0)`?**
  _Edge tagged AMBIGUOUS (relation: conceptually_related_to) - confidence is low._
- **What is the exact relationship between `S-01: Bypass de autenticación por restauración de sesión sin firma` and `Sovereign AML — Carta de Presentación (one-pager v3.0)`?**
  _Edge tagged AMBIGUOUS (relation: conceptually_related_to) - confidence is low._
- **What is the exact relationship between `S-04: Sin control de acceso por rol (RBAC)` and `Sovereign AML — Carta de Presentación (one-pager v3.0)`?**
  _Edge tagged AMBIGUOUS (relation: conceptually_related_to) - confidence is low._
- **What is the exact relationship between `requirements.txt (dependencias fijadas, S-12)` and `runtime.txt (pin de versión de Python 3.10)`?**
  _Edge tagged AMBIGUOUS (relation: conceptually_related_to) - confidence is low._
- **Why does `h()` connect `Módulos de Visualización Streamlit` to `Gestión de Riesgos y Planes de Acción`, `Auditoría y Bitácora de Sesión`, `Tokens Firmados de Restauración de Sesión`, `Generación de Reportes Streamlit`, `Flujo de Login en app.py`, `Utilidades HTML Seguras`, `Diagnóstico Imperator y Falsos Positivos`, `Visualización de Red Transaccional`, `Módulo de Mitigación de Riesgo`, `Módulos Streamlit Misceláneos`?**
  _High betweenness centrality (0.105) - this node is a cross-community bridge._
- **Why does `_registrar_acceso_auditoria()` connect `Auditoría y Bitácora de Sesión` to `Configuración del Motor AML`, `Marco Normativo LD/FT (Ley 6593 / GAFILAT)`, `Flujo de Login en app.py`, `CRUD de Licencias y Modelos`?**
  _High betweenness centrality (0.062) - this node is a cross-community bridge._