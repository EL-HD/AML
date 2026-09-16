# Plan de Trabajo: UI/UX y Seguridad · Sovereign AML

**Fecha:** 16/09/2026 · **Diseño:** Claude Opus 5 (auditoría) · **Ejecución:** Fable 5 (agente)
**Alcance:** solo UI/UX y seguridad. No se modifica la lógica de scoring IMPERATOR ni el motor LD/FT.
**Rama de trabajo:** `mejora/uiux-seguridad-2026-09` (NUNCA commit directo a `main`: Railway redepliega en cada push).

---

## 1. Hallazgos de la auditoría

### 1.1 Seguridad (priorizado por severidad, referencia OWASP Top 10 2021)

| ID | Sev. | OWASP | Hallazgo | Evidencia |
|----|------|-------|----------|-----------|
| S-01 | CRÍTICA | A07 / A01 | **Bypass de autenticación por restauración de sesión.** Si `SESSION_SIGN_KEY` no está definida, `_decode_session_payload` acepta base64 sin firma: cualquiera puede abrir `?restore_session=1&restore_payload=<base64 de {"licence_id": "...", ...}>` y entrar autenticado, suplantando cualquier tenant. | `app.py` L157-192, L217-229 |
| S-02 | CRÍTICA | A07 | Aun con firma, el payload **no expira, no tiene nonce y no se valida contra `BitacoraSesions`**: un payload capturado sirve para siempre (replay) y anula el control de sesión única. Además viaja en la URL (historial, logs de proxy, Referer) y en `localStorage` (robable por cualquier XSS). | `app.py` L241-327 |
| S-03 | ALTA | A01 | **IDOR entre tenants en caché de análisis.** El archivo `/tmp/sovereign_aml_cache/<uuid>.saml` (transacciones con PII) se carga con solo conocer el `analysis_cache` de la URL; no se liga al `licence_id` ni al usuario. Se guarda sin cifrar. | `app.py` L66-145 |
| S-04 | ALTA | A01 | **Sin control de acceso por rol (RBAC).** Cualquier licencia autenticada puede crear, listar, modificar y borrar TODAS las licencias (`/licencias/*`, `/usuarios/`). `LicenciaUpdate` permite cambiar `fecha_expiracion` propia. No existe campo `rol`. | `auth_api.py` L131-167, `backend/models.py` |
| S-05 | ALTA | A05 | **Protección XSRF de Streamlit desactivada** (`--server.enableXsrfProtection false`). | `supervisord.conf` |
| S-06 | ALTA | A03 | **XSS almacenado/reflejado:** 339 usos de `unsafe_allow_html=True` y solo 4 `escape()`. Datos de licencia (`name`, `mail`, `empresa`), `user_name`, y valores del Excel se interpolan sin escapar (p. ej. sidebar L570-578, bienvenida L1256, `mod_cliente.py`). Combinado con S-02, un XSS roba la sesión desde `localStorage`. | `app.py`, `frontend/*.py` |
| S-07 | MEDIA | A07 | Rate limiting débil: por IP, pero Streamlit llama al API desde `127.0.0.1`, así que todos los usuarios comparten el mismo contador (DoS de login) y no hay bloqueo por cuenta. `/token` no tiene límite. Mensajes distintos para "usuario no existe" y "contraseña incorrecta" (enumeración de usuarios). Sin timeout en `requests.post`. | `auth_api.py` L53-66, L118, `backend/crud.py` L72-84, `app.py` L513 |
| S-08 | MEDIA | A04 / A08 | Importación `.saml` sin límites: sin tope de tamaño descomprimido (zip bomb), sin límite de filas, y `config.json` se fusiona sin lista blanca de claves ni rangos (mass assignment; `int()` puede lanzar excepción no controlada). | `frontend/mod_sesion.py`, `app.py` L1310-1330 |
| S-09 | MEDIA | A03 | **Inyección de fórmulas (CSV/Excel injection)** en exportaciones: valores que inician con `= + - @` no se neutralizan. | `mod_sesion.exportar_sesion`, `mod_reportes.py` |
| S-10 | MEDIA | A09 | Fallos de auditoría (Art. 19 Ley 6593) se silencian con `except: pass`; no hay log. No se auditan login fallido, logout, exportaciones ni cambios de configuración. | `frontend/mod_sesion.py` L33-55 |
| S-11 | MEDIA | A07 | Política de contraseñas mínima (solo 8 caracteres), sin MFA, sin expiración, enlace "¿Olvidó su contraseña?" es `href="#"`. | `backend/schemas.py`, `app.py` L529 |
| S-12 | MEDIA | A06 | Dependencias sin fijar (`>=`), sin `pip-audit` en CI. `python-multipart`, `PyJWT`, `streamlit` requieren versiones mínimas seguras. | `requirements.txt` |
| S-13 | BAJA | A05 | Higiene de repositorio: 36 archivos `__pycache__` y `backup_dark_fintech/` versionados en git; `Procfile` expone uvicorn en `0.0.0.0` (contradice la arquitectura). Datos de prueba `.xlsx` en el repo. | `git ls-files` |
| S-14 | BAJA | A05 | Sin cabeceras de seguridad (CSP, HSTS, X-Frame-Options, Referrer-Policy). Streamlit no las emite. | Despliegue Railway |
| S-15 | BAJA | A02 | `datetime.now()` sin zona horaria en bitácoras: afecta la trazabilidad forense. JWT sin `iat`, `jti`, `iss`, `aud`. | `backend/crud.py`, `auth_api.py` |

