-- =====================================================================
-- MDM Task: Master Schema Governance
-- Target: public.customer_master (EXISTING production table - LIVE data)
-- Change: Add marital_status attribute per Jira specification.
-- Scope:  Additive, idempotent DDL only. No CREATE TABLE, no DROP/RENAME/
--         RETYPE of existing columns, no DML. Staging is handled in DuckDB
--         and is explicitly out of scope for this script.
-- =====================================================================

-- Audit columns (id, created_at, updated_at) already exist on the table and
-- are therefore NOT re-added here (standard audit columns are added on first
-- creation only).

-- marital_status
--   * VARCHAR(10): longest permitted value is 'Divorced' (8 chars); 10 gives
--     minimal headroom while still bounding storage.
--   * Inline CHECK constraint enforces the governed reference domain
--     ('Single','Married','Divorced','Widowed'). NULL passes the CHECK, so
--     existing rows are unaffected.
--   * Deliberately NULLABLE: the table already contains live rows and a
--     NOT NULL constraint would fail against them. NOT NULL for new intake
--     records is enforced at the pipeline layer, per the Jira spec.
--   * No UNIQUE constraint: this is a low-cardinality descriptive attribute.
--   * No index: four distinct values yield poor selectivity; a B-tree index
--     would add write cost without read benefit. Revisit only if profiling
--     views show heavy filtered scans on this column.
--   * Data dictionary registration (business definition, source system,
--     KYC compliance classification, PII sensitivity) is a governance step
--     performed outside this DDL.
ALTER TABLE public.customer_master
    ADD COLUMN IF NOT EXISTS marital_status VARCHAR(10)
        CONSTRAINT chk_customer_master_marital_status
        CHECK (marital_status IN ('Single', 'Married', 'Divorced', 'Widowed'));

-- ---------------------------------------------------------------------
-- Rollback (for change-governance record only - NOT executed here):
--   ALTER TABLE public.customer_master DROP COLUMN IF EXISTS marital_status;
-- ---------------------------------------------------------------------

-- ---------------------------------------------------------------------
-- Intended UPSERT pattern (documentation only - no DML in this script):
--   The pipeline should merge cleansed KYC records keyed on the surrogate
--   primary key `id`, refreshing `updated_at` on every match:
--
--   INSERT INTO public.customer_master
--       (id, party_legal_name, contact_phone, gov_id_ssn, marital_status)
--   VALUES (...)
--   ON CONFLICT (id) DO UPDATE SET
--       party_legal_name = EXCLUDED.party_legal_name,
--       contact_phone    = EXCLUDED.contact_phone,
--       gov_id_ssn       = EXCLUDED.gov_id_ssn,
--       marital_status   = EXCLUDED.marital_status,
--       updated_at       = CURRENT_TIMESTAMP;
--
--   created_at is intentionally excluded from the UPDATE branch so the
--   original insertion timestamp is preserved.
-- ---------------------------------------------------------------------