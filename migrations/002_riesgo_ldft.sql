-- =============================================================
-- MIGRACIÓN 002 — Administración de Riesgo Institucional de LD/FT
-- Propósito : Tablas de Segmentación, Eventos de riesgo, Controles
--             (mitigadores) y Planes de Acción, conforme al modelo
--             GAFILAT / IVE (GERILAFT App) y Art. 8-11 Decreto 15-2026.
-- Ejecutar  : psql -U postgres -d AML -f 002_riesgo_ldft.sql
-- Nota      : SQLAlchemy (models.Base.metadata.create_all, invocado por
--             auth_api.py al arrancar) también crea estas tablas si no
--             existen; este script queda como referencia/DDL explícito
--             y para entornos donde se aplique manualmente.
-- =============================================================

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ── Segmentación (Factor -> Segmento -> Variable) ────────────────────────
CREATE TABLE IF NOT EXISTS public."RiesgoSegmentos" (
    id         UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    licenciaid UUID         NOT NULL,
    factor     VARCHAR(60)  NOT NULL,
    segmento   VARCHAR(120) NOT NULL,
    variable   VARCHAR(120) NOT NULL,
    creado_por VARCHAR(100) NOT NULL,
    creado_en  TIMESTAMP    NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_riesgosegmentos_licenciaid ON public."RiesgoSegmentos"(licenciaid);

-- ── Eventos de riesgo ─────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public."RiesgoEventos" (
    id                   UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
    licenciaid           UUID          NOT NULL,
    codigo               VARCHAR(20)   NOT NULL,
    nombre               VARCHAR(200)  NOT NULL,
    descripcion          VARCHAR(1000),
    factor               VARCHAR(60)   NOT NULL,
    segmento_id          UUID,
    probabilidad         INTEGER       NOT NULL CHECK (probabilidad BETWEEN 1 AND 4),
    riesgo_operacional   INTEGER       NOT NULL CHECK (riesgo_operacional BETWEEN 1 AND 4),
    riesgo_legal         INTEGER       NOT NULL CHECK (riesgo_legal BETWEEN 1 AND 4),
    riesgo_reputacional  INTEGER       NOT NULL CHECK (riesgo_reputacional BETWEEN 1 AND 4),
    riesgo_contagio      INTEGER       NOT NULL CHECK (riesgo_contagio BETWEEN 1 AND 4),
    impacto              INTEGER       NOT NULL CHECK (impacto BETWEEN 1 AND 4),
    nivel_inherente       INTEGER       NOT NULL CHECK (nivel_inherente BETWEEN 1 AND 4),
    nivel_residual        INTEGER       NOT NULL CHECK (nivel_residual BETWEEN 1 AND 4),
    requiere_plan_accion  BOOLEAN       NOT NULL DEFAULT FALSE,
    creado_por           VARCHAR(100)  NOT NULL,
    creado_en            TIMESTAMP     NOT NULL DEFAULT NOW(),
    actualizado_en        TIMESTAMP     NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_riesgoeventos_licenciaid  ON public."RiesgoEventos"(licenciaid);
CREATE INDEX IF NOT EXISTS idx_riesgoeventos_segmento_id ON public."RiesgoEventos"(segmento_id);

-- ── Controles / mitigadores ───────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public."RiesgoControles" (
    id                     UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
    licenciaid             UUID          NOT NULL,
    nombre                 VARCHAR(150)  NOT NULL,
    descripcion            VARCHAR(1000) NOT NULL,
    documentado            BOOLEAN       NOT NULL DEFAULT FALSE,
    tipo_control           VARCHAR(20)   NOT NULL,
    ejecucion              VARCHAR(20)   NOT NULL,
    nivel_cumplimiento     VARCHAR(20)   NOT NULL,
    nivel_efectividad      VARCHAR(20)   NOT NULL,
    evaluado               BOOLEAN       NOT NULL DEFAULT FALSE,
    responsable_evaluacion VARCHAR(150),
    fecha_evaluacion       DATE,
    ponderacion            INTEGER       NOT NULL CHECK (ponderacion BETWEEN 0 AND 100),
    nivel_ponderacion      INTEGER       NOT NULL CHECK (nivel_ponderacion BETWEEN 1 AND 4),
    creado_por             VARCHAR(100)  NOT NULL,
    creado_en              TIMESTAMP     NOT NULL DEFAULT NOW(),
    actualizado_en         TIMESTAMP     NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_riesgocontroles_licenciaid ON public."RiesgoControles"(licenciaid);

-- ── Vínculo N:M evento <-> control ────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public."RiesgoEventoControl" (
    id         UUID      PRIMARY KEY DEFAULT gen_random_uuid(),
    licenciaid UUID      NOT NULL,
    evento_id  UUID      NOT NULL,
    control_id UUID      NOT NULL,
    creado_en  TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_riesgoeventocontrol_licenciaid ON public."RiesgoEventoControl"(licenciaid);
CREATE INDEX IF NOT EXISTS idx_riesgoeventocontrol_evento_id  ON public."RiesgoEventoControl"(evento_id);
CREATE INDEX IF NOT EXISTS idx_riesgoeventocontrol_control_id ON public."RiesgoEventoControl"(control_id);

-- ── Plan de acción ────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public."RiesgoPlanesAccion" (
    id                UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
    licenciaid        UUID          NOT NULL,
    evento_id         UUID          NOT NULL,
    medida_propuesta  VARCHAR(1000) NOT NULL,
    responsable       VARCHAR(150)  NOT NULL,
    fecha_inicio      DATE          NOT NULL,
    fecha_fin         DATE          NOT NULL,
    porcentaje_avance INTEGER       NOT NULL DEFAULT 0 CHECK (porcentaje_avance BETWEEN 0 AND 100),
    creado_por        VARCHAR(100)  NOT NULL,
    creado_en         TIMESTAMP     NOT NULL DEFAULT NOW(),
    actualizado_en    TIMESTAMP     NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_riesgoplanesaccion_licenciaid ON public."RiesgoPlanesAccion"(licenciaid);
CREATE INDEX IF NOT EXISTS idx_riesgoplanesaccion_evento_id  ON public."RiesgoPlanesAccion"(evento_id);

COMMENT ON TABLE public."RiesgoSegmentos"    IS 'Identificación — Factor/Segmento/Variable (Art. 9 Decreto 15-2026)';
COMMENT ON TABLE public."RiesgoEventos"      IS 'Identificación/Medición — eventos de riesgo LD/FT (Art. 9-10 Decreto 15-2026)';
COMMENT ON TABLE public."RiesgoControles"    IS 'Control — mitigadores de riesgo y su ponderación (Art. 11 Decreto 15-2026)';
COMMENT ON TABLE public."RiesgoEventoControl" IS 'Vínculo N:M entre eventos de riesgo y controles mitigadores';
COMMENT ON TABLE public."RiesgoPlanesAccion" IS 'Monitoreo — planes de acción para riesgo residual Medio Alto/Alto';
