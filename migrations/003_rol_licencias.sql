-- =============================================================
-- MIGRACIÓN 003: rol en Licencias (control de acceso por rol)
-- Propósito : RBAC mínimo (OWASP A01). Roles permitidos:
--             admin, oficial, analista, auditor.
-- Ejecutar  : python scripts/db_migrate.py  (o psql -f)
-- Nota      : las licencias existentes quedan como 'analista'.
--             Asigne 'admin' manualmente a la licencia administradora:
--             UPDATE public."Licencias" SET rol = 'admin' WHERE "User" = '<usuario>';
-- =============================================================

ALTER TABLE public."Licencias"
    ADD COLUMN IF NOT EXISTS rol VARCHAR(20) NOT NULL DEFAULT 'analista';

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'licencias_rol_check'
    ) THEN
        ALTER TABLE public."Licencias"
            ADD CONSTRAINT licencias_rol_check
            CHECK (rol IN ('admin', 'oficial', 'analista', 'auditor'));
    END IF;
END $$;

COMMENT ON COLUMN public."Licencias".rol IS 'Rol RBAC: admin | oficial | analista | auditor';
