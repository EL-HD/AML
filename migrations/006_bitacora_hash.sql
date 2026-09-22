-- =============================================================
-- MIGRACIÓN 006: Bitácora a prueba de alteraciones
-- Propósito : Encadenar criptográficamente public."BitacoraAuditoria"
--             por licencia (seq, hash_prev, hash) y volverla append-only.
-- Base legal : Art. 19 Ley 6593 (trazabilidad del Oficial de
--              Cumplimiento); GAFI R.11 (conservación de registros);
--              OWASP A09 (integridad de la bitácora de seguridad).
-- Ejecutar   : python scripts/db_migrate.py  (o psql -f)
-- Idempotente: puede ejecutarse varias veces sin efectos adversos.
--
-- Diseño de la cadena (el cálculo del hash vive SOLO en backend/auditoria.py):
--   seq       : correlativo 1..n por licenciaid (sin huecos).
--   hash_prev : hash del registro anterior de la misma licencia; el primer
--               eslabón (seq = 1) usa 64 ceros (génesis).
--   hash      : SHA-256 (o HMAC-SHA256 si AUDIT_HMAC_KEY está definida) de la
--               serialización canónica: JSON con claves ordenadas de
--               {v, licenciaid, seq, hash_prev, timestamp ISO UTC, usuario,
--               modulo, accion}.
--   hash_alg  : 'sha256' o 'hmac-sha256' (permite rotar a HMAC sin romper la
--               verificación de los eslabones anteriores).
--
-- Registros existentes ("pre-cadena"): conservan seq/hash NULL. Se optó por
-- no sellarlos en un bloque génesis porque para hacerlo en SQL habría que
-- replicar la serialización canónica en PL/pgSQL (dos puntos de cálculo) y
-- porque su integridad previa a esta migración no es demostrable. Quedan
-- protegidos desde ahora por los mismos triggers (sin UPDATE ni DELETE) y el
-- trigger de inserción impide que se agreguen nuevos registros sin cadena,
-- por lo que el conjunto pre-cadena queda congelado y la verificación lo
-- reporta como informativo.
-- =============================================================

ALTER TABLE public."BitacoraAuditoria" ADD COLUMN IF NOT EXISTS seq       BIGINT;
ALTER TABLE public."BitacoraAuditoria" ADD COLUMN IF NOT EXISTS hash_prev VARCHAR(64);
ALTER TABLE public."BitacoraAuditoria" ADD COLUMN IF NOT EXISTS hash      VARCHAR(64);
ALTER TABLE public."BitacoraAuditoria" ADD COLUMN IF NOT EXISTS hash_alg  VARCHAR(16);

-- Un solo seq por licencia (los NULL pre-cadena no colisionan entre sí).
CREATE UNIQUE INDEX IF NOT EXISTS uq_bitacora_licencia_seq
    ON public."BitacoraAuditoria"(licenciaid, seq);

-- ── Append-only: ni UPDATE ni DELETE sobre ningún registro ───────────────
CREATE OR REPLACE FUNCTION public.fn_bitacora_inmutable() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'Operación % no permitida en %: la bitácora de auditoría es append-only (Art. 19 Ley 6593)',
        TG_OP, TG_TABLE_NAME;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_bitacora_inmutable ON public."BitacoraAuditoria";
CREATE TRIGGER trg_bitacora_inmutable
    BEFORE UPDATE OR DELETE ON public."BitacoraAuditoria"
    FOR EACH ROW EXECUTE FUNCTION public.fn_bitacora_inmutable();

-- ── Validación estructural de cada eslabón nuevo ─────────────────────────
-- No calcula el hash (eso es responsabilidad exclusiva de la aplicación);
-- verifica que el eslabón sea consecutivo y apunte al hash del anterior.
CREATE OR REPLACE FUNCTION public.fn_bitacora_validar_eslabon() RETURNS trigger AS $$
DECLARE
    ultimo_seq  BIGINT;
    ultimo_hash VARCHAR(64);
BEGIN
    IF NEW.seq IS NULL OR NEW.hash IS NULL OR NEW.hash_prev IS NULL OR NEW.hash_alg IS NULL THEN
        RAISE EXCEPTION 'BitacoraAuditoria: todo registro nuevo debe traer seq, hash_prev, hash y hash_alg';
    END IF;
    IF NEW.seq < 1 THEN
        RAISE EXCEPTION 'BitacoraAuditoria: seq debe ser mayor o igual a 1';
    END IF;
    IF NEW.hash !~ '^[0-9a-f]{64}$' OR NEW.hash_prev !~ '^[0-9a-f]{64}$' THEN
        RAISE EXCEPTION 'BitacoraAuditoria: hash y hash_prev deben ser SHA-256 en hexadecimal minúsculo';
    END IF;
    IF NEW.hash_alg NOT IN ('sha256', 'hmac-sha256') THEN
        RAISE EXCEPTION 'BitacoraAuditoria: hash_alg desconocido (%)', NEW.hash_alg;
    END IF;
    SELECT seq, hash INTO ultimo_seq, ultimo_hash
      FROM public."BitacoraAuditoria"
     WHERE licenciaid = NEW.licenciaid AND seq IS NOT NULL
     ORDER BY seq DESC LIMIT 1;
    IF ultimo_seq IS NULL THEN
        IF NEW.seq <> 1 OR NEW.hash_prev <> repeat('0', 64) THEN
            RAISE EXCEPTION 'BitacoraAuditoria: el primer eslabón de la licencia debe ser seq = 1 con hash_prev génesis';
        END IF;
    ELSE
        IF NEW.seq <> ultimo_seq + 1 THEN
            RAISE EXCEPTION 'BitacoraAuditoria: seq % fuera de orden (se esperaba %)', NEW.seq, ultimo_seq + 1;
        END IF;
        IF NEW.hash_prev <> ultimo_hash THEN
            RAISE EXCEPTION 'BitacoraAuditoria: hash_prev no coincide con el hash del eslabón %', ultimo_seq;
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_bitacora_validar_eslabon ON public."BitacoraAuditoria";
CREATE TRIGGER trg_bitacora_validar_eslabon
    BEFORE INSERT ON public."BitacoraAuditoria"
    FOR EACH ROW EXECUTE FUNCTION public.fn_bitacora_validar_eslabon();

-- ── Documentación ─────────────────────────────────────────────────────────
COMMENT ON COLUMN public."BitacoraAuditoria".seq       IS 'Correlativo por licencia sin huecos (NULL = registro pre-cadena anterior a 006)';
COMMENT ON COLUMN public."BitacoraAuditoria".hash_prev IS 'Hash del eslabón anterior de la misma licencia; 64 ceros en el primero';
COMMENT ON COLUMN public."BitacoraAuditoria".hash      IS 'SHA-256 o HMAC-SHA256 de la serialización canónica (backend/auditoria.py)';
COMMENT ON COLUMN public."BitacoraAuditoria".hash_alg  IS 'sha256 | hmac-sha256 (HMAC cuando AUDIT_HMAC_KEY está definida)';
