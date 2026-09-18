-- ============================================================================
-- MDM: Core Banking Customer 360 -- Master Schema Governance
-- Object      : public.customer_master
-- Script      : V001__create_customer_master.sql  (forward migration)
-- Rollback    : V001__create_customer_master__rollback.sql (see block at end)
-- Owner       : MDM Platform / DBA / Data Governance
-- Notes       : The table does NOT exist yet, therefore aadhaar_no and
--               credit_score are created inline with their full constraints.
--               No phased add-nullable -> backfill -> enforce NOT NULL step is
--               required because there are no pre-existing rows to violate
--               NOT NULL / UNIQUE. If this script is ever re-pointed at an
--               environment where the table already exists, use the phased
--               ALTER TABLE strategy documented in the rollback/notes block.
-- ============================================================================

-- gen_random_uuid() is core in PostgreSQL 13+. pgcrypto keeps the script
-- portable to PostgreSQL 10-12 without changing the DDL below.
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ----------------------------------------------------------------------------
-- 1. Golden record table
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.customer_master (
    -- Standard MDM audit / surrogate key columns (first creation only)
    id                  UUID         DEFAULT gen_random_uuid() PRIMARY KEY,
    created_at          TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,

    -- Business / natural key: Customer Information File (CIF) number issued by
    -- the core banking system. Kept separate from the surrogate UUID so that
    -- ETL UPSERTs can target a stable business identifier.
    customer_id         VARCHAR(20)  NOT NULL,

    -- Identity attributes
    first_name          VARCHAR(100) NOT NULL,
    middle_name         VARCHAR(100),
    last_name           VARCHAR(100) NOT NULL,
    date_of_birth       DATE,
    gender              VARCHAR(10),

    -- Contact attributes (PII - restricted)
    email               VARCHAR(255),
    mobile_no           VARCHAR(15),

    -- Regulatory identifiers (PII - sensitive)
    pan_no              VARCHAR(10),

    -- Aadhaar number for Aadhaar-based KYC.
    -- Spec: VARCHAR(12) NOT NULL UNIQUE. Classified SENSITIVE PII:
    --   * encryption-at-rest mandatory (tablespace/TDE or column-level pgcrypto
    --     handled by the platform; DDL keeps clear VARCHAR(12) per contract),
    --   * access restricted to KYC role; masked in all non-production copies.
    -- The UNIQUE constraint implicitly creates a B-tree index that also
    -- serves the ETL UPSERT / de-duplication lookups.
    aadhaar_no          VARCHAR(12)  NOT NULL,

    -- Automated credit score. Source lineage: ETL risk computation / bureau.
    -- Nullable because a score may not yet exist for a newly onboarded
    -- customer. Valid range is 300-900 (Indian bureau scale).
    credit_score        INT,
    credit_score_source VARCHAR(50),      -- e.g. CIBIL, EXPERIAN, INTERNAL_RISK_ETL
    credit_score_as_of  DATE,             -- effective date of the score

    -- KYC lifecycle
    kyc_status          VARCHAR(20)  NOT NULL DEFAULT 'PENDING',
    kyc_verified_at     TIMESTAMP,

    -- Address attributes (PII - restricted)
    address_line1       VARCHAR(255),
    address_line2       VARCHAR(255),
    city                VARCHAR(100),
    state               VARCHAR(100),
    postal_code         VARCHAR(10),
    country_code        CHAR(2)      NOT NULL DEFAULT 'IN',

    -- Master-data lifecycle / lineage
    customer_status     VARCHAR(20)  NOT NULL DEFAULT 'ACTIVE',
    source_system       VARCHAR(50),      -- originating system of record
    record_version      INT          NOT NULL DEFAULT 1,

    -- ------------------------------------------------------------------------
    -- Named constraints: explicit names make CI validation, rollback and
    -- error messages deterministic across environments.
    -- ------------------------------------------------------------------------
    CONSTRAINT uq_customer_master_customer_id  UNIQUE (customer_id),
    CONSTRAINT uq_customer_master_aadhaar_no   UNIQUE (aadhaar_no),
    CONSTRAINT ck_customer_master_aadhaar_fmt  CHECK (aadhaar_no ~ '^[0-9]{12}$'),
    CONSTRAINT ck_customer_master_credit_score CHECK (credit_score BETWEEN 300 AND 900),
    CONSTRAINT ck_customer_master_gender       CHECK (gender IS NULL OR gender IN ('MALE','FEMALE','OTHER','UNKNOWN')),
    CONSTRAINT ck_customer_master_kyc_status   CHECK (kyc_status IN ('PENDING','VERIFIED','REJECTED','EXPIRED')),
    CONSTRAINT ck_customer_master_cust_status  CHECK (customer_status IN ('ACTIVE','INACTIVE','DORMANT','CLOSED')),
    CONSTRAINT ck_customer_master_pan_fmt      CHECK (pan_no IS NULL OR pan_no ~ '^[A-Z]{5}[0-9]{4}[A-Z]$'),
    CONSTRAINT ck_customer_master_email_fmt    CHECK (email IS NULL OR position('@' in email) > 1),
    CONSTRAINT ck_customer_master_updated_ge_created CHECK (updated_at >= created_at)
);

