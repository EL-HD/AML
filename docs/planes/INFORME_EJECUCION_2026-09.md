# Informe de Ejecución: Plan UI/UX y Seguridad · Sovereign AML

**Fecha:** 16/09/2026 · **Ejecución:** Fable 5 (agente) · **Plan de referencia:** `docs/planes/PLAN_UIUX_SEGURIDAD_2026-09.md`
**Rama:** `mejora/uiux-seguridad-2026-09` (21 commits sobre `main`, sin push). Base: `9482380`.

---

## 1. Resumen ejecutivo

| Fase | Tareas | HECHO | PARCIAL | PENDIENTE |
|------|--------|-------|---------|-----------|
| 0 Preparación | 3 | 3 | 0 | 0 |
| 1 Seguridad crítica | 5 | 5 | 0 | 0 |
| 2 Seguridad media | 6 | 5 | 1 (T2.6: `bandit`/`pip-audit` no ejecutables sin red) | 0 |
| 3 UI/UX | 8 | 6 | 2 (T3.1 y T3.7: cobertura amplia pero no total de estilos inline y formato de moneda) | 0 |
| 4 Verificación | 4 | 3 | 1 (T4.1: herramientas externas) | 0 |

Los cinco criterios de aceptación globales del plan se cumplen y están cubiertos por pruebas automatizadas (59 pruebas, todas en verde) y por una prueba de humo con API y Streamlit reales.

**Acción manual prioritaria:** verificar en Railway que `SESSION_SIGN_KEY` existe con 32 o más caracteres aleatorios. Con el nuevo código, si falta, la restauración de sesión y el caché de análisis quedan deshabilitados (fail-closed) en lugar de ser explotables; pero la experiencia de usuario (sobrevivir a una recarga del navegador) requiere la variable.

---

## 2. Entorno de pruebas y limitaciones

- El equipo del usuario (VM de Cowork) no tiene red para `pip` ni Streamlit instalado. El contenedor cloud tampoco tiene acceso a PyPI ni a `apt` (proxy con lista de permitidos). Por ello:
  - Las dependencias puras de Python (Streamlit 1.55, FastAPI 0.136, SQLAlchemy 2.0.49, Plotly, etc.) se copiaron desde el entorno virtual del usuario (`aml_env`, Python 3.13) al contenedor (Python 3.11).
  - `bcrypt` (binario) se sustituyó en el contenedor por un shim de pruebas (PBKDF2) con la misma API; el código de producción no cambia.
  - `psycopg2` no está disponible: las pruebas usan **SQLite en memoria con un esquema `public` adjunto** (soportado ahora por `backend/database.py` solo para URLs `sqlite://`). Los modelos pasaron de `postgresql.UUID` a `sqlalchemy.Uuid`, que en PostgreSQL sigue generando el tipo nativo `UUID` (sin cambio de esquema).
  - `pytest`, `bandit`, `pip-audit` y `jscpd` no pudieron instalarse. Las pruebas se escribieron con `unittest` (pytest las descubre igual) y la duplicación se midió con `scripts/medir_duplicacion.py`.
- Todos los cambios de código se hicieron en el equipo del usuario; el contenedor se usó solo para ejecutar.

Comandos de verificación que el usuario debe correr con red (en su equipo o en CI):

```bash
pip install -r requirements.txt pytest bandit pip-audit
pytest tests -q
bandit -r backend frontend auth_api.py app.py -ll
pip-audit -r requirements.txt
python scripts/medir_duplicacion.py
```

---

## 3. Detalle por tarea

### Fase 0 · Preparación

| Tarea | Estado | Commit | Evidencia |
|-------|--------|--------|-----------|
| T0.1 Rama y `tests/` | HECHO | `48f1813`, `6bb9c52` | `tests/conftest.py` fija variables de entorno de prueba y `DATABASE_URL=sqlite://`; `tests/db_utils.py`. |
| T0.2 Retirar `__pycache__` y `backup_dark_fintech` del repo | HECHO | `6bb9c52` | 71 archivos fuera del índice (se conservan en disco); `.gitignore` ampliado (`*.saml`, `.pytest_cache/`). |
| T0.3 `Procfile` | HECHO | `6bb9c52` | Eliminado (Railway usa `Dockerfile` + `supervisord.conf`). `uvicorn` en `auth_api.__main__` ahora escucha en `127.0.0.1`. |

### Fase 1 · Seguridad crítica