**Acción manual inmediata (antes de cualquier cambio de código):** verificar en Railway que `SESSION_SIGN_KEY` y `SECRET_KEY` existen y son de 32+ bytes aleatorios. Si `SESSION_SIGN_KEY` no existe, S-01 está explotable HOY en producción.

### 1.2 UI/UX

| ID | Prioridad | Hallazgo |
|----|-----------|----------|
| U-01 | ALTA | ~500 líneas de CSS embebidas en `app.py` + estilos inline en 339 bloques HTML. No hay tokens de diseño; los colores (`#f59e0b`, `#171c23`, `#d8c3ad`...) se repiten a mano. Duplicación muy por encima del 10% permitido. |
| U-02 | ALTA | Navegación plana de 13 opciones en un `st.radio`. Sin agrupación por flujo de trabajo del Oficial de Cumplimiento. |
| U-03 | ALTA | Inconsistencia visual: `render_html_table` pinta tablas **blancas** dentro de un tema oscuro. |
| U-04 | ALTA | Accesibilidad (WCAG 2.1 AA): etiquetas de inputs ocultas (`stWidgetLabel display:none`), fuentes de 0.6rem (~9.6 px), textos `rgba(...,0.4)` con contraste insuficiente, el estado se comunica solo con color (puntos verde/ámbar). |
| U-05 | MEDIA | Elementos engañosos o poco profesionales para un producto regulado: indicador fijo "IMPERATOR ENGINE ACTIVE" (no refleja estado real), "ACCESO RESTRINGIDO - NIVEL 4 CID", "NORMATIVA SOVEREIGN-V3" (normativa inexistente), enlace de recuperación de contraseña sin función, `page_icon` emoji. |
| U-06 | MEDIA | Sidebar sobrecargado: tarjeta descriptiva, créditos del autor, parámetros, exportación y licencia compiten con la navegación. |
| U-07 | MEDIA | Rendimiento percibido: el `.saml` se regenera en cada rerun (sidebar), el logo se lee y codifica en base64 en cada render del login, `pd.read_excel` sin caché. |
| U-08 | MEDIA | Moneda inconsistente: "Umbral base: Q" en sidebar vs. RTE en USD 10,000. |
| U-09 | BAJA | Sin estados vacíos ni guías de primer uso por módulo; mensajes de error genéricos ("Error de conexión con la API"). |
| U-10 | BAJA | Sin plantilla descargable del Excel requerido; la lista de columnas se muestra como texto. |

---

## 2. Plan de ejecución (para Fable 5)

### Reglas de ejecución
1. Trabajar sobre la carpeta `AML` del equipo del usuario (vía `device_bash`, montada en `$HOME/mnt/AML`).
2. Crear rama `mejora/uiux-seguridad-2026-09` desde `main`. **No hacer `git push`.** Un commit por tarea (Conventional Commits en español).
3. La VM local no tiene red para `pip`. Para pruebas: copiar el código al contenedor cloud (`device_stage_files` de los `.py`), instalar `requirements.txt` + `pytest bandit pip-audit` ahí y ejecutar. Los cambios de código se hacen SIEMPRE en el equipo del usuario.
4. No tocar: `backend/procesador.py` (scoring), `backend/riesgo_ldft_logic.py`, migraciones existentes, `.env`.
5. Sin guiones largos en textos. Sin emojis. Código auditable: validaciones explícitas, sin `except: pass`.
6. Duplicación < 10%: toda operación repetida va a una función reutilizable.

