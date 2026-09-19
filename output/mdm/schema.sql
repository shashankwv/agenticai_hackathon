-- =============================================================================
-- Migration  : V001__create_customer_master.sql
-- Ticket     : MDM Task: Master Schema Governance
-- Object     : public.customer_master
-- Purpose    : Golden-record (MDM) table for customer master data, including
--              regulatory identifier (aadhaar_no) and credit scoring attribute
--              (credit_score) as mandated by the governance specification.
-- Idempotent : Yes. Uses IF NOT EXISTS / CREATE OR REPLACE so the script can be
--              re-run safely across DEV / QA / UAT / PROD.
-- Note       : The table does not exist yet, therefore the spec's
--              'ALTER TABLE ... ADD COLUMN' is folded into the initial
--              CREATE TABLE. Because there are no existing rows, the NOT NULL
--              and UNIQUE constraints on aadhaar_no can be applied directly;
--              no backfill / default strategy is required at this time.
--              (On a populated table these constraints would instead be added
--              as NULLable + backfilled + validated, then tightened.)
-- Requires   : PostgreSQL 13+ (gen_random_uuid() is built-in). On PG < 13
--              run: CREATE EXTENSION IF NOT EXISTS pgcrypto;
-- =============================================================================

BEGIN;

-- -----------------------------------------------------------------------------
-- 1. TABLE DEFINITION
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.customer_master (
    -- Surrogate primary key. UUID chosen over serial/bigint so golden records
    -- can be generated/merged across systems without key collisions.
    id              UUID        DEFAULT gen_random_uuid() PRIMARY KEY,

    -- Regulatory identifier (UIDAI Aadhaar). Exactly 12 numeric digits.
    -- VARCHAR(12) (not INT/BIGINT) preserves leading zeros semantics and avoids
    -- arithmetic misuse. NOT NULL + UNIQUE per governance spec: Aadhaar acts as
    -- the natural / match key for de-duplication of customer golden records.
    -- PII CLASSIFICATION: RESTRICTED / SENSITIVE PII -> encryption-at-rest and
    -- column masking policy apply (see COMMENT ON COLUMN below).
    aadhaar_no      VARCHAR(12) NOT NULL,

    -- Credit bureau score. INT is sufficient (range 300-900). NULLable because a
    -- score may not yet be available for a newly onboarded customer; the CHECK
    -- constraint only enforces the range when a value is present.
    credit_score    INT,

    -- Standard MDM audit columns (added on first creation only).
    created_at      TIMESTAMP   DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP   DEFAULT CURRENT_TIMESTAMP,

    -- Named constraints so they can be referenced explicitly in validation
    -- suites, rollback scripts and the data dictionary.
    CONSTRAINT uq_customer_master_aadhaar_no
        UNIQUE (aadhaar_no),

    -- Defensive format check: Aadhaar numbers are 12 digits and never start
    -- with 0 or 1 per UIDAI numbering scheme. Prevents junk / masked values
    -- (e.g. 'XXXXXXXX1234') from leaking into the golden record.
    CONSTRAINT ck_customer_master_aadhaar_no_format
        CHECK (aadhaar_no ~ '^[2-9][0-9]{11}$'),

    -- Range check mandated by the spec. NULL passes a CHECK in PostgreSQL,
    -- so unknown scores are still permitted.
    CONSTRAINT ck_customer_master_credit_score_range
        CHECK (credit_score BETWEEN 300 AND 900)
);

-- -----------------------------------------------------------------------------
-- 2. INDEXES
--    * aadhaar_no is already covered by the UNIQUE constraint's B-tree index
--      (uq_customer_master_aadhaar_no); no additional index is needed.
-- -----------------------------------------------------------------------------

-- Supports risk-segmentation / scoring-band queries (e.g. credit_score < 600).
CREATE INDEX IF NOT EXISTS ix_customer_master_credit_score
    ON public.customer_master (credit_score);

-- Supports incremental / CDC extracts by downstream consumers (WHERE updated_at > :watermark).
CREATE INDEX IF NOT EXISTS ix_customer_master_updated_at
    ON public.customer_master (updated_at);

-- -----------------------------------------------------------------------------
-- 3. AUDIT TRIGGER: keep updated_at accurate on every UPDATE
--    Application code should not be trusted to maintain updated_at.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.fn_set_updated_at()
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
    EXECUTE FUNCTION public.fn_set_updated_at();

-- -----------------------------------------------------------------------------
-- 4. DATA DICTIONARY / COLUMN-LEVEL METADATA (governance deliverable #2)
--    Stored in the catalog so the governance repository can harvest it.
-- -----------------------------------------------------------------------------
COMMENT ON TABLE  public.customer_master IS
    'MDM golden record for Customer. Owner: Data Governance. Classification: CONFIDENTIAL. Contains RESTRICTED PII (aadhaar_no).';

COMMENT ON COLUMN public.customer_master.id IS
    'Surrogate primary key (UUID v4). System generated; never exposed as a business identifier.';

COMMENT ON COLUMN public.customer_master.aadhaar_no IS
    'UIDAI Aadhaar number (12 digits). PII_CLASS=RESTRICTED; ENCRYPTION_AT_REST=REQUIRED (TDE/pgcrypto or storage-level encryption); MASKING_POLICY=SHOW_LAST_4 (e.g. XXXXXXXX1234) for all non-privileged roles; RETENTION=per regulatory policy; LAWFUL_BASIS=KYC/regulatory. Natural match key for de-duplication.';

COMMENT ON COLUMN public.customer_master.credit_score IS
    'Credit bureau score, valid range 300-900 (enforced by CHECK). PII_CLASS=SENSITIVE (financial). NULL = score not yet obtained. MASKING_POLICY=NONE for authorised credit-risk roles, NULLIFY for others.';

COMMENT ON COLUMN public.customer_master.created_at IS
    'Audit: record creation timestamp (server time). Set once by DEFAULT; never updated.';

COMMENT ON COLUMN public.customer_master.updated_at IS
    'Audit: last modification timestamp (server time). Maintained automatically by trigger trg_customer_master_set_updated_at.';

-- -----------------------------------------------------------------------------
-- 5. ACCESS CONTROL / MASKING GUIDANCE (documentation only - roles are
--    environment specific and provisioned by a separate security migration)
--    * Grant SELECT on aadhaar_no only to a dedicated role (e.g. mdm_pii_reader).
--    * Expose a masked view (RIGHT(aadhaar_no,4) prefixed with 'XXXXXXXX') to
--      general consumers; or apply a column-level masking extension.
--    * Enable storage-level / tablespace encryption in all environments.
-- -----------------------------------------------------------------------------

COMMIT;

-- =============================================================================
-- 6. INTENDED UPSERT PATTERN (documentation only - NOT executed here)
--    aadhaar_no is the natural key used for conflict detection. The surrogate
--    id and created_at are never overwritten on conflict; only mutable
--    business attributes and updated_at are refreshed.
--
--    INSERT INTO public.customer_master (aadhaar_no, credit_score)
--    VALUES (:aadhaar_no, :credit_score)
--    ON CONFLICT (aadhaar_no) DO UPDATE
--        SET credit_score = EXCLUDED.credit_score,
--            updated_at   = CURRENT_TIMESTAMP
--    WHERE public.customer_master.credit_score IS DISTINCT FROM EXCLUDED.credit_score;
--
--    The trailing WHERE avoids no-op writes (and spurious updated_at bumps)
--    when the incoming record is identical to the stored golden record.
-- =============================================================================

-- =============================================================================
-- 7. MIGRATION VALIDATION SUITE (run read-only in lower environments;
--    documented as comments so this script remains schema-only)
--
--    -- 7a. Constraints present?
--    SELECT conname, contype
--      FROM pg_constraint
--     WHERE conrelid = 'public.customer_master'::regclass;
--    -- expect: customer_master_pkey (p), uq_customer_master_aadhaar_no (u),
--    --         ck_customer_master_aadhaar_no_format (c),
--    --         ck_customer_master_credit_score_range (c)
--
--    -- 7b. NOT NULL enforced on aadhaar_no?
--    SELECT attname, attnotnull FROM pg_attribute
--     WHERE attrelid = 'public.customer_master'::regclass AND attname = 'aadhaar_no';
--    -- expect: attnotnull = true
--
--    -- 7c. Uniqueness verification (must return zero rows once data exists)
--    SELECT aadhaar_no, COUNT(*) FROM public.customer_master
--     GROUP BY aadhaar_no HAVING COUNT(*) > 1;
--
--    -- 7d. CHECK enforcement (must return zero rows once data exists)
--    SELECT id FROM public.customer_master
--     WHERE credit_score IS NOT NULL AND credit_score NOT BETWEEN 300 AND 900;
--
--    -- 7e. Negative tests (expect ERROR, run inside a transaction and ROLLBACK):
--    --     insert credit_score = 299  -> violates ck_customer_master_credit_score_range
--    --     insert credit_score = 901  -> violates ck_customer_master_credit_score_range
--    --     insert duplicate aadhaar   -> violates uq_customer_master_aadhaar_no
--    --     insert NULL aadhaar        -> violates NOT NULL
--    --     insert '0123456789AB'      -> violates ck_customer_master_aadhaar_no_format
-- =============================================================================

-- =============================================================================
-- 8. ROLLBACK SCRIPT  (U001__drop_customer_master.sql) - documented here,
--    intentionally commented out. Because this is the initial creation, the
--    rollback drops the objects created above. If the table has been populated
--    in production, prefer a soft rollback (drop constraints/columns only) and
--    obtain governance sign-off before any destructive action.
--
--    BEGIN;
--    DROP TRIGGER  IF EXISTS trg_customer_master_set_updated_at ON public.customer_master;
--    DROP INDEX    IF EXISTS public.ix_customer_master_updated_at;
--    DROP INDEX    IF EXISTS public.ix_customer_master_credit_score;
--    DROP TABLE    IF EXISTS public.customer_master;
--    -- Only drop the shared function if no other table depends on it:
--    -- DROP FUNCTION IF EXISTS public.fn_set_updated_at();
--    COMMIT;
--
--    Column-only rollback variant (if the table must be retained):
--    ALTER TABLE public.customer_master DROP CONSTRAINT IF EXISTS ck_customer_master_credit_score_range;
--    ALTER TABLE public.customer_master DROP CONSTRAINT IF EXISTS ck_customer_master_aadhaar_no_format;
--    ALTER TABLE public.customer_master DROP CONSTRAINT IF EXISTS uq_customer_master_aadhaar_no;
--    ALTER TABLE public.customer_master DROP COLUMN IF EXISTS credit_score;
--    ALTER TABLE public.customer_master DROP COLUMN IF EXISTS aadhaar_no;
-- =============================================================================