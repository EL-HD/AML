-- =============================================================
-- MIGRACIÓN 005: Screening de listas de sanciones
-- Propósito : Persistir listas de sanciones (OFAC SDN, ONU consolidada),
--             sus entradas con alias, las coincidencias por licencia y el
--             historial append-only de decisiones humanas.
-- Base legal : Recomendaciones 6 y 7 del GAFI (sanciones financieras
--              dirigidas: terrorismo y proliferación); Art. 23 y 25 Ley 6593.
-- Ejecutar   : python scripts/db_migrate.py  (o psql -f)
-- Idempotente: puede ejecutarse varias veces sin efectos adversos.
-- Multi-tenant: las listas son globales (públicas); las coincidencias y
--              decisiones llevan licenciaid y toda consulta filtra por él.
-- =============================================================

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ── Listas cargadas (versión, fuente, hash del archivo, cantidad) ────────
CREATE TABLE IF NOT EXISTS public."ListasSancion" (
    id                 UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    fuente             VARCHAR(20)  NOT NULL,
    version            VARCHAR(60)  NOT NULL,
    nombre_archivo     VARCHAR(255) NOT NULL,
    hash_sha256        VARCHAR(64)  NOT NULL,
    cantidad_entradas  INTEGER      NOT NULL DEFAULT 0,
    filas_rechazadas   INTEGER      NOT NULL DEFAULT 0,
    origen             VARCHAR(20)  NOT NULL DEFAULT 'carga_manual',
    activa             BOOLEAN      NOT NULL DEFAULT TRUE,
    cargada_por        VARCHAR(100) NOT NULL,
    cargada_en         TIMESTAMP    NOT NULL DEFAULT NOW(),
    CONSTRAINT listassancion_fuente_check CHECK (fuente IN ('OFAC_SDN','ONU'))
);
CREATE INDEX IF NOT EXISTS idx_listassancion_fuente_activa ON public."ListasSancion"(fuente, activa);

-- ── Entradas de lista (sujeto listado + alias en JSON) ───────────────────
CREATE TABLE IF NOT EXISTS public."ListasSancionEntradas" (
    id                  UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    lista_id            UUID         NOT NULL REFERENCES public."ListasSancion"(id),
    fuente              VARCHAR(20)  NOT NULL,
    referencia          VARCHAR(60)  NOT NULL,
    nombre              VARCHAR(300) NOT NULL,
    nombre_normalizado  VARCHAR(300) NOT NULL,
    tipo                VARCHAR(40),
    programa            VARCHAR(200),
    nacionalidad        VARCHAR(100),
    alias_json          TEXT         NOT NULL DEFAULT '[]'
);
CREATE INDEX IF NOT EXISTS "ix_public_ListasSancionEntradas_lista_id" ON public."ListasSancionEntradas"(lista_id);
CREATE INDEX IF NOT EXISTS idx_listasentradas_lista_ref ON public."ListasSancionEntradas"(lista_id, referencia);

-- ── Coincidencias por licencia con decisión humana ───────────────────────
CREATE TABLE IF NOT EXISTS public."ScreeningCoincidencias" (
    id                   UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
    licenciaid           UUID          NOT NULL,
    cliente              VARCHAR(200)  NOT NULL,
    cliente_normalizado  VARCHAR(300)  NOT NULL,
    origen               VARCHAR(30)   NOT NULL DEFAULT 'Cliente',
    hash_lote            VARCHAR(64),
    lista_id             UUID          NOT NULL,
    entrada_id           UUID          NOT NULL,
    fuente               VARCHAR(20)   NOT NULL,
    referencia           VARCHAR(60)   NOT NULL,
    nombre_lista         VARCHAR(300)  NOT NULL,
    alias_coincidente    VARCHAR(300),
    puntaje              DOUBLE PRECISION NOT NULL,
    motivo               VARCHAR(300)  NOT NULL,
    estado               VARCHAR(20)   NOT NULL DEFAULT 'Pendiente',
    fundamento           VARCHAR(4000) NOT NULL DEFAULT '',
    revisor              VARCHAR(100),
    revisado_en          TIMESTAMP,
    caso_id              UUID,
    detectado_por        VARCHAR(100)  NOT NULL,
    detectado_en         TIMESTAMP     NOT NULL DEFAULT NOW(),
    actualizado_en       TIMESTAMP     NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_screening_licencia_cliente_entrada UNIQUE (licenciaid, cliente_normalizado, entrada_id),
    CONSTRAINT screening_estado_check CHECK (estado IN ('Pendiente','Descartada','Confirmada'))
);
CREATE INDEX IF NOT EXISTS "ix_public_ScreeningCoincidencias_licenciaid" ON public."ScreeningCoincidencias"(licenciaid);
CREATE INDEX IF NOT EXISTS idx_screening_licencia_estado  ON public."ScreeningCoincidencias"(licenciaid, estado);
CREATE INDEX IF NOT EXISTS idx_screening_licencia_cliente ON public."ScreeningCoincidencias"(licenciaid, cliente_normalizado);

-- ── Historial append-only de decisiones ──────────────────────────────────
CREATE TABLE IF NOT EXISTS public."ScreeningDecisiones" (
    id               UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
    licenciaid       UUID          NOT NULL,
    coincidencia_id  UUID          NOT NULL REFERENCES public."ScreeningCoincidencias"(id),
    estado_anterior  VARCHAR(20)   NOT NULL,
    estado_nuevo     VARCHAR(20)   NOT NULL,
    fundamento       VARCHAR(4000) NOT NULL,
    revisor          VARCHAR(100)  NOT NULL,
    rol              VARCHAR(20)   NOT NULL,
    registrado_en    TIMESTAMP     NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS "ix_public_ScreeningDecisiones_licenciaid"      ON public."ScreeningDecisiones"(licenciaid);
CREATE INDEX IF NOT EXISTS "ix_public_ScreeningDecisiones_coincidencia_id" ON public."ScreeningDecisiones"(coincidencia_id);
CREATE INDEX IF NOT EXISTS idx_screeningdec_licencia_coinc ON public."ScreeningDecisiones"(licenciaid, coincidencia_id);

-- ── Inmutabilidad del historial de decisiones (reutiliza fn de 004) ──────
CREATE OR REPLACE FUNCTION public.fn_casos_alerta_inmutable() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'Operación % no permitida en %: registro protegido por retención (Art. 34 Ley 6593)',
        TG_OP, TG_TABLE_NAME;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_screeningdec_inmutable ON public."ScreeningDecisiones";
CREATE TRIGGER trg_screeningdec_inmutable
    BEFORE UPDATE OR DELETE ON public."ScreeningDecisiones"
    FOR EACH ROW EXECUTE FUNCTION public.fn_casos_alerta_inmutable();

-- ── Documentación ─────────────────────────────────────────────────────────
COMMENT ON TABLE  public."ListasSancion"            IS 'Versiones cargadas de listas de sanciones (OFAC SDN, ONU); globales';
COMMENT ON COLUMN public."ListasSancion".hash_sha256 IS 'SHA-256 del archivo principal cargado (sdn.csv o consolidated.xml)';
COMMENT ON TABLE  public."ListasSancionEntradas"    IS 'Sujetos listados con alias (JSON) y nombre normalizado';
COMMENT ON TABLE  public."ScreeningCoincidencias"   IS 'Coincidencias por licencia con estado Pendiente/Descartada/Confirmada y fundamento (GAFI R.6/R.7)';
COMMENT ON TABLE  public."ScreeningDecisiones"      IS 'Historial append-only de decisiones sobre coincidencias';