### Fase 0 · Preparación (sin cambios funcionales)
- **T0.1** Crear rama. Añadir `tests/` con `conftest.py`.
- **T0.2** `git rm -r --cached` de `__pycache__/`, `backup_dark_fintech/` (se conserva en disco, sale del repo). Actualizar `.gitignore`.
- **T0.3** Eliminar `Procfile` o alinearlo a `127.0.0.1` (Railway usa Dockerfile).

### Fase 1 · Seguridad crítica (S-01 a S-06)
- **T1.1 (S-01, S-02)** Crear `backend/session_token.py`:
  - `firmar_restauracion(licence_id, session_id) -> str` con HMAC-SHA256, campos `lid`, `sid`, `iat`, `exp` (máx. 30 min), `nonce`.
  - `verificar_restauracion(token) -> dict | None`: rechaza si falta clave, firma inválida, expirado.
  - **Fail-closed:** si `SESSION_SIGN_KEY` falta, la restauración se DESHABILITA (y se registra warning); nunca se acepta payload sin firma.
  - El payload solo lleva identificadores, **no** `user_data`. Al restaurar, `user_data` se recarga desde BD y se valida que `sid` sea la sesión más reciente de esa licencia (reutilizar la lógica de `get_current_user`, extraída a `crud.sesion_vigente(db, sid)`).
  - Tras restaurar: rotar (nuevo token), limpiar query params (ya existe).
  - Pruebas: sin clave, firma alterada, expirado, sesión desplazada por otro login, caso válido.
- **T1.2 (S-03)** Ligar caché al tenant: nombre de archivo `<licence_id>_<cache_id>.saml`; `restore_analysis_cache` exige coincidencia con el `licence_id` autenticado. Cifrar con Fernet (`cryptography`) usando clave derivada de `SESSION_SIGN_KEY`. Permisos `0o600`. Prueba de acceso cruzado.
- **T1.3 (S-04)** RBAC mínimo:
  - Migración `003_rol_licencias.sql`: columna `rol VARCHAR(20) NOT NULL DEFAULT 'analista' CHECK (rol IN ('admin','oficial','analista','auditor'))`. Añadir a `models.Licencia` y `schemas`.
  - Dependencia `require_role(*roles)` en `auth_api.py`; `/licencias/*` y `/usuarios/` solo `admin`.
  - Quitar `fecha_expiracion` y `rol` de lo que un no-admin puede modificar.
  - Frontend: ocultar "Configuración" de parámetros sensibles a `analista`/`auditor` (función `puede(accion)` central en `frontend/permisos.py`).
  - Pruebas con `TestClient`: analista recibe 403.
- **T1.4 (S-05)** Quitar `--server.enableXsrfProtection false` de `supervisord.conf`; crear `.streamlit/config.toml` con `enableXsrfProtection = true`, `enableCORS = false`, `maxUploadSize = 25`, `toolbarMode = "minimal"`, `showErrorDetails = false`. Verificar que la carga de archivos sigue funcionando.
- **T1.5 (S-06)** Crear `frontend/ui_safe.py` con `h(valor) -> str` (escape) y `html_block(template, **valores)` que escapa todos los valores por defecto. Recorrer los 339 usos: todo valor dinámico debe pasar por `h()`. Añadir prueba que renderiza con `<script>` en nombre de cliente y verifica que sale escapado. Añadir chequeo `bandit` + un grep en tests que falle si aparece `unsafe_allow_html=True` con f-string sin `h(` (heurística documentada).

### Fase 2 · Seguridad media (S-07 a S-12)
- **T2.1 (S-07)** Rate limit por `username` + IP real (`X-Forwarded-For` enviado por Streamlit desde `st.context.headers`, validado). Bloqueo temporal de cuenta tras 5 fallos. Aplicar también a `/token`. Mensaje único "Credenciales inválidas". `timeout=10` en `requests.post`. Registrar intentos fallidos en auditoría.
- **T2.2 (S-08)** `.saml`: límite de tamaño comprimido (25 MB) y descomprimido (100 MB, verificando `ZipInfo.file_size` antes de leer), máx. 200,000 filas, lista blanca de claves de config con rangos (modelo Pydantic `AmlConfig`), rechazo de claves desconocidas. Mismo límite de filas para `.xlsx`.
- **T2.3 (S-09)** `sanitizar_celda()` en un único helper; aplicarlo en toda exportación CSV/XLSX.
- **T2.4 (S-10)** Reemplazar `except: pass` por `logger.exception` con contador; auditar LOGIN_OK, LOGIN_FALLIDO, LOGOUT, EXPORTACION, CAMBIO_CONFIG, IMPORTACION. Timestamps con `timezone.utc`.
- **T2.5 (S-11)** Política de contraseñas: mínimo 12, mayúscula, minúscula, número, símbolo, bloqueo de contraseñas comunes (lista local). Quitar el enlace falso "¿Olvidó su contraseña?" y reemplazarlo por texto "Contacte al administrador". Dejar documentado MFA (TOTP con `pyotp`) como fase posterior (no implementar ahora).
- **T2.6 (S-12, S-15)** Fijar versiones exactas en `requirements.txt` (las instaladas y probadas en el contenedor). Ejecutar `pip-audit` y `bandit -r backend frontend auth_api.py app.py`; corregir hallazgos HIGH. JWT con `iat`, `jti`, `iss`, `aud` y validación correspondiente.

