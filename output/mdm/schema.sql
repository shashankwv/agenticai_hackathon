-- =============================================================================
-- MDM Task: Master Schema Governance
-- Object   : public.customer_master (Customer Profile Master / Golden Record)
-- Purpose  : Initial creation of the Customer Master table including the new
--            optional PII attribute ALTERNATE_CONTACT_NUMBER, database-level
--            data-quality constraints, audit/history capture, and indexes.
-- Target   : PostgreSQL 13+ (gen_random_uuid() is built-in from PG13; the
--            pgcrypto extension line below keeps the script portable to PG12).
-- Rollout  : DEV -> QA/UAT -> PROD per release calendar (CAB approval required).
-- =============================================================================

-- Safe on PG13+ (no-op) and required on PG12 for gen_random_uuid().
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- -----------------------------------------------------------------------------
-- 1. CORE MASTER TABLE
-- -----------------------------------------------------------------------------
-- Design decisions:
--   * Surrogate PK is a UUID (id) so golden records can be minted by any node
--     without sequence contention and are globally unique across environments.
--   * customer_id is the immutable BUSINESS KEY used for match/survivorship and
--     for the UPSERT conflict target; therefore it is NOT NULL + UNIQUE.
--   * Contact numbers are stored as VARCHAR(20) (E.164 max is 15 digits; extra
--     headroom for future prefix handling). ALTERNATE_CONTACT_NUMBER mirrors the
--     PRIMARY_CONTACT_NUMBER type/length exactly, as mandated by the spec.
--   * ALTERNATE_CONTACT_NUMBER is NULLable (optional attribute, no backfill).
--   * All contact number columns are classified PII: apply column-level masking
--     / encryption via the enterprise data-protection policy (same policy as
--     PRIMARY_CONTACT_NUMBER). Classification is recorded via COMMENT ON below.
CREATE TABLE IF NOT EXISTS public.customer_master (
    -- Standard MDM audit / identity columns (first creation only)
    id                          UUID            DEFAULT gen_random_uuid() PRIMARY KEY,
    created_at                  TIMESTAMP       DEFAULT CURRENT_TIMESTAMP,
    updated_at                  TIMESTAMP       DEFAULT CURRENT_TIMESTAMP,

    -- Business key (source-agnostic enterprise customer identifier)
    customer_id                 VARCHAR(50)     NOT NULL,

    -- Core profile attributes
    first_name                  VARCHAR(100)    NOT NULL,
    middle_name                 VARCHAR(100),
    last_name                   VARCHAR(100)    NOT NULL,
    date_of_birth               DATE,
    gender                      VARCHAR(20),
    email_address               VARCHAR(255),

    -- Contact numbers (PII) -- alternate mirrors primary type/length per spec
    primary_contact_number      VARCHAR(20),
    alternate_contact_number    VARCHAR(20),          -- NEW optional attribute

    -- Address attributes
    address_line_1              VARCHAR(255),
    address_line_2              VARCHAR(255),
    city                        VARCHAR(100),
    state_province              VARCHAR(100),
    postal_code                 VARCHAR(20),
    country_code                CHAR(2),              -- ISO 3166-1 alpha-2

    -- MDM lineage / governance attributes
    customer_status             VARCHAR(20)     NOT NULL DEFAULT 'ACTIVE',
    source_system               VARCHAR(50),
    source_record_id            VARCHAR(100),
    golden_record_flag          BOOLEAN         NOT NULL DEFAULT TRUE,
    record_version              INTEGER         NOT NULL DEFAULT 1,
    last_modified_by            VARCHAR(100),
    last_modified_channel       VARCHAR(50),

    -- Business key uniqueness (also the UPSERT conflict target)
    CONSTRAINT uq_customer_master_customer_id UNIQUE (customer_id),

    -- Controlled vocabulary for lifecycle status
    CONSTRAINT chk_customer_master_status
        CHECK (customer_status IN ('ACTIVE', 'INACTIVE', 'SUSPENDED', 'MERGED', 'DELETED')),

    -- DQ Rule: numeric-only, standard mobile length (10-15 digits) for PRIMARY
    CONSTRAINT chk_customer_master_primary_contact_format
        CHECK (primary_contact_number IS NULL OR primary_contact_number ~ '^[0-9]{10,15}$'),

    -- DQ Rule: numeric-only, standard mobile length (10-15 digits) for ALTERNATE
    CONSTRAINT chk_customer_master_alt_contact_format
        CHECK (alternate_contact_number IS NULL OR alternate_contact_number ~ '^[0-9]{10,15}$'),

    -- Governance Rule: ALTERNATE_CONTACT_NUMBER <> PRIMARY_CONTACT_NUMBER when not NULL
    -- (NULL on either side passes; equality of two populated values is rejected)
    CONSTRAINT chk_customer_master_alt_contact_not_equal_primary
        CHECK (
            alternate_contact_number IS NULL
            OR primary_contact_number IS NULL
            OR alternate_contact_number <> primary_contact_number
        ),

    -- ISO country code must be exactly two uppercase letters when supplied
    CONSTRAINT chk_customer_master_country_code
        CHECK (country_code IS NULL OR country_code ~ '^[A-Z]{2}$')
);

