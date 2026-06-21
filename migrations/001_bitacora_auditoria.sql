-- =============================================================
-- MIGRACIÓN 001 — BitacoraAuditoria
-- Propósito : Tabla de auditoría de accesos a módulos sensibles
-- Base legal : Art. 19 Ley 6593 (Guatemala) — trazabilidad
--              del Oficial de Cumplimiento
-- Ejecutar  : psql -U postgres -d AML -f 001_bitacora_auditoria.sql
-- =============================================================

-- Extensión para gen_random_uuid() (ya suele estar en Supabase/PostgreSQL 13+)
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS public."BitacoraAuditoria" (
    id            UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    licenciaid    UUID         NOT NULL,
    username      VARCHAR(100) NOT NULL,
    timestamp     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    modulo_accedido VARCHAR(100) NOT NULL,
    accion        VARCHAR(100) NOT NULL DEFAULT 'VISUALIZACION'
);

-- Índices para consultas de auditoría rápida
CREATE INDEX IF NOT EXISTS idx_auditoria_licenciaid
    ON public."BitacoraAuditoria"(licenciaid);

CREATE INDEX IF NOT EXISTS idx_auditoria_timestamp
    ON public."BitacoraAuditoria"(timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_auditoria_modulo
    ON public."BitacoraAuditoria"(modulo_accedido);

-- Comentarios descriptivos
COMMENT ON TABLE  public."BitacoraAuditoria"          IS 'Registro de accesos a módulos sensibles — Art. 19 Ley 6593';
COMMENT ON COLUMN public."BitacoraAuditoria".licenciaid IS 'FK lógica a Licencias.licenceid';
COMMENT ON COLUMN public."BitacoraAuditoria".username   IS 'Nombre de usuario autenticado';
COMMENT ON COLUMN public."BitacoraAuditoria".timestamp  IS 'Timestamp del acceso (con timezone)';
COMMENT ON COLUMN public."BitacoraAuditoria".modulo_accedido IS 'Módulo accedido (ej. Casos de Alerta)';
COMMENT ON COLUMN public."BitacoraAuditoria".accion     IS 'Tipo de acción (VISUALIZACION, GENERACION_RTS, etc.)';
