-- =====================================================================
-- MDM Master Table: public.customer_master
-- Purpose : Golden record for customer KYC data with risk scoring.
-- Target  : PostgreSQL 13+ (gen_random_uuid() is built-in from PG13;
--           on older versions run: CREATE EXTENSION IF NOT EXISTS pgcrypto;)
-- Notes   : Sample payload was not supplied, so the column set below is
--           derived from standard KYC / AML master-data requirements.
--           Script is idempotent and contains schema definitions only.
-- =====================================================================

CREATE TABLE IF NOT EXISTS public.customer_master (

    -- ------------------------------------------------------------------
    -- Surrogate key (MDM standard). UUID avoids cross-system collisions
    -- and lets golden records be minted independently of source systems.
    -- ------------------------------------------------------------------
    id                          UUID            DEFAULT gen_random_uuid() PRIMARY KEY,

    -- ------------------------------------------------------------------
    -- Business / natural key. This is the stable identifier exposed to
    -- downstream consumers and the conflict target for UPSERTs.
    -- ------------------------------------------------------------------
    customer_number             VARCHAR(50)     NOT NULL,

    -- Lineage: which source system produced the record and its local id.
    -- Composite uniqueness prevents the same source row loading twice.
    source_system               VARCHAR(50)     NOT NULL,
    source_record_id            VARCHAR(100)    NOT NULL,

    -- ------------------------------------------------------------------
    -- Party identification
    -- ------------------------------------------------------------------
    customer_type               VARCHAR(20)     NOT NULL DEFAULT 'INDIVIDUAL',
    first_name                  VARCHAR(100),
    middle_name                 VARCHAR(100),
    last_name                   VARCHAR(100),
    legal_entity_name           VARCHAR(255),   -- populated for BUSINESS customers
    date_of_birth               DATE,
    gender                      VARCHAR(20),
    nationality_code            CHAR(2),        -- ISO 3166-1 alpha-2
    country_of_residence_code   CHAR(2),        -- ISO 3166-1 alpha-2

    -- Sensitive identifiers are stored as salted hashes, never plaintext.
    -- Raw values remain in the vault/tokenisation service.
    tax_id_hash                 VARCHAR(128),
    national_id_hash            VARCHAR(128),

    -- ------------------------------------------------------------------
    -- Contact details
    -- ------------------------------------------------------------------
    email                       VARCHAR(320),   -- RFC 5321 maximum length
    phone_number                VARCHAR(32),    -- E.164 formatted
    address_line_1              VARCHAR(255),
    address_line_2              VARCHAR(255),
    city                        VARCHAR(100),
    state_province              VARCHAR(100),
    postal_code                 VARCHAR(20),
    address_country_code        CHAR(2),

    -- ------------------------------------------------------------------
    -- KYC verification
    -- ------------------------------------------------------------------
    kyc_status                  VARCHAR(20)     NOT NULL DEFAULT 'PENDING',
    kyc_level                   VARCHAR(20),    -- e.g. SIMPLIFIED / STANDARD / ENHANCED
    kyc_verified_at             TIMESTAMP,
    kyc_expires_at              TIMESTAMP,
    kyc_verified_by             VARCHAR(100),   -- analyst id or automated engine
    id_document_type            VARCHAR(30),    -- PASSPORT / NATIONAL_ID / DRIVING_LICENCE
    id_document_number_hash     VARCHAR(128),
    id_document_issuing_country CHAR(2),
    id_document_expiry_date     DATE,

    -- ------------------------------------------------------------------
    -- AML / screening flags
    -- ------------------------------------------------------------------
    pep_flag                    BOOLEAN         NOT NULL DEFAULT FALSE,  -- politically exposed person
    sanctions_hit_flag          BOOLEAN         NOT NULL DEFAULT FALSE,
    adverse_media_flag          BOOLEAN         NOT NULL DEFAULT FALSE,
    screening_status            VARCHAR(20)     NOT NULL DEFAULT 'NOT_SCREENED',
    last_screened_at            TIMESTAMP,

    -- ------------------------------------------------------------------
    -- Risk scoring
    -- DOUBLE PRECISION chosen because scores are model outputs that may
    -- be fractional; the CHECK bounds the score to a 0-100 scale.
    -- ------------------------------------------------------------------
    risk_score                  DOUBLE PRECISION,
    risk_rating                 VARCHAR(10),    -- LOW / MEDIUM / HIGH / PROHIBITED
    risk_model_version          VARCHAR(32),    -- traceability of the scoring model
    risk_assessed_at            TIMESTAMP,
    next_review_due_date        DATE,           -- periodic KYC refresh scheduling

    -- ------------------------------------------------------------------
    -- MDM survivorship / lifecycle
    -- ------------------------------------------------------------------
    record_status               VARCHAR(20)     NOT NULL DEFAULT 'ACTIVE',  -- ACTIVE / INACTIVE / MERGED
    golden_record_id            UUID,           -- when MERGED, points at surviving record
    data_quality_score          DOUBLE PRECISION,
    version                     INT             NOT NULL DEFAULT 1,  -- optimistic concurrency

    -- ------------------------------------------------------------------
    -- Standard MDM audit columns (added on first creation only)
    -- ------------------------------------------------------------------
    created_at                  TIMESTAMP       DEFAULT CURRENT_TIMESTAMP,
    updated_at                  TIMESTAMP       DEFAULT CURRENT_TIMESTAMP,
    created_by                  VARCHAR(100),
    updated_by                  VARCHAR(100),

    -- ------------------------------------------------------------------
    -- Table-level constraints
    -- ------------------------------------------------------------------
    CONSTRAINT uq_customer_master_customer_number
        UNIQUE (customer_number),

    CONSTRAINT uq_customer_master_source
        UNIQUE (source_system, source_record_id),

    CONSTRAINT fk_customer_master_golden_record
        FOREIGN KEY (golden_record_id) REFERENCES public.customer_master (id),

    CONSTRAINT chk_customer_master_customer_type
        CHECK (customer_type IN ('INDIVIDUAL', 'BUSINESS')),

    CONSTRAINT chk_customer_master_kyc_status
        CHECK (kyc_status IN ('PENDING', 'IN_REVIEW', 'VERIFIED', 'REJECTED', 'EXPIRED')),

    CONSTRAINT chk_customer_master_screening_status
        CHECK (screening_status IN ('NOT_SCREENED', 'CLEAR', 'POTENTIAL_MATCH', 'CONFIRMED_MATCH')),

    CONSTRAINT chk_customer_master_risk_score
        CHECK (risk_score IS NULL OR (risk_score >= 0 AND risk_score <= 100)),

    CONSTRAINT chk_customer_master_risk_rating
        CHECK (risk_rating IS NULL OR risk_rating IN ('LOW', 'MEDIUM', 'HIGH', 'PROHIBITED')),

    CONSTRAINT chk_customer_master_record_status
        CHECK (record_status IN ('ACTIVE', 'INACTIVE', 'MERGED')),

    -- A MERGED record must point at its survivor; non-merged records must not.
    CONSTRAINT chk_customer_master_merge_consistency
        CHECK ((record_status = 'MERGED' AND golden_record_id IS NOT NULL)
            OR (record_status <> 'MERGED' AND golden_record_id IS NULL)),

    CONSTRAINT chk_customer_master_version_positive
        CHECK (version >= 1)
);