-- Data dictionary metadata (business definition, owner, sensitivity)
COMMENT ON TABLE  public.customer_master IS
    'Customer Master golden record. Owner: Customer Data Domain. Contains PII.';
COMMENT ON COLUMN public.customer_master.customer_id IS
    'Enterprise business key for the customer; immutable; UPSERT conflict target.';
COMMENT ON COLUMN public.customer_master.primary_contact_number IS
    'Primary mobile number. PII - RESTRICTED. Numeric only, 10-15 digits. Masking/encryption per Contact Number policy.';
COMMENT ON COLUMN public.customer_master.alternate_contact_number IS
    'Optional alternate mobile number. PII - RESTRICTED. Same type/length/masking as PRIMARY_CONTACT_NUMBER. Must differ from primary when populated. NOT used in match rules (survivorship: most-recent-non-null).';
COMMENT ON COLUMN public.customer_master.last_modified_channel IS
    'Originating channel of the last change (e.g., UI, ETL, API, BATCH). Copied to audit history.';

-- -----------------------------------------------------------------------------
-- 2. INDEXES
-- -----------------------------------------------------------------------------
-- Name-based search / match candidate generation
CREATE INDEX IF NOT EXISTS idx_customer_master_last_first_name
    ON public.customer_master (last_name, first_name);

-- Case-insensitive e-mail lookup (common match key)
CREATE INDEX IF NOT EXISTS idx_customer_master_email_lower
    ON public.customer_master (LOWER(email_address))
    WHERE email_address IS NOT NULL;

-- Contact number lookups; partial indexes keep them small since values are optional
CREATE INDEX IF NOT EXISTS idx_customer_master_primary_contact
    ON public.customer_master (primary_contact_number)
    WHERE primary_contact_number IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_customer_master_alt_contact
    ON public.customer_master (alternate_contact_number)
    WHERE alternate_contact_number IS NOT NULL;

-- Source lineage lookups for ETL reconciliation
CREATE INDEX IF NOT EXISTS idx_customer_master_source
    ON public.customer_master (source_system, source_record_id);

-- Incremental extract / CDC support for downstream consumers
CREATE INDEX IF NOT EXISTS idx_customer_master_updated_at
    ON public.customer_master (updated_at);

-- -----------------------------------------------------------------------------
-- 3. updated_at MAINTENANCE TRIGGER
-- -----------------------------------------------------------------------------
-- Keeps updated_at accurate regardless of which client/ETL performs the write.
CREATE OR REPLACE FUNCTION public.fn_customer_master_set_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at     := CURRENT_TIMESTAMP;
    NEW.record_version := COALESCE(OLD.record_version, 0) + 1;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_customer_master_set_updated_at ON public.customer_master;