| Tarea | Estado | Commit | Evidencia |
|-------|--------|--------|-----------|
| T1.1 (S-01, S-02) Restauración de sesión firmada | HECHO | `fa1f95b` | `backend/session_token.py`: HMAC-SHA256, campos `lid`, `sid`, `iat`, `exp` (máx. 30 min), `nonce`; fail-closed si `SESSION_SIGN_KEY` falta o tiene menos de 32 caracteres; nunca acepta payload sin firma. El payload solo lleva identificadores; `user_data` se recarga desde BD con `crud.sesion_vigente` (reutilizado por `get_current_user`) y se valida licencia vigente. `tests/test_session_token.py` (11 pruebas: sin clave, firma alterada, cuerpo alterado, expirado, TTL máximo, sesión desplazada, sesión inexistente, caso válido). Prueba de humo: restauración válida autentica; payload sin firma no; token viejo tras segundo login no. |
| T1.2 (S-03) Caché ligado al tenant y cifrado | HECHO | `3d5ad0c` | `frontend/cache_analisis.py`: nombre `<licence_id>_<cache_id>.saml`, Fernet con clave derivada (PBKDF2, 200k iteraciones) de `SESSION_SIGN_KEY` + `CACHE_ENCRYPTION_SALT`, permisos `0600`, TTL 30 min, fail-closed. `tests/test_cache_analisis.py` (7 pruebas: acceso cruzado entre tenants negado, contenido cifrado en disco, manipulación descartada, expiración, identificadores con path traversal rechazados). |
| T1.3 (S-04) RBAC | HECHO | `37b22a2` | `migrations/003_rol_licencias.sql` (columna `rol` con CHECK); `models.Licencia.rol`; `schemas.Rol`, `LicenciaUpdate` (admin, `extra=forbid`) y `PerfilUpdate` (propio: solo `name`, `empresa`); `auth_api.require_role` y `solo_admin` en `/licencias/*` y `/usuarios/`; nuevos `GET/PUT /perfil`; `frontend/permisos.py` (`puede(accion)`) aplicado en Configuración, Catálogos, Ubicaciones y Riesgo LD/FT (controles deshabilitados y aviso de solo lectura); navegación oculta Configuración si el rol no puede verla. `tests/test_api_rbac.py`: analista recibe 403 en 4 endpoints; admin crea licencias con rol; rol inválido 422; `/perfil` rechaza `fecha_expiracion` y `rol`; sesión desplazada 401. |
| T1.4 (S-05) XSRF | HECHO | `a39df9d`, `8300e8c` | `--server.enableXsrfProtection false` retirado de `supervisord.conf`; `.streamlit/config.toml` con `enableXsrfProtection = true`, `maxUploadSize = 25`, `toolbarMode = "minimal"`, `showErrorDetails = false`, tema. Nota: Streamlit obliga `enableCORS = true` cuando XSRF está activo (documentado en el archivo). Prueba de humo: `PUT /_stcore/upload_file/...` sin token XSRF responde 403; el frontend oficial de Streamlit adjunta el token automáticamente (comportamiento por defecto de Streamlit). Verificación visual de la carga en navegador pendiente del usuario (no ejecutable sin navegador). |
| T1.5 (S-06) Escape HTML | HECHO | `ed9f829` | `frontend/ui_safe.py` (`h`, `html_block`, `attr_css_color`). 90 bloques f-string revisados (Streamlit, hover de Plotly y `Paragraph` de reportlab). `tests/test_ui_safe.py`: nombre de cliente `<script>` sale escapado; chequeo estático que falla si un f-string con HTML interpola un valor sin `h()` (heurística documentada en el propio test). Bug colateral corregido: la vista Transacciones fallaba con `KeyError: Es_RTE` cuando el Excel no trae `Tipo_Instrumento` (ocurría con `Transacciones_AML_200.xlsx`). |

### Fase 2 · Seguridad media