### Fase 3 · UI/UX
- **T3.1 (U-01)** Sistema de diseño: `frontend/theme/tokens.py` (colores, espaciado, tipografía, radios) + `frontend/theme/styles.css` cargado una sola vez con `st.html`/`st.markdown`. Mover todo el CSS de `app.py` ahí. Componentes reutilizables en `frontend/ui_components.py`: `kpi_card`, `section_title`, `info_panel`, `status_badge`, `empty_state`, `page_header`. Reemplazar bloques inline repetidos por estos componentes (usan `ui_safe` por dentro).
- **T3.2 (U-02, U-06)** Navegación agrupada con `st.navigation` / `st.Page` (si la versión de Streamlit lo soporta; si no, `st.radio` por secciones):
  - **Monitoreo:** Resumen Ejecutivo, Casos de Alerta, Transacciones
  - **Investigación:** Análisis por Cliente, Red Transaccional
  - **Riesgo:** Matrices de Riesgo, Riesgo Institucional LD/FT, Imperator Diagnostics, Gestión de Ubicaciones, Acciones de Mitigación
  - **Reportería:** Informes y Reportes
  - **Administración:** Configuración (según rol), Manual de Usuario
  - Sidebar: licencia compacta arriba, navegación, exportación; créditos del autor movidos al Manual / pie discreto.
- **T3.3 (U-03)** `render_html_table` con paleta oscura coherente (o migrar a `st.dataframe` con `column_config` donde no haya problema de nitidez).
- **T3.4 (U-04)** Accesibilidad: labels visibles (o `aria-label`), tamaño mínimo 12 px, contraste AA verificado con script (ratio ≥ 4.5:1) para cada par de tokens texto/fondo; estados con texto + color.
- **T3.5 (U-05)** Login profesional: quitar "NIVEL 4 CID" y "NORMATIVA SOVEREIGN-V3"; aviso legal real ("Uso exclusivo de personal autorizado. Accesos registrados conforme a la normativa de prevención de LD/FT."). Indicador de motor basado en estado real (datos cargados / API disponible). `page_icon` con el logo.
- **T3.6 (U-07)** `@st.cache_data` para logo y lectura de Excel; generar `.saml` solo al pulsar "Preparar exportación".
- **T3.7 (U-08, U-10)** Moneda configurable (GTQ/USD) con formato único `fmt_moneda()`. Botón "Descargar plantilla Excel" con las columnas requeridas y una fila de ejemplo.
- **T3.8 (U-09)** Estados vacíos y mensajes de error accionables en cada módulo (usar `empty_state`).

### Fase 4 · Verificación y entrega
- **T4.1** `pytest` completo en verde; `bandit` sin HIGH; `pip-audit` sin vulnerabilidades conocidas o documentadas.
- **T4.2** Prueba de humo: levantar API + Streamlit en el contenedor cloud con PostgreSQL local (o SQLite si aplica) y verificar login, carga de `Transacciones_AML_200.xlsx`, navegación por todos los módulos, exportar/importar `.saml`, logout, timeout.
- **T4.3** Medir duplicación (`jscpd` o `pylint --disable=all --enable=duplicate-code`) < 10%.
- **T4.4** Informe final `docs/planes/INFORME_EJECUCION_2026-09.md`: tareas hechas, pendientes, riesgos, variables de entorno nuevas, pasos de despliegue (migración 003, variables Railway).

### Criterios de aceptación globales
- Ninguna restauración de sesión sin firma, sin expiración o con sesión desplazada.
- Ningún dato dinámico renderizado como HTML sin escape.
- Analista no puede administrar licencias (403).
- XSRF activo; carga de archivos funcional.
- UI con navegación agrupada, tokens únicos, contraste AA y sin textos engañosos.

### Variables de entorno nuevas / requeridas
`SESSION_SIGN_KEY` (obligatoria, 32+ bytes), `SECRET_KEY`, `JWT_ISSUER`, `JWT_AUDIENCE`, `CACHE_ENCRYPTION_SALT`.
