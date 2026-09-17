-- =============================================================
-- MIGRACIÓN 007: MFA TOTP (RFC 6238) para usuarios
-- Propósito : Tabla public."MfaUsuarios" con el secreto TOTP cifrado
--             (Fernet, clave MFA_ENCRYPTION_KEY), estado de enrolamiento,
--             último contador aceptado (anti-replay) y códigos de
--             recuperación hasheados (PBKDF2-HMAC-SHA256, un solo uso).
-- Base legal : GAFI R.15 (nuevas tecnologías) y Art. 19 Ley 6593
--              (trazabilidad); OWASP A07 (fallos de autenticación).
-- Ejecutar   : python scripts/db_migrate.py  (o psql -f)
-- Idempotente: puede ejecutarse varias veces sin efectos adversos.
--
-- Un registro por licenciaid (usuario). La aplicación es la única que
-- cifra/descifra el secreto; la base nunca lo ve en claro.
--   activo               : FALSE mientras el enrolamiento no se confirme con
--                          un código válido.
--   ultimo_contador      : último contador TOTP aceptado; cualquier contador
--                          igual o menor se rechaza (anti-replay).
--   codigos_recuperacion : JSON con los hashes vigentes; al usarse un código
--                          se elimina su hash (un solo uso).
--   sesion_mfa           : sessionid (BitacoraSesions) que superó el segundo
--                          factor; una sesión distinta no se considera
--                          autenticada aunque la contraseña fuera correcta.
-- =============================================================

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS public."MfaUsuarios" (
    id                   UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
    licenciaid           UUID          NOT NULL,
    usuario              VARCHAR(100)  NOT NULL,
    secreto_cifrado      TEXT          NOT NULL,
    activo               BOOLEAN       NOT NULL DEFAULT FALSE,
    enrolado_en          TIMESTAMP     NULL,
    ultimo_contador      BIGINT        NOT NULL DEFAULT 0,
    codigos_recuperacion TEXT          NOT NULL DEFAULT '[]',
    codigos_restantes    INTEGER       NOT NULL DEFAULT 0,
    sesion_mfa           UUID          NULL,
    creado_en            TIMESTAMP     NOT NULL DEFAULT NOW(),
    actualizado_en       TIMESTAMP     NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_mfa_licencia UNIQUE (licenciaid),
    CONSTRAINT mfa_codigos_restantes_check CHECK (codigos_restantes >= 0),
    CONSTRAINT mfa_ultimo_contador_check CHECK (ultimo_contador >= 0)
);

-- Si la tabla la creó el ORM (create_all) antes de esta migración, la
-- restricción única ya existe con el mismo nombre; los CHECK se añaden
-- solo si faltan.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'mfa_codigos_restantes_check') THEN
        ALTER TABLE public."MfaUsuarios"
            ADD CONSTRAINT mfa_codigos_restantes_check CHECK (codigos_restantes >= 0);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'mfa_ultimo_contador_check') THEN
        ALTER TABLE public."MfaUsuarios"
            ADD CONSTRAINT mfa_ultimo_contador_check CHECK (ultimo_contador >= 0);
    END IF;
END $$;

COMMENT ON TABLE  public."MfaUsuarios" IS 'MFA TOTP (RFC 6238) por licencia: secreto cifrado con Fernet, anti-replay y códigos de recuperación hasheados (T6 Fase 2).';
COMMENT ON COLUMN public."MfaUsuarios".secreto_cifrado IS 'Secreto Base32 cifrado con Fernet (MFA_ENCRYPTION_KEY). Nunca en claro.';
COMMENT ON COLUMN public."MfaUsuarios".ultimo_contador IS 'Último contador TOTP aceptado (anti-replay): se rechazan contadores <= a este valor.';
COMMENT ON COLUMN public."MfaUsuarios".codigos_recuperacion IS 'JSON con hashes PBKDF2-HMAC-SHA256 de los códigos de recuperación vigentes (un solo uso).';
COMMENT ON COLUMN public."MfaUsuarios".sesion_mfa IS 'sessionid de BitacoraSesions que superó el segundo factor.';