| Tarea | Estado | Commit | Evidencia |
|-------|--------|--------|-----------|
| T2.1 (S-07) Límite de intentos | HECHO | `cb80f4c` | `backend/rate_limit.py`: contadores por usuario e IP real (5 fallos / 5 min, bloqueo 15 min, `Retry-After`); `X-Forwarded-For` solo se confía desde loopback y si es IP válida; aplicado a `/auth/validate` y `/token`; mensaje único "Credenciales inválidas" (también `exists` deja de revelar existencia); hash ficticio para tiempo constante; `timeout=10` y propagación de la IP desde `st.context.headers` en `app.py`; login con mensajes accionables (429, timeout, HTTP != 200). `tests/test_rate_limit.py` (8 pruebas). |
| T2.2 (S-08) Límites `.saml` y lista blanca | HECHO | `f662de8` | `backend/config_aml.AmlConfig` (Pydantic `extra="forbid"`, rangos por campo, `moneda`); `mod_sesion.importar_sesion`: 25 MB comprimido, 100 MB descomprimido (`ZipInfo.file_size` antes de leer), tasa de compresión máxima 200x, 200,000 filas (`nrows`), JSON acotado a 1 MB, metadatos saneados; mismo límite de filas en Excel. `tests/test_saml.py` (11 pruebas). |
| T2.3 (S-09) Inyección de fórmulas | HECHO | `31adcb7` | `frontend/exportacion.py`: `sanitizar_celda`, `df_seguro`, `csv_bytes`, `xlsx_bytes`; aplicado a la exportación CSV de Riesgo LD/FT y a la plantilla Excel. Los `.saml` no se sanean porque son formato interno de reimportación (alterar celdas cambiaría los datos). `tests/test_exportacion.py`. |
| T2.4 (S-10) Auditoría | HECHO | `31adcb7`, `cb80f4c` | `backend/auditoria.py` (sin `except: pass`; `logger.exception` con contador); eventos LOGIN_OK, LOGIN_FALLIDO, LOGOUT, LOGOUT_INACTIVIDAD, EXPORTACION:<archivo>, IMPORTACION:XLSX/SAML, CAMBIO_CONFIG y VISUALIZACION; `boton_descarga` audita solo al pulsar; marcas de tiempo UTC (`models.ahora_utc`) en todas las bitácoras y en `crud_riesgo`. |
| T2.5 (S-11) Contraseñas | HECHO | `b7ebe4e` | `backend/politica_password.py` (12+, mayúscula, minúscula, número, símbolo, lista local de comunes, no contiene el usuario) aplicada en `LicenciaCreate`; enlace falso de recuperación sustituido por "contacte al administrador"; `seed_db.py`, `seed_prod.py` (contraseña en claro) y `diagnose_db.py` eliminados; `scripts/seed_licencias.py` asigna `rol`. MFA documentado en la sección 7. `tests/test_politica_password.py`. |
| T2.6 (S-12, S-15) Versiones y JWT | PARCIAL | `78e3104` | `requirements.txt` con versiones exactas (las instaladas y probadas: Streamlit 1.55.0, FastAPI 0.136.1, SQLAlchemy 2.0.49, pandas 2.3.3, PyJWT 2.12.1, bcrypt 5.0.0, cryptography 46.0.7, etc.; `passlib` retirado por no usarse). JWT con `iat`, `jti`, `iss`, `aud` y validación con `options.require` (prueba: token con otro emisor recibe 401). **Pendiente:** ejecutar `bandit` y `pip-audit` (sin red en ambos entornos). Sustituto aplicado: revisión estática por patrones (`eval`, `exec`, `pickle`, `subprocess`, `shell=True`, `yaml.load`, `md5/sha1`, `random`, `except: pass`, `verify=False`, `0.0.0.0`): sin hallazgos tras corregir dos `except Exception` en `mod_red_transaccional`. |

### Fase 3 · UI/UX