CREATE TRIGGER trg_customer_master_set_updated_at
    BEFORE UPDATE ON public.customer_master
    FOR EACH ROW
    EXECUTE FUNCTION public.fn_customer_master_set_updated_at();

-- -----------------------------------------------------------------------------
-- 4. AUDIT / HISTORY STRUCTURE (attribute-level change capture)
-- -----------------------------------------------------------------------------
-- Design decisions:
--   * Attribute-level (long/narrow) history: one row per changed column so the
--     same structure serves ALTERNATE_CONTACT_NUMBER and PRIMARY_CONTACT_NUMBER
--     without further DDL when additional attributes are onboarded.
--   * Captures old value, new value, changed_by, channel, timestamp, operation.
--   * changed_by / channel are resolved from session GUCs (mdm.changed_by,
--     mdm.channel) set by the application/ETL, falling back to the row-level
--     lineage columns and finally to the DB session_user.
--   * FK to customer_master is intentionally omitted (ON DELETE would erase
--     history); the customer_master_id + customer_id pair provides lineage.
CREATE TABLE IF NOT EXISTS public.customer_master_audit (
    id                  UUID            DEFAULT gen_random_uuid() PRIMARY KEY,
    created_at          TIMESTAMP       DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP       DEFAULT CURRENT_TIMESTAMP,
    customer_master_id  UUID            NOT NULL,
    customer_id         VARCHAR(50)     NOT NULL,
    column_name         VARCHAR(63)     NOT NULL,
    old_value           VARCHAR(255),
    new_value           VARCHAR(255),
    operation           VARCHAR(10)     NOT NULL,
    changed_by          VARCHAR(100)    NOT NULL,
    channel             VARCHAR(50)     NOT NULL,
    changed_at          TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_customer_master_audit_operation
        CHECK (operation IN ('INSERT', 'UPDATE', 'DELETE'))
);

COMMENT ON TABLE public.customer_master_audit IS
    'Attribute-level change history for Customer Master PII contact attributes. Contains PII - apply same masking as source columns.';

CREATE INDEX IF NOT EXISTS idx_customer_master_audit_customer
    ON public.customer_master_audit (customer_master_id, changed_at DESC);

CREATE INDEX IF NOT EXISTS idx_customer_master_audit_column_time
    ON public.customer_master_audit (column_name, changed_at DESC);

-- Trigger function: writes history rows for ALTERNATE_CONTACT_NUMBER (and
-- PRIMARY_CONTACT_NUMBER for consistency) whenever the value changes.
-- NOTE: the INSERT inside this function is part of the audit mechanism
--       definition (schema), not data seeding.
CREATE OR REPLACE FUNCTION public.fn_customer_master_contact_audit()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    v_changed_by VARCHAR(100);
    v_channel    VARCHAR(50);
