-- =============================================================
-- MIGRACIÓN 004: Casos de Alerta persistentes
-- Propósito : Persistir el ciclo de vida de los casos de alerta
--             (Inusual -> Sospechosa) con flujo de cuatro ojos e
--             historial append-only.
-- Base legal : Art. 29 (examen y fundamento), Art. 30 (RTS) y
--              Art. 34 (conservación mínima de 5 años) Ley 6593.
-- Ejecutar   : python scripts/db_migrate.py  (o psql -f)
-- Idempotente: puede ejecutarse varias veces sin efectos adversos.
-- Clave estable del caso (ver backend/casos_alerta.py):
--   hash_lote  = SHA-256 del lote canónico de transacciones
--   clave_caso = SHA-256 de "licenciaid|hash_lote|cliente_normalizado"
-- Retención  : ni CasosAlerta ni CasosAlertaHistorial admiten DELETE;
--              el historial tampoco admite UPDATE (triggers).
-- =============================================================

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ── Estado vigente del caso ───────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public."CasosAlerta" (
    id                              UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
    licenciaid                      UUID          NOT NULL,
    clave_caso                      VARCHAR(64)   NOT NULL,
    hash_lote                       VARCHAR(64)   NOT NULL,
    cliente                         VARCHAR(200)  NOT NULL,
    nombre_archivo                  VARCHAR(255),
    estado                          VARCHAR(40)   NOT NULL DEFAULT 'Inusual_Pendiente',
    fundamento                      VARCHAR(4000) NOT NULL DEFAULT '',
    score_max                       DOUBLE PRECISION,
    nivel_riesgo                    VARCHAR(30),
    propuesto_por                   VARCHAR(100),
    propuesto_en                    TIMESTAMP,
    aprobado_por                    VARCHAR(100),
    aprobado_en                     TIMESTAMP,
    fecha_clasificacion_sospechosa  DATE,
    creado_por                      VARCHAR(100)  NOT NULL,
    creado_en                       TIMESTAMP     NOT NULL DEFAULT NOW(),
    actualizado_por                 VARCHAR(100)  NOT NULL,
    actualizado_en                  TIMESTAMP     NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_casosalerta_licencia_clave UNIQUE (licenciaid, clave_caso),
    CONSTRAINT casosalerta_estado_check CHECK (
        estado IN ('Inusual_Pendiente','Inusual_Examinada','Sospechosa_Propuesta',
                   'Sospechosa_Confirmada','Descartada')
    )
);
CREATE INDEX IF NOT EXISTS "ix_public_CasosAlerta_licenciaid" ON public."CasosAlerta"(licenciaid);
CREATE INDEX IF NOT EXISTS idx_casosalerta_licencia_lote    ON public."CasosAlerta"(licenciaid, hash_lote);

-- ── Historial append-only ─────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public."CasosAlertaHistorial" (
    id               UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
    licenciaid       UUID          NOT NULL,
    caso_id          UUID          NOT NULL REFERENCES public."CasosAlerta"(id),
    estado_anterior  VARCHAR(40),
    estado_nuevo     VARCHAR(40)   NOT NULL,
    accion           VARCHAR(40)   NOT NULL,
    fundamento       VARCHAR(4000) NOT NULL DEFAULT '',
    usuario          VARCHAR(100)  NOT NULL,
    rol              VARCHAR(20)   NOT NULL,
    registrado_en    TIMESTAMP     NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS "ix_public_CasosAlertaHistorial_licenciaid" ON public."CasosAlertaHistorial"(licenciaid);
CREATE INDEX IF NOT EXISTS "ix_public_CasosAlertaHistorial_caso_id"    ON public."CasosAlertaHistorial"(caso_id);
CREATE INDEX IF NOT EXISTS idx_casosalertahist_licencia_caso          ON public."CasosAlertaHistorial"(licenciaid, caso_id);

-- ── Protección de retención (Art. 34): sin DELETE; historial sin UPDATE ──
CREATE OR REPLACE FUNCTION public.fn_casos_alerta_inmutable() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'Operación % no permitida en %: registro protegido por retención (Art. 34 Ley 6593)',
        TG_OP, TG_TABLE_NAME;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_casosalerta_sin_delete ON public."CasosAlerta";
CREATE TRIGGER trg_casosalerta_sin_delete
    BEFORE DELETE ON public."CasosAlerta"
    FOR EACH ROW EXECUTE FUNCTION public.fn_casos_alerta_inmutable();

DROP TRIGGER IF EXISTS trg_casosalertahist_inmutable ON public."CasosAlertaHistorial";
CREATE TRIGGER trg_casosalertahist_inmutable
    BEFORE UPDATE OR DELETE ON public."CasosAlertaHistorial"
    FOR EACH ROW EXECUTE FUNCTION public.fn_casos_alerta_inmutable();

-- ── Documentación ─────────────────────────────────────────────────────────
COMMENT ON TABLE  public."CasosAlerta"                  IS 'Estado vigente de casos de alerta por licencia y lote (Art. 29-30 Ley 6593)';
COMMENT ON COLUMN public."CasosAlerta".clave_caso        IS 'SHA-256 de licenciaid|hash_lote|cliente normalizado (clave estable)';
COMMENT ON COLUMN public."CasosAlerta".hash_lote         IS 'SHA-256 del lote canónico de transacciones';
COMMENT ON COLUMN public."CasosAlerta".propuesto_por     IS 'Usuario que propuso Sospechosa (no puede aprobar)';
COMMENT ON COLUMN public."CasosAlerta".aprobado_por      IS 'Oficial/Admin que confirmó la operación sospechosa';
COMMENT ON TABLE  public."CasosAlertaHistorial"         IS 'Historial append-only de transiciones de estado (sin UPDATE ni DELETE)';