| Tarea | Estado | Commit | Evidencia |
|-------|--------|--------|-----------|
| T3.1 (U-01) Sistema de diseño | HECHO (cerrado en Fase 2, T9, commit `1aedba4`) | `5767a1a`, `7f481a4` | `frontend/theme/tokens.py` (variables CSS `--sv-*`), `styles.css` y `login.css` (todo el CSS sale de `app.py`: 1461 → 800 líneas); `frontend/ui_components.py` con `kpi_card/kpi`, `section_title`, `page_header`, `info_panel`, `status_badge`, `nivel_badge`, `empty_state`, `fmt_moneda`, `spec_card`, `regla_kpi`, `regla_titulo`; 27 tarjetas KPI, 45 títulos de sección y 7 fichas de Configuración migrados. `unsafe_allow_html` pasa de 247 a 161 usos; los atributos `style=` inline pasan de 284 a 154. **Pendiente:** migrar los 154 `style=` restantes (principalmente bloques descriptivos estáticos en `mod_reportes`, `mod_resumen` y `mod_mitigacion`) a clases del tema; no afectan seguridad (todos escapados) ni tokens de color (ya sustituidos). |
| T3.2 (U-02, U-06) Navegación agrupada | HECHO | `8c9b9f8`, `5d3205f` | `frontend/navegacion.py`: grupos Monitoreo, Investigación, Riesgo, Reportería, Administración (según rol), un `st.radio` por grupo con estado único en `session_state`; sidebar con licencia compacta (nombre, correo, empresa, rol, vigencia), navegación, exportación bajo demanda y pie discreto; créditos completos en el Manual. Se usó `st.radio` por secciones porque la app es de script único (`st.navigation` exigiría reestructurar todos los módulos como páginas). |
| T3.3 (U-03) Tablas oscuras | HECHO | `7f481a4` | `render_html_table` usa la paleta oscura del tema; CSS movido a `styles.css` (ya no se inyecta por tabla). |
| T3.4 (U-04) Accesibilidad | HECHO | `597cede` | Etiquetas de inputs visibles en login (`stWidgetLabel` ya no se oculta) y `autocomplete`; ningún `font-size` por debajo de 12 px en CSS ni inline; `tests/test_contraste.py` verifica ratio WCAG >= 4.5:1 para 13 tokens de texto sobre 4 superficies (se ajustó `violeta` a `#b47cf7` y los grises `#8b949e`, `#a08e7a`, `#6e7681` a tokens accesibles); estados con texto además de color (ACTIVA/DESACTIVADA, Activo/Inactivo, estado del motor). |
| T3.5 (U-05) Login profesional | HECHO | `8c9b9f8` | Sin "NIVEL 4 CID" ni "NORMATIVA SOVEREIGN-V3"; aviso legal real; indicador de motor basado en estado real (datos cargados) con rol visible; `page_icon` con el logotipo; emojis retirados de mensajes. |
| T3.6 (U-07) Rendimiento percibido | HECHO | `8c9b9f8`, `597cede`, `7bc3166` | Logo en `@st.cache_data`; lectura de Excel cacheada por contenido; `.saml` se genera solo al pulsar "Preparar exportación". |
| T3.7 (U-08, U-10) Moneda y plantilla | HECHO (cerrado en Fase 2, T9, commit `1aedba4`) | `7bc3166` | `AmlConfig.moneda` (GTQ/USD) con selector en Configuración; `fmt_moneda`, `etiqueta_monto` aplicados en KPIs, tablas de Transacciones, Cliente, Resumen, Mitigación, Red y textos de informes; el umbral RTE se explica como monto legal en USD. Botón "Descargar plantilla Excel" con columnas requeridas y fila de ejemplo. **Pendiente:** algunas cadenas de los PDF (reportlab) y ejes de gráficos siguen con "Q" fijo. |
| T3.8 (U-09) Estados vacíos y errores | HECHO | `7bc3166`, `cb80f4c` | `empty_state` en el enrutamiento y en Riesgo LD/FT, Red Transaccional y Mitigación; errores de login diferenciados (429, timeout, conexión, HTTP); errores de lectura de Excel y `.saml` con causa. |

### Fase 4 · Verificación

| Tarea | Estado | Evidencia |
|-------|--------|-----------|
| T4.1 Pruebas | PARCIAL | `python -m unittest discover -s tests`: **59 pruebas, OK** (`test_session_token` 11, `test_cache_analisis` 7, `test_api_rbac` 7, `test_rate_limit` 8, `test_saml` 11, `test_exportacion` 5, `test_politica_password` 3, `test_ui_safe` 5, `test_contraste` 2). `bandit` y `pip-audit` pendientes de ejecución con red. |
| T4.2 Prueba de humo | HECHO | En el contenedor: `uvicorn auth_api:app` (127.0.0.1:8000) + `streamlit run app.py` (127.0.0.1:8501) con SQLite persistente. Verificado: `/_stcore/health` 200; login incorrecto muestra "Credenciales inválidas"; login correcto autentica con rol y `session_id`; restauración con token firmado; rechazo de payload sin firma; rechazo de token tras sesión desplazada; logout; cierre por inactividad; navegación entre los 5 grupos; analista ve Configuración en solo lectura; plantilla Excel disponible. Con `AppTest` se renderizaron las 15 vistas (login, sin datos y 13 módulos) con `Transacciones_AML_200.xlsx` y un nombre de usuario `<script>alert(1)</script>`: 0 excepciones y el script aparece escapado. Exportar/importar `.saml` cubierto por `tests/test_saml.py` (ida y vuelta). Pendiente de verificación en navegador real: carga de archivos con XSRF (comportamiento estándar de Streamlit). |
| T4.3 Duplicación | HECHO | `scripts/medir_duplicacion.py` (ventanas de 6 líneas normalizadas): **2.10 %** (7,433 líneas, 156 duplicadas) frente a 2.50 % en `main`. Umbral 10 %. |
| T4.4 Informe | HECHO | Este documento. |