BEGIN
    v_changed_by := COALESCE(
        NULLIF(current_setting('mdm.changed_by', true), ''),
        CASE WHEN TG_OP = 'DELETE' THEN OLD.last_modified_by ELSE NEW.last_modified_by END,
        session_user::VARCHAR
    );
    v_channel := COALESCE(
        NULLIF(current_setting('mdm.channel', true), ''),
        CASE WHEN TG_OP = 'DELETE' THEN OLD.last_modified_channel ELSE NEW.last_modified_channel END,
        'UNKNOWN'
    );

    IF TG_OP = 'INSERT' THEN
        IF NEW.alternate_contact_number IS NOT NULL THEN
            INSERT INTO public.customer_master_audit
                (customer_master_id, customer_id, column_name, old_value, new_value, operation, changed_by, channel)
            VALUES
                (NEW.id, NEW.customer_id, 'alternate_contact_number', NULL, NEW.alternate_contact_number, TG_OP, v_changed_by, v_channel);
        END IF;
        IF NEW.primary_contact_number IS NOT NULL THEN
            INSERT INTO public.customer_master_audit
                (customer_master_id, customer_id, column_name, old_value, new_value, operation, changed_by, channel)
            VALUES
                (NEW.id, NEW.customer_id, 'primary_contact_number', NULL, NEW.primary_contact_number, TG_OP, v_changed_by, v_channel);
        END IF;
        RETURN NEW;

    ELSIF TG_OP = 'UPDATE' THEN
        -- IS DISTINCT FROM handles NULL <-> value transitions correctly
        IF NEW.alternate_contact_number IS DISTINCT FROM OLD.alternate_contact_number THEN
            INSERT INTO public.customer_master_audit
                (customer_master_id, customer_id, column_name, old_value, new_value, operation, changed_by, channel)
            VALUES
                (NEW.id, NEW.customer_id, 'alternate_contact_number', OLD.alternate_contact_number, NEW.alternate_contact_number, TG_OP, v_changed_by, v_channel);
        END IF;
        IF NEW.primary_contact_number IS DISTINCT FROM OLD.primary_contact_number THEN
            INSERT INTO public.customer_master_audit
                (customer_master_id, customer_id, column_name, old_value, new_value, operation, changed_by, channel)
            VALUES
                (NEW.id, NEW.customer_id, 'primary_contact_number', OLD.primary_contact_number, NEW.primary_contact_number, TG_OP, v_changed_by, v_channel);
        END IF;
        RETURN NEW;

    ELSIF TG_OP = 'DELETE' THEN
        IF OLD.alternate_contact_number IS NOT NULL THEN
            INSERT INTO public.customer_master_audit
                (customer_master_id, customer_id, column_name, old_value, new_value, operation, changed_by, channel)
            VALUES
                (OLD.id, OLD.customer_id, 'alternate_contact_number', OLD.alternate_contact_number, NULL, TG_OP, v_changed_by, v_channel);
        END IF;
        IF OLD.primary_contact_number IS NOT NULL THEN
            INSERT INTO public.customer_master_audit
                (customer_master_id, customer_id, column_name, old_value, new_value, operation, changed_by, channel)
            VALUES
                (OLD.id, OLD.customer_id, 'primary_contact_number', OLD.primary_contact_number, NULL, TG_OP, v_changed_by, v_channel);
        END IF;
        RETURN OLD;
    END IF;

    RETURN NULL;
END;
$$;

DROP TRIGGER IF EXISTS trg_customer_master_contact_audit ON public.customer_master;
CREATE TRIGGER trg_customer_master_contact_audit
    AFTER INSERT OR UPDATE OR DELETE ON public.customer_master
    FOR EACH ROW
    EXECUTE FUNCTION public.fn_customer_master_contact_audit();

-- -----------------------------------------------------------------------------
-- 5. INTENDED UPSERT PATTERN (documentation only - NOT executed by this script)
-- -----------------------------------------------------------------------------
-- ETL / MDM hub should merge on the business key customer_id. Surrogate id,
-- created_at and record_version are never overwritten; updated_at is handled by
-- trigger. Set session context first so the audit trigger captures actor/channel:
--
--   SET LOCAL mdm.changed_by = 'etl_service_account';
--   SET LOCAL mdm.channel    = 'ETL';
--
--   INSERT INTO public.customer_master
--       (customer_id, first_name, last_name, email_address,
--        primary_contact_number, alternate_contact_number,
--        address_line_1, city, state_province, postal_code, country_code,
--        customer_status, source_system, source_record_id,
--        last_modified_by, last_modified_channel)
--   VALUES (...)
--   ON CONFLICT (customer_id) DO UPDATE
--   SET first_name               = EXCLUDED.first_name,
--       last_name                = EXCLUDED.last_name,
--       email_address            = EXCLUDED.email_address,
--       primary_contact_number   = EXCLUDED.primary_contact_number,
--       -- Survivorship for the alternate number: most-recent-non-null
--       alternate_contact_number = COALESCE(EXCLUDED.alternate_contact_number,
--                                           public.customer_master.alternate_contact_number),
--       address_line_1           = EXCLUDED.address_line_1,
--       city                     = EXCLUDED.city,
--       state_province           = EXCLUDED.state_province,
--       postal_code              = EXCL