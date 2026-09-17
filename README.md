# SOVEREIGN AML: Intelligence Platform

Plataforma de inteligencia de negocio (BI) y cumplimiento normativo contra el Lavado de Dinero, Financiamiento del Terrorismo y de la Proliferación de Armas de Destrucción Masiva (LD/FT/FPADM), alineada con la **Iniciativa de Ley 6593** (Guatemala), las **40 Recomendaciones del GAFI** y el modelo de administración de riesgo institucional **GAFILAT / IVE**.

Motor analítico propio: **IMPERATOR** (scoring de riesgo por transacción/cliente, basado en ISO 31000, COSO ERM y el enfoque basado en riesgo: RBA: del GAFI).

---

## 1. Arquitectura

Un único servicio en Railway ejecuta dos procesos bajo `supervisord`:

```
┌─────────────────────────────────────────────┐
│  Contenedor (Dockerfile, Railway)            │
│                                               │
│   supervisord                                │
│   ├── fastapi   (auth_api.py)  → 127.0.0.1:8000  (interno)
│   └── streamlit (app.py)       → 0.0.0.0:$PORT   (público)
│                                               │
└─────────────────┬─────────────────────────────┘
                   │ SQLAlchemy
                   ▼
          PostgreSQL (servicio Railway separado)
```

* **`auth_api.py`** (FastAPI): autenticación (JWT, rate limiting), CRUD de licencias/usuarios. Solo accesible en `127.0.0.1`: nunca expuesto directamente a internet.
* **`app.py`** (Streamlit): interfaz principal, enruta a los módulos de `frontend/`.
* **PostgreSQL**: una tabla `Licencias` por Persona Obligada (multi-tenant vía `licenciaid`/`licence_id` UUID). El resto de las tablas de negocio se segmentan por ese mismo `licenciaid`.
* Algunos módulos de frontend (p. ej. `mod_sesion.py`, `mod_riesgo_ldft.py`) abren su propia `SessionLocal()` (ver `backend/database.py`) para leer/escribir datos que no pasan por la API de autenticación: mismo patrón, sin duplicar lógica de conexión.

### Despliegue
* **Railway** (`railway.toml`): build vía `Dockerfile`, `startCommand = supervisord -c /app/supervisord.conf`.
* **Git**: repo `EL-HD/AML`, rama `main`: Railway redepliega automáticamente en cada push.
* Workflow operativo: cambios vía Claude (GitKraken MCP para commit/push, conector Railway MCP para verificar logs/deploys/variables).

---

## 2. Módulos (`frontend/`)

| Módulo | Función |
|--------|---------|
| `mod_sesion.py` | Login, control de sesión única, bitácora de auditoría (Art. 19 Ley 6593). |
| `mod_resumen.py` | Resumen ejecutivo: KPIs de riesgo y de cumplimiento (Arts. 28-30 Ley 6593). |
| `mod_transacciones.py` | Listado de transacciones, detección de RTE (efectivo ≥ USD 10,000, Art. 31). |
| `mod_alertas.py` | Ciclo de vida de casos: Inusual → Examinada → Sospechosa → RTS (Arts. 28-30). |
| `mod_cliente.py` | Ficha de cliente, PEP/CPE, Beneficiario Final (UBO, Art. 21). |
| `mod_red_transaccional.py` | Grafo de flujos de dinero: layering, cuentas puente, ciclos. |
| `mod_matrices.py` | Glosario y matrices de score (S_T, S_C, S_B, S_N). |
| `mod_mitigacion.py` | Catálogo de acciones de mitigación (Preventivas/Correctivas/Regulatorias/Estratégicas/KYC). |
| `mod_imperator_diagnostics.py` | Calibración de reglas, explicabilidad del score, pruebas de estrés. |
| `mod_reportes.py` | Generación de PDFs regulatorios: RTS (Art. 30), RTE (Art. 31), reportes ejecutivos. |
| `mod_configuracion.py` | Parámetros del sistema, política de retención de datos (Art. 34, mínimo 5 años). |
| `mod_ubicaciones.py` | Gestión de ubicaciones/geografía de riesgo. |
| `mod_manual.py` | Manual de usuario in-app (este documento tiene su equivalente técnico aquí). |
| `mod_riesgo_ldft.py` | **Riesgo Institucional de LD/FT/FPADM** (GAFILAT/IVE): ver sección 3. |
| `mod_utils.py` | Helpers compartidos de renderizado (`render_html_table`, `plotly_dark_layout`). |

## 3. Backend (`backend/`)