---

## 4. Variables de entorno nuevas o requeridas

| Variable | Obligatoria | Descripción |
|----------|-------------|-------------|
| `SESSION_SIGN_KEY` | Sí (32+ caracteres) | Firma de tokens de restauración y derivación de la clave del caché cifrado. Si falta o es corta: restauración y caché deshabilitados, se registra un warning. |
| `CACHE_ENCRYPTION_SALT` | Recomendada | Sal de derivación de la clave del caché (valor estable; por defecto `sovereign-aml-cache`). |
| `JWT_ISSUER` | Recomendada | Claim `iss` (por defecto `sovereign-aml-auth`). |
| `JWT_AUDIENCE` | Recomendada | Claim `aud` (por defecto `sovereign-aml-app`). |
| `SECRET_KEY` | Sí (ya existente) | Firma JWT. |

`.env.example` y `scripts/generate_env.py` ya las incluyen.

## 5. Pasos de despliegue

1. **Antes de fusionar:** verificar en Railway (servicio único) que `SESSION_SIGN_KEY` y `SECRET_KEY` existen y tienen 32+ caracteres aleatorios. Añadir `CACHE_ENCRYPTION_SALT`, `JWT_ISSUER` y `JWT_AUDIENCE` (opcionales pero recomendadas).
2. **Migración 003:** ejecutar `python scripts/db_migrate.py` contra la base de producción (idempotente) o aplicar `migrations/003_rol_licencias.sql`. Todas las licencias quedan como `analista`; asignar el rol administrador:
   `UPDATE public."Licencias" SET rol = 'admin' WHERE "User" = '<usuario_admin>';`
   Sin este paso nadie podrá administrar licencias por la API (403).
3. **Dependencias:** `cryptography` es nueva en `requirements.txt` (Dockerfile la instala). En local: `pip install -r requirements.txt` dentro de `aml_env`.
4. **Tokens JWT existentes** dejan de ser válidos al desplegar (nuevos claims obligatorios); los usuarios deben iniciar sesión de nuevo. Las sesiones guardadas en `localStorage` con el formato antiguo se descartan automáticamente.
5. Revisar la rama, ejecutar `pytest`, `bandit` y `pip-audit` con red, y fusionar a `main` (Railway redepliega en cada push).

## 6. Riesgos residuales

- **Restauración de sesión en `localStorage`:** el token sigue viajando en la URL una vez y se guarda en `localStorage`; ahora expira en 30 minutos, está ligado a la sesión vigente y no contiene datos personales, pero un XSS futuro podría reutilizarlo durante su vigencia. Mitigación adicional posible: `sessionStorage` (pierde la restauración en pestañas nuevas) o cookie `HttpOnly` servida por la API.
- **Límite de intentos en memoria:** válido para un worker (configuración actual de Railway). Con varios workers migrar a Redis.
- **Bitácora de sesiones (`BitacoraSesions.last_activity`)** sigue siendo `timestamp` sin zona; se escriben valores UTC, coherentes con el contenedor (UTC).
- **`bandit`/`pip-audit` no ejecutados** en esta iteración por falta de red; se dejan los comandos en README.
- **CORS de Streamlit** se fuerza a `true` por exigencia de XSRF (comportamiento de Streamlit); la cookie `_streamlit_xsrf` protege las mutaciones. La API mantiene `CORS_ALLOWED_ORIGINS`.
- **Cabeceras de seguridad (S-14):** no se abordan en código (Streamlit no las emite); configurar CSP, HSTS, `X-Frame-Options` y `Referrer-Policy` en el proxy de Railway o un reverse proxy.

## 7. Fase posterior recomendada

- **MFA (TOTP con `pyotp`):** columna `totp_secret` cifrada en `Licencias`, enrolamiento con QR en `/perfil`, verificación del código tras la contraseña en `/auth/validate` y `/token`, códigos de respaldo; obligatorio para `admin` y `oficial`.
- Completar T3.1 (estilos inline restantes) y T3.7 (moneda en PDF): **hecho en Fase 2 (T9, `1aedba4`)**, ver `INFORME_FASE2_2026-09.md`.
- Cabeceras de seguridad en el proxy (S-14).
- Cambio de contraseña por el propio usuario y expiración periódica (S-11).