-- ----------------------------------------------------------------------------
-- 2. Secondary indexes
--    Note: PRIMARY KEY (id), UNIQUE (customer_id) and UNIQUE (aadhaar_no)
--    already create B-tree indexes; do not duplicate them.
-- ----------------------------------------------------------------------------
-- Case-insensitive email lookups from UI search / ETL matching.
CREATE INDEX IF NOT EXISTS ix_customer_master_email_lower
    ON public.customer_master (lower(email));

-- Mobile-based customer search (contact-centre / OTP flows).
CREATE INDEX IF NOT EXISTS ix_customer_master_mobile_no
    ON public.customer_master (mobile_no);

-- Partial index: only non-null PAN values are worth indexing.
CREATE INDEX IF NOT EXISTS ix_customer_master_pan_no
    ON public.customer_master (pan_no)
    WHERE pan_no IS NOT NULL;

-- Operational filtering by KYC / customer lifecycle state.
CREATE INDEX IF NOT EXISTS ix_customer_master_kyc_status
    ON public.customer_master (kyc_status);

CREATE INDEX IF NOT EXISTS ix_customer_master_customer_status
    ON public.customer_master (customer_status);

-- Risk analytics: range scans on credit score (partial - skip unscored rows).
CREATE INDEX IF NOT EXISTS ix_customer_master_credit_score
    ON public.customer_master (credit_score)
    WHERE credit_score IS NOT NULL;

-- Incremental / CDC extraction by ETL.
CREATE INDEX IF NOT EXISTS ix_customer_master_updated_at
    ON public.customer_master (updated_at);

-- ----------------------------------------------------------------------------
-- 3. updated_at maintenance trigger
--    Guarantees updated_at is always refreshed on UPDATE regardless of whether
--    the calling ETL/UI sets it, and bumps record_version for optimistic
--    concurrency / lineage.
-- ----------------------------------------------------------------------------
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

-- ----------------------------------------------------------------------------
-- 4. Data dictionary / MDM catalogue metadata (queryable via pg_description)
-- ----------------------------------------------------------------------------
COMMENT ON TABLE  public.customer_master IS
    'Customer 360 golden record. System of record for master customer attributes. Domain: Core Banking. Steward: Data Governance.';
COMMENT ON COLUMN public.customer_master.id IS
    'Surrogate primary key (UUID v4). Internal only; never exposed as a business identifier.';
COMMENT ON COLUMN public.customer_master.customer_id IS
    'Business/natural key: core banking CIF number. UPSERT conflict target for ETL.';
COMMENT ON COLUMN public.customer_master.aadhaar_no IS
    'Classification: SENSITIVE PII (Aadhaar). 12-digit numeric. NOT NULL UNIQUE. Encryption-at-rest required; access restricted to KYC_OFFICER role; must be masked (XXXX-XXXX-1234) in logs, UI and non-prod environments.';
COMMENT ON COLUMN public.customer_master.credit_score IS
    'Automated credit score, valid range 300-900. Lineage: ETL risk computation / credit bureau feed. NULL = not yet scored.';
COMMENT ON COLUMN public.customer_master.credit_score_source IS
    'Provenance of credit_score (e.g. CIBIL, EXPERIAN, INTERNAL_RISK_ETL).';
COMMENT ON COLUMN public.customer_master.credit_score_as_of IS
    'Effective/as-of date of credit_score as reported by the source.';
COMMENT ON COLUMN public.customer_master.pan_no IS
    'Classification: SENSITIVE PII (PAN). Format AAAAA9999A.';
COMMENT ON COLUMN public.customer_master.email IS
    'Classification: RESTRICTED PII.';
COMMENT ON COLUMN public.customer_master.mobile_no IS
    'Classification: RESTRICTED PII.';
COMMENT ON COLUMN public.customer_master.created_at IS
    'MDM audit: row creation timestamp (server time).';
COMMENT ON COLUMN public.customer_master.updated_at IS
    'MDM audit: last modification timestamp, maintained by trigger.';

-- ----------------------------------------------------------------------------
-- 5. Access control baseline for PII (roles are provisioned by the platform)
--    Left as governance guidance; uncomment once roles exist in target env.
-- ----------------------------------------------------------------------------
-- REVOKE ALL ON public.customer_master FROM PUBLIC;
-- GRANT SELECT (id, customer_id, first_name, last_name, kyc_status, customer_status, credit_score)
--     ON public.customer_master TO app_readonly;
-- GRANT SELECT, INSERT, UPDATE ON public.customer_master TO mdm_etl_writer;
-- GRANT SELECT (aadhaar_no, pan_no) ON public.customer_master TO kyc_officer;