-- =====================================================================
-- Indexes
-- (customer_number and source composite are already covered by the
--  UNIQUE constraints above, which create backing indexes.)
-- =====================================================================

-- Operational queues: analysts filter by KYC status constantly.
CREATE INDEX IF NOT EXISTS ix_customer_master_kyc_status
    ON public.customer_master (kyc_status);

-- Risk dashboards and enhanced-due-diligence workflows.
CREATE INDEX IF NOT EXISTS ix_customer_master_risk_rating
    ON public.customer_master (risk_rating);

-- Partial index: only ACTIVE records need periodic-review scheduling.
CREATE INDEX IF NOT EXISTS ix_customer_master_next_review_due
    ON public.customer_master (next_review_due_date)
    WHERE record_status = 'ACTIVE';

-- Partial index for screening exceptions; hits are rare so index stays tiny.
CREATE INDEX IF NOT EXISTS ix_customer_master_screening_hits
    ON public.customer_master (screening_status)
    WHERE pep_flag OR sanctions_hit_flag OR adverse_media_flag;

-- Case-insensitive email lookup used by match/merge rules.
CREATE INDEX IF NOT EXISTS ix_customer_master_email_lower
    ON public.customer_master (LOWER(email));

-- Fuzzy-match candidate retrieval (name + DOB blocking key).
CREATE INDEX IF NOT EXISTS ix_customer_master_name_dob
    ON public.customer_master (LOWER(last_name), LOWER(first_name), date_of_birth);