| Archivo | Función |
|---------|---------|
| `database.py` | Engine SQLAlchemy, `SessionLocal`, `get_db()`. `DATABASE_URL` desde env var (sin credenciales hardcodeadas). |
| `models.py` | Modelos ORM: `Licencia`, `BitacoraSesions`, `BitacoraAuditoria`, y las 5 tablas de Riesgo LD/FT (`RiesgoSegmentos`, `RiesgoEventos`, `RiesgoControles`, `RiesgoEventoControl`, `RiesgoPlanesAccion`). |
| `schemas.py` | Validación Pydantic: `Literal` para listas cerradas, rangos explícitos (`Field(ge=..., le=...)`). |
| `crud.py` | Acceso a datos de Licencias/autenticación. Hash bcrypt (`get_password_hash`/`verify_password`). |
| `crud_riesgo.py` | Acceso a datos del módulo de Riesgo LD/FT: todas las funciones filtran por `licenciaid` (previene IDOR). |
| `riesgo_ldft_logic.py` | Motor de cálculo **puro** (sin DB/Streamlit) del riesgo LD/FT: impacto, matriz de calor, ponderación de controles, riesgo residual. Ver docstring del módulo para los supuestos de ingeniería documentados. |
| `procesador.py` | Motor de scoring IMPERATOR (S_T, S_C, S_B, S_N) sobre el Excel de transacciones. |

## 4. Módulo de Riesgo Institucional LD/FT/FPADM

Implementación del enfoque basado en riesgo institucional (Art. 8-11 Decreto 15-2026, modelo GAFILAT/IVE: GERILAFT App), **complementario** al riesgo transaccional de IMPERATOR: mientras IMPERATOR evalúa el riesgo de cada transacción/cliente, este módulo evalúa el riesgo del **negocio como Persona Obligada** (segmentos, eventos, controles).

* **Documentación de referencia:** [`docs/base-conocimiento/ADR-LDFT-2026-GAFILAT-IVE.md`](docs/base-conocimiento/ADR-LDFT-2026-GAFILAT-IVE.md): resumen del documento fuente IVE analizado.
* **Migración de referencia:** `migrations/002_riesgo_ldft.sql` (las tablas se crean automáticamente vía `models.Base.metadata.create_all()` al iniciar `auth_api.py`).
* **Motor de cálculo:** `backend/riesgo_ldft_logic.py`: validado con pruebas unitarias contra los 3 ejemplos numéricos del documento fuente.
* **Utilidad de datos base:** `scripts/seed_licencias.py`: crea/restablece licencias (admin, invitado) de forma idempotente, sin contraseñas hardcodeadas (lee de variables de entorno `SEED_<USER>_PASSWORD`).

## 5. Seguridad (OWASP Top 10)

| Riesgo OWASP | Mitigación aplicada |
|---|---|
| A01: Broken Access Control | RBAC por rol (`admin`, `oficial`, `analista`, `auditor`): `/licencias/*` y `/usuarios/` solo `admin` (`auth_api.require_role`), `/perfil` con campos restringidos; `frontend/permisos.py` deshabilita controles según rol. Caché de análisis ligado al `licence_id` y cifrado (`frontend/cache_analisis.py`). Todas las consultas filtran por `licenciaid`. |
| A02: Cryptographic Failures | Contraseñas con bcrypt; `SECRET_KEY` obligatoria; restauración de sesión con token HMAC-SHA256 firmado, con expiración (30 min), nonce y validación contra la sesión vigente (`backend/session_token.py`, fail-closed sin `SESSION_SIGN_KEY`); JWT con `exp`, `iat`, `jti`, `iss`, `aud`. |
| A03: Injection | ORM con binding de parámetros; `Literal` de Pydantic para listas cerradas; todo valor dinámico en HTML pasa por `frontend/ui_safe.h` (prueba estática en `tests/test_ui_safe.py`); saneado anti-inyección de fórmulas centralizado en `frontend/exportacion.py`. |
| A05: Security Misconfiguration | Protección XSRF de Streamlit activa y configuración versionada en `.streamlit/config.toml` (subida máxima 25 MB); CORS de la API restringido por `CORS_ALLOWED_ORIGINS`; versiones exactas en `requirements.txt`; importación `.saml` con límites de tamaño, filas y lista blanca de configuración (`backend/config_aml.AmlConfig`). |
| A07: Identification & Auth Failures | Límite de intentos por usuario e IP real (5 fallos / 5 min, bloqueo 15 min) en `/auth/validate` y `/token`; mensaje único "Credenciales inválidas"; política de contraseñas (12+, complejidad, lista de comunes); control de sesión única vía `BitacoraSesions`. MFA (TOTP) planificado como fase posterior. |
| A09: Security Logging | `backend/auditoria.py` registra en `BitacoraAuditoria` (UTC) accesos a módulos, LOGIN_OK, LOGIN_FALLIDO, LOGOUT, EXPORTACION, IMPORTACION y CAMBIO_CONFIG (Art. 19 Ley 6593); ningún fallo se silencia. |

## 6. Variables de entorno

| Variable | Obligatoria | Uso |
|----------|-------------|-----|
| `DATABASE_URL` o `DB_*` | Sí | PostgreSQL (SQLite solo para pruebas automatizadas). |
| `SECRET_KEY` | Sí | Firma de JWT (32+ bytes aleatorios). |
| `SESSION_SIGN_KEY` | Sí | Firma de la restauración de sesión y derivación de la clave del caché cifrado (32+ caracteres). Sin ella ambas funciones quedan deshabilitadas. |
| `CACHE_ENCRYPTION_SALT` | Recomendada | Sal para derivar la clave del caché de análisis. |
| `JWT_ISSUER`, `JWT_AUDIENCE` | Recomendadas | Claims `iss`/`aud` del JWT (por defecto `sovereign-aml-auth` / `sovereign-aml-app`). |
| `AUTH_API_URL` | Sí (Streamlit) | URL interna de la API (`http://localhost:8000` en Railway). |
| `CORS_ALLOWED_ORIGINS` | Recomendada | Orígenes permitidos por la API. |
| `SCREENING_AUTO_DOWNLOAD` | No (por defecto `false`) | Habilita la descarga de listas de sanciones desde las URLs oficiales fijas (OFAC, ONU) definidas en `backend/screening.py`. La carga manual por el Administrador funciona siempre. |

## 7. Pruebas y calidad

```bash
python -m unittest discover -s tests -v        # también funciona con: pytest tests
python scripts/medir_duplicacion.py            # duplicación de código (< 10 %)
bandit -r backend frontend auth_api.py app.py  # análisis estático de seguridad
pip-audit -r requirements.txt                  # vulnerabilidades en dependencias
```

### Integración continua (GitHub Actions)

`.github/workflows/ci.yml` se ejecuta en cada push y pull request hacia `main` y `mejora/**`, con permisos mínimos (`contents: read`), sin secretos y con variables ficticias de prueba. Dos trabajos:

* **calidad**: Python 3.11 con caché de pip, `unittest`, `bandit -c bandit.yaml ... -ll` (severidad media o superior; `bandit.yaml` excluye `tests/`), `pip-audit -r requirements.txt` y `scripts/medir_duplicacion.py --umbral 10`.
* **migraciones**: servicio `postgres:16` efímero; ejecuta `scripts/db_migrate.py` dos veces sobre una base vacía (la segunda debe terminar sin SQL pendiente) y verifica `schema_migrations`, la columna `Licencias.rol` y su CHECK.

Las acciones están fijadas a versión mayor; Dependabot (`.github/dependabot.yml`) propone actualizaciones para pasar a SHA fijados.

**Desplegar en Railway solo si CI pasa ("Wait for CI").** Railway puede esperar a que los *check suites* de GitHub terminen en verde antes de construir. Activación manual (no se cambia desde el repositorio):

1. Railway > proyecto > servicio de la aplicación > **Settings** > sección **Source** (repositorio `EL-HD/AML`, rama `main`).
2. Activar **Wait for CI** (en algunas versiones del panel aparece como *Check Suites*).
3. A partir de entonces, cada push a `main` solo despliega cuando el workflow `CI` finaliza con éxito; si falla, Railway omite el despliegue y conserva el anterior.

## 8. Levantar el sistema en local (comando `aml`)

Requiere: Postgres local ya corriendo (Homebrew/DBeaver/pgAdmin, base `AML` en `localhost:5432`), Python 3.10+.

```bash
./aml up             # 1ra vez: crea .env (edítalo con tus credenciales) y venv; luego migra y levanta API+Streamlit
./aml migrate         # aplica migrations/*.sql + tablas ORM sin levantar servicios
./aml seed            # catálogos globales + licencia de prueba
./aml dump            # backup de la base local -> backups/
./aml restore <file>  # restaura un .dump en la base local
./aml railway-pull    # dump de producción (Railway) -> backups/ (requiere proxy TCP temporal, ver script)
./aml status | down   # estado / detener API+Streamlit (Postgres no se toca, es tuyo)
```

`.env`, `backups/` y `.aml/` (logs/pids) quedan fuera de git. Detalle en `scripts/`.

## 9. Historial de cambios recientes

* **2026-09**: Plan UI/UX y seguridad (ver `docs/planes/`): restauración de sesión firmada y expirable, caché cifrado por tenant, RBAC con migración `003_rol_licencias.sql`, XSRF activo, escape HTML universal, límites de importación, política de contraseñas, auditoría completa, sistema de diseño con tokens y navegación agrupada.

* **2026-07**: Módulo de Riesgo Institucional LD/FT/FPADM (GAFILAT/IVE) agregado end-to-end.
* **2026-07**: Fix: `pandas.DataFrame.applymap` eliminado en pandas 3.0 → migrado a `.map()`; `requirements.txt` fija piso `pandas>=2.1.0`.
* **2026-07**: Fix: `StreamlitDuplicateElementId` en mapa de calor (gráficos duplicados por renderizado de `st.tabs`): `key` explícito por pestaña.
* **2026-09**: Comando `aml` (orquestador local): levanta Postgres/migraciones/API/Streamlit con un solo comando; `aml dump`/`aml restore`/`aml railway-pull` para respaldos.
* **2026-07**: Firma institucional estandarizada: "Ing. Hobéd Díaz M.A. M.A.F.I." (M.A. = Magíster Artium, término correcto en Guatemala: no equivalente a "Msc.").

---

*SOVEREIGN AML v3.0 · Ing. Hobéd Díaz M.A. M.A.F.I.*