-- ----------------------------------------------------------------------------
-- 6. Intended UPSERT pattern (documentation only -- NOT executed here)
--    The ETL loads a cleansed payload keyed on the business key customer_id.
--    aadhaar_no is a second UNIQUE key; a conflict on aadhaar_no with a
--    DIFFERENT customer_id indicates a duplicate identity and must be routed
--    to the MDM survivorship / stewardship queue rather than silently merged.
--
--    INSERT INTO public.customer_master (
--        customer_id, first_name, middle_name, last_name, date_of_birth, gender,
--        email, mobile_no, pan_no, aadhaar_no, credit_score, credit_score_source,
--        credit_score_as_of, kyc_status, address_line1, address_line2, city,
--        state, postal_code, country_code, customer_status, source_system)
--    VALUES (...)
--    ON CONFLICT (customer_id) DO UPDATE SET
--        first_name          = EXCLUDED.first_name,
--        middle_name         = EXCLUDED.middle_name,
--        last_name           = EXCLUDED.last_name,
--        date_of_birth       = EXCLUDED.date_of_birth,
--        gender              = EXCLUDED.gender,
--        email               = EXCLUDED.email,
--        mobile_no           = EXCLUDED.mobile_no,
--        pan_no              = EXCLUDED.pan_no,
--        aadhaar_no          = EXCLUDED.aadhaar_no,
--        credit_score        = EXCLUDED.credit_score,
--        credit_score_source = EXCLUDED.credit_score_source,
--        credit_score_as_of  = EXCLUDED.credit_score_as_of,
--        kyc_status          = EXCLUDED.kyc_status,
--        address_line1       = EXCLUDED.address_line1,
--        address_line2       = EXCLUDED.address_line2,
--        city                = EXCLUDED.city,
--        state               = EXCLUDED.state,
--        postal_code         = EXCLUDED.postal_code,
--        country_code        = EXCLUDED.country_code,
--        customer_status     = EXCLUDED.customer_status,
--        source_system       = EXCLUDED.source_system,
--        updated_at          = CURRENT_TIMESTAMP
--    WHERE public.customer_master.updated_at < EXCLUDED.updated_at;   -- optional last-write-wins guard
--
--    id, created_at are never overwritten; updated_at / record_version are
--    also enforced by trg_customer_master_set_updated_at.

-- ----------------------------------------------------------------------------
-- 7. Governance note: phased strategy if the table ALREADY exists with rows
--    (kept for completeness of the migration contract; not executed here)
--
--    Step 1: ALTER TABLE public.customer_master ADD COLUMN IF NOT EXISTS aadhaar_no VARCHAR(12);
--            ALTER TABLE public.customer_master ADD COLUMN IF NOT EXISTS credit_score INT;
--            ALTER TABLE public.customer_master ADD CONSTRAINT ck_customer_master_credit_score
--                CHECK (credit_score BETWEEN 300 AND 900);
--    Step 2: Backfill aadhaar_no from the KYC source system via ETL (no placeholder
--            values are permitted for a UNIQUE column; Data Governance approval required
--            for any exception).
--    Step 3: CREATE UNIQUE INDEX CONCURRENTLY uq_customer_master_aadhaar_no
--                ON public.customer_master (aadhaar_no);
--            ALTER TABLE public.customer_master ADD CONSTRAINT uq_customer_master_aadhaar_no
--                UNIQUE USING INDEX uq_customer_master_aadhaar_no;
--    Step 4: Validate zero NULLs, then
--            ALTER TABLE public.customer_master ALTER COLUMN aadhaar_no SET NOT NULL;
-- ----------------------------------------------------------------------------

-- ----------------------------------------------------------------------------
-- 8. ROLLBACK SCRIPT  (V001__create_customer_master__rollback.sql)
--    Executed only by the CI rollback-verification stage or a DBA.
--    Order matters: trigger -> function -> indexes -> table.
--
--    DROP TRIGGER  IF EXISTS trg_customer_master_set_updated_at ON public.customer_master;
--    DROP FUNCTION IF EXISTS public.fn_customer_master_set_updated_at();
--    DROP INDEX    IF EXISTS ix_customer_master_email_lower;
--    DROP INDEX    IF EXISTS ix_customer_master_mobile_no;
--    DROP INDEX    IF EXISTS ix_customer_master_pan_no;
--    DROP INDEX    IF EXISTS ix_customer_master_kyc_status;
--    DROP INDEX    IF EXISTS ix_customer_master_customer_status;
--    DROP INDEX    IF EXISTS ix_customer_master_credit_score;
--    DROP INDEX    IF EXISTS ix_customer_master_updated_at;
--    DROP TABLE    IF EXISTS public.customer_master;
-- ----------------------------------------------------------------------------