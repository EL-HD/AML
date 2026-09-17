# Plan Fase 2: Cumplimiento, Seguridad y Analítica · Sovereign AML

**Fecha:** 17/09/2026 · **Diseño:** Claude Opus 5 · **Ejecución:** Fable 5, una tarea por agente, en orden.
**Rama:** `mejora/fase2-cumplimiento-2026-09` (sin push, sin merge, sin tocar Railway).

## Reglas comunes (obligatorias para cada tarea)
1. Código en el equipo del usuario: `device_bash`, carpeta `$HOME/mnt/AML`. Editar in situ con scripts python o sed; nunca reescribir archivos desde salida truncada.
2. Pruebas en el contenedor cloud: empaquetar el árbol con `git ls-files -co --exclude-standard` + `tar` dentro de `.aml/`, stagear con `device_stage_files` y extraer. En el contenedor ya existe `/home/claude/pylib` (streamlit, fastapi, sqlalchemy, etc.), `/home/claude/shims` y `/home/claude/env.sh`; PYTHONPATH=/home/claude/pylib:/home/claude/shims:<raíz extraída>. PyPI está bloqueado: no se pueden instalar paquetes nuevos; toda dependencia nueva debe ser opcional o de biblioteca estándar, o quedar documentada como pendiente. PostgreSQL 16 está instalado en el contenedor (`service postgresql start`, usuario postgres/pw) pero sin driver psycopg2: validar SQL con `psql`.
3. Pruebas con `python3 -m unittest discover -s tests` (70 pruebas actuales deben seguir en verde) + prueba de humo con `/home/claude/apptest_smoke.py` cuando la tarea toque UI.
4. Commit por tarea (Conventional Commits en español) solo con los archivos propios de la tarea (`git add <rutas>`, nunca `git add -A`): puede haber otra sesión editando. Pie de commit:
   `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`
5. PROHIBIDO: git push, merge a main, modificar `.env`, `backend/procesador.py` (salvo T8 como capa separada), `backend/riesgo_ldft_logic.py`, migraciones existentes 001-003.
6. OWASP Top 10, validaciones explícitas, sin `except: pass`, duplicación < 10 %, sin guiones largos ni emojis, textos en español profesional.
7. Migraciones nuevas: `migrations/00N_*.sql` idempotentes (IF NOT EXISTS), aplicadas por `scripts/db_migrate.py` al arrancar. Tablas multi-tenant con `licenciaid` y todas las consultas filtradas por él (anti IDOR).
8. Al terminar, añadir una sección a `docs/planes/INFORME_FASE2_2026-09.md` (HECHO/PARCIAL/PENDIENTE, commit, evidencia, variables nuevas, pasos de despliegue).

## Tareas (orden de prioridad)
- **T1 Persistencia de casos (Art. 29, 30 y 34 Ley 6593).** Tabla `CasosAlerta` (licenciaid, clave estable del caso: cliente + hash del lote/archivo, estado, fundamento, score, usuario, fechas) e historial `CasosAlertaHistorial` (append-only). Flujo cuatro ojos: analista propone "Sospechosa_Confirmada"; solo oficial/admin aprueba; quien propone no puede aprobar. Al cargar un análisis se rehidratan estados guardados. Retención mínima 5 años (sin borrado desde la UI). Auditoría CAMBIO_ESTADO_CASO.
- **T2 CI en GitHub Actions.** `.github/workflows/ci.yml`: Python 3.11, instala requirements, `python -m unittest discover -s tests`, `bandit -r backend frontend auth_api.py app.py -ll`, `pip-audit -r requirements.txt`, medición de duplicación. Documentar cómo activar "Wait for CI" en Railway. Sin secretos en el workflow; permisos mínimos (`contents: read`).
- **T3 Screening de listas de sanciones (GAFI R.6/R.7).** Módulo `backend/screening.py`: normalización de nombres (acentos, orden, tokens), similitud con `difflib`/Jaro-Winkler propio, umbral configurable, resultado explicable. Carga de listas OFAC SDN (CSV) y ONU consolidada (XML) desde archivo subido por admin y, opcionalmente, descarga programada con verificación de host fijo y tamaño máximo (sin SSRF). Tabla de coincidencias con revisión humana (descartar/confirmar con fundamento). Vista en UI para admin/oficial; integrar señal en ficha de cliente.
- **T4 Bitácora a prueba de alteraciones.** Columnas `hash_prev` y `hash` (SHA-256 encadenado por licenciaid) en `BitacoraAuditoria` mediante migración; función de verificación de integridad y vista para auditor/admin que reporte la primera ruptura. Considerar concurrencia (bloqueo por licenciaid).
- **T5 Cabeceras de seguridad.** Caddy o reverse proxy en el contenedor delante de Streamlit con CSP compatible con Streamlit, HSTS, X-Frame-Options/frame-ancestors, Referrer-Policy, Permissions-Policy, X-Content-Type-Options. Si no se puede descargar Caddy en la imagen, alternativa en Python (proxy ASGI con websockets) documentando el trade-off. Mantener healthcheck.
- **T6 MFA TOTP (RFC 6238) para admin y oficial** implementado con biblioteca estándar (hmac/base64/struct), enrolamiento con secreto cifrado, códigos de recuperación hasheados, ventana ±1, anti-replay.
- **T7 Respaldos.** Script de `pg_dump` cifrado con retención y guía de restauración probada; opción de servicio cron en Railway documentada.
- **T8 Detección de anomalías.** Capa separada `backend/anomalias.py` (sin tocar procesador.py) con Isolation Forest si sklearn existe, o z-score robusto (MAD) como fallback; explicación por variable; se muestra como señal complementaria, no altera el score IMPERATOR.
- **T9 Pendientes UI.** Moneda configurable en PDFs y ejes; reducir estilos inline restantes.