-- Survivorship navigation from merged duplicates to golden record.
CREATE INDEX IF NOT EXISTS ix_customer_master_golden_record
    ON public.customer_master (golden_record_id)
    WHERE golden_record_id IS NOT NULL;

-- Incremental CDC extraction by downstream consumers.
CREATE INDEX IF NOT EXISTS ix_customer_master_updated_at
    ON public.customer_master (updated_at);

-- =====================================================================
-- updated_at maintenance trigger (schema object, not DML).
-- Guarantees updated_at is refreshed even when callers forget to set it.
-- =====================================================================
CREATE OR REPLACE FUNCTION public.fn_customer_master_set_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at := CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_customer_master_set_updated_at ON public.customer_master;

CREATE TRIGGER trg_customer_master_set_updated_at
    BEFORE UPDATE ON public.customer_master
    FOR EACH ROW
    EXECUTE FUNCTION public.fn_customer_master_set_updated_at();

-- =====================================================================
-- Column documentation
-- =====================================================================
COMMENT ON TABLE  public.customer_master IS 'MDM golden record for customer KYC profile and AML risk scoring.';
COMMENT ON COLUMN public.customer_master.customer_number IS 'Business key; stable identifier exposed to downstream systems and used as UPSERT conflict target.';
COMMENT ON COLUMN public.customer_master.tax_id_hash IS 'Salted hash of tax identifier; plaintext held only in tokenisation vault.';
COMMENT ON COLUMN public.customer_master.risk_score IS 'Model-generated risk score on a 0-100 scale.';
COMMENT ON COLUMN public.customer_master.risk_model_version IS 'Version of the scoring model that produced risk_score, for audit reproducibility.';
COMMENT ON COLUMN public.customer_master.golden_record_id IS 'Self-reference to the surviving record when this row has been merged.';
COMMENT ON COLUMN public.customer_master.version IS 'Monotonic row version for optimistic concurrency control.';

-- =====================================================================
-- Intended UPSERT pattern (documentation only - NOT executed here)
-- =====================================================================
-- Loads from the cleansing pipeline should target the business key so a
-- re-delivered record updates in place rather than creating a duplicate.
-- Audit columns are handled as follows: created_at / created_by are set
-- only on INSERT (never overwritten), updated_at is bumped by the trigger,
-- and version is incremented to support optimistic locking.
--
--   INSERT INTO public.customer_master (
--       customer_number, source_system, source_record_id, customer_type,
--       first_name, last_name, date_of_birth, email, kyc_status,
--       risk_score, risk_rating, risk_model_version, risk_assessed_at,
--       created_by, updated_by
--   )
--   VALUES (...)
--   ON CONFLICT (customer_number) DO UPDATE SET
--       source_system      = EXCLUDED.source_system,
--       source_record_id   = EXCLUDED.source_record_id,
--       customer_type      = EXCLUDED.customer_type,
--       first_name         = EXCLUDED.first_name,
--       last_name          = EXCLUDED.last_name,
--       date_of_birth      = EXCLUDED.date_of_birth,
--       email              = EXCLUDED.email,
--       kyc_status         = EXCLUDED.kyc_status,
--       risk_score         = EXCLUDED.risk_score,
--       risk_rating        = EXCLUDED.risk_rating,
--       risk_model_version = EXCLUDED.risk_model_version,
--       risk_assessed_at   = EXCLUDED.risk_assessed_at,
--       updated_by         = EXCLUDED.updated_by,
--       version            = public.customer_master.version + 1
--   WHERE public.customer_master.record_status <> 'MERGED';
--
-- The trailing WHERE prevents a stale source feed from resurrecting a
-- record that has already been merged into another golden record.
-- Use COALESCE(EXCLUDED.col, customer_master.col) per column if the
-- survivorship rule is 'do not overwrite with NULL'.