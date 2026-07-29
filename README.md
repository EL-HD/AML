# SOVEREIGN AML — Intelligence Platform

Plataforma de inteligencia de negocio (BI) y cumplimiento normativo contra el Lavado de Dinero, Financiamiento del Terrorismo y de la Proliferación de Armas de Destrucción Masiva (LD/FT/FPADM), alineada con la **Iniciativa de Ley 6593** (Guatemala), las **40 Recomendaciones del GAFI** y el modelo de administración de riesgo institucional **GAFILAT / IVE**.

Motor analítico propio: **IMPERATOR** (scoring de riesgo por transacción/cliente, basado en ISO 31000, COSO ERM y el enfoque basado en riesgo — RBA — del GAFI).

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

* **`auth_api.py`** (FastAPI): autenticación (JWT, rate limiting), CRUD de licencias/usuarios. Solo accesible en `127.0.0.1` — nunca expuesto directamente a internet.
* **`app.py`** (Streamlit): interfaz principal, enruta a los módulos de `frontend/`.
* **PostgreSQL**: una tabla `Licencias` por Persona Obligada (multi-tenant vía `licenciaid`/`licence_id` UUID). El resto de las tablas de negocio se segmentan por ese mismo `licenciaid`.
* Algunos módulos de frontend (p. ej. `mod_sesion.py`, `mod_riesgo_ldft.py`) abren su propia `SessionLocal()` (ver `backend/database.py`) para leer/escribir datos que no pasan por la API de autenticación — mismo patrón, sin duplicar lógica de conexión.

### Despliegue
* **Railway** (`railway.toml`): build vía `Dockerfile`, `startCommand = supervisord -c /app/supervisord.conf`.
* **Git**: repo `EL-HD/AML`, rama `main` — Railway redepliega automáticamente en cada push.
* Workflow operativo: cambios vía Claude (GitKraken MCP para commit/push, conector Railway MCP para verificar logs/deploys/variables).

---

## 2. Módulos (`frontend/`)

| Módulo | Función |
|--------|---------|
| `mod_sesion.py` | Login, control de sesión única, bitácora de auditoría (Art. 19 Ley 6593). |
| `mod_resumen.py` | Resumen ejecutivo — KPIs de riesgo y de cumplimiento (Arts. 28-30 Ley 6593). |
| `mod_transacciones.py` | Listado de transacciones, detección de RTE (efectivo ≥ USD 10,000, Art. 31). |
| `mod_alertas.py` | Ciclo de vida de casos: Inusual → Examinada → Sospechosa → RTS (Arts. 28-30). |
| `mod_cliente.py` | Ficha de cliente, PEP/CPE, Beneficiario Final (UBO, Art. 21). |
| `mod_red_transaccional.py` | Grafo de flujos de dinero — layering, cuentas puente, ciclos. |
| `mod_matrices.py` | Glosario y matrices de score (S_T, S_C, S_B, S_N). |
| `mod_mitigacion.py` | Catálogo de acciones de mitigación (Preventivas/Correctivas/Regulatorias/Estratégicas/KYC). |
| `mod_imperator_diagnostics.py` | Calibración de reglas, explicabilidad del score, pruebas de estrés. |
| `mod_reportes.py` | Generación de PDFs regulatorios: RTS (Art. 30), RTE (Art. 31), reportes ejecutivos. |
| `mod_configuracion.py` | Parámetros del sistema, política de retención de datos (Art. 34, mínimo 5 años). |
| `mod_ubicaciones.py` | Gestión de ubicaciones/geografía de riesgo. |
| `mod_manual.py` | Manual de usuario in-app (este documento tiene su equivalente técnico aquí). |
| `mod_riesgo_ldft.py` | **Riesgo Institucional de LD/FT/FPADM** (GAFILAT/IVE) — ver sección 3. |
| `mod_utils.py` | Helpers compartidos de renderizado (`render_html_table`, `plotly_dark_layout`). |

## 3. Backend (`backend/`)

| Archivo | Función |
|---------|---------|
| `database.py` | Engine SQLAlchemy, `SessionLocal`, `get_db()`. `DATABASE_URL` desde env var (sin credenciales hardcodeadas). |
| `models.py` | Modelos ORM: `Licencia`, `BitacoraSesions`, `BitacoraAuditoria`, y las 5 tablas de Riesgo LD/FT (`RiesgoSegmentos`, `RiesgoEventos`, `RiesgoControles`, `RiesgoEventoControl`, `RiesgoPlanesAccion`). |
| `schemas.py` | Validación Pydantic — `Literal` para listas cerradas, rangos explícitos (`Field(ge=..., le=...)`). |
| `crud.py` | Acceso a datos de Licencias/autenticación. Hash bcrypt (`get_password_hash`/`verify_password`). |
| `crud_riesgo.py` | Acceso a datos del módulo de Riesgo LD/FT — todas las funciones filtran por `licenciaid` (previene IDOR). |
| `riesgo_ldft_logic.py` | Motor de cálculo **puro** (sin DB/Streamlit) del riesgo LD/FT: impacto, matriz de calor, ponderación de controles, riesgo residual. Ver docstring del módulo para los supuestos de ingeniería documentados. |
| `procesador.py` | Motor de scoring IMPERATOR (S_T, S_C, S_B, S_N) sobre el Excel de transacciones. |

## 4. Módulo de Riesgo Institucional LD/FT/FPADM

Implementación del enfoque basado en riesgo institucional (Art. 8-11 Decreto 15-2026, modelo GAFILAT/IVE — GERILAFT App), **complementario** al riesgo transaccional de IMPERATOR: mientras IMPERATOR evalúa el riesgo de cada transacción/cliente, este módulo evalúa el riesgo del **negocio como Persona Obligada** (segmentos, eventos, controles).

* **Documentación de referencia:** [`docs/base-conocimiento/ADR-LDFT-2026-GAFILAT-IVE.md`](docs/base-conocimiento/ADR-LDFT-2026-GAFILAT-IVE.md) — resumen del documento fuente IVE analizado.
* **Migración de referencia:** `migrations/002_riesgo_ldft.sql` (las tablas se crean automáticamente vía `models.Base.metadata.create_all()` al iniciar `auth_api.py`).
* **Motor de cálculo:** `backend/riesgo_ldft_logic.py` — validado con pruebas unitarias contra los 3 ejemplos numéricos del documento fuente.
* **Utilidad de datos base:** `scripts/seed_licencias.py` — crea/restablece licencias (admin, invitado) de forma idempotente, sin contraseñas hardcodeadas (lee de variables de entorno `SEED_<USER>_PASSWORD`).

## 5. Seguridad (OWASP Top 10)

| Riesgo OWASP | Mitigación aplicada |
|---|---|
| A01 — Broken Access Control | Todas las consultas de datos sensibles filtran por `licenciaid`; verificación de propiedad antes de vincular/eliminar registros (ver `crud_riesgo.py`). |
| A02 — Cryptographic Failures | Contraseñas con bcrypt (`bcrypt.gensalt()`); `SECRET_KEY` obligatoria por env var (falla al arrancar si no está configurada). |
| A03 — Injection | ORM con binding de parámetros (sin SQL crudo concatenado); `Literal` de Pydantic para listas cerradas; escape HTML explícito antes de interpolar datos de usuario en `unsafe_allow_html`; saneado anti-inyección de fórmulas (CSV/Excel) con prefijo `'`. |
| A05 — Security Misconfiguration | CORS restringido por `CORS_ALLOWED_ORIGINS` (no wildcard); dependencias con piso de versión fijado en `requirements.txt`. |
| A07 — Identification & Auth Failures | Rate limiting en `/auth/validate` (5 intentos / 5 min por IP); control de sesión única vía `BitacoraSesions`. |
| A09 — Security Logging | `BitacoraAuditoria` registra accesos a módulos sensibles (Art. 19 Ley 6593). |

## 6. Historial de cambios recientes

* **2026-07** — Módulo de Riesgo Institucional LD/FT/FPADM (GAFILAT/IVE) agregado end-to-end.
* **2026-07** — Fix: `pandas.DataFrame.applymap` eliminado en pandas 3.0 → migrado a `.map()`; `requirements.txt` fija piso `pandas>=2.1.0`.
* **2026-07** — Fix: `StreamlitDuplicateElementId` en mapa de calor (gráficos duplicados por renderizado de `st.tabs`) — `key` explícito por pestaña.
* **2026-07** — Firma institucional estandarizada: "Ing. Hobéd Díaz M.A. M.A.F.I." (M.A. = Magíster Artium, término correcto en Guatemala — no equivalente a "Msc.").

---

*SOVEREIGN AML v3.0 · Ing. Hobéd Díaz M.A. M.A.F.I.*
