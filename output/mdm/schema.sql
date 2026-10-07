-- =====================================================================
-- MDM Task: Master Schema Governance (KYC Party Master)
-- Target : PostgreSQL 13+
-- Scope  : customer_master (Party), ETL staging, match/merge rule registry,
--          survivorship support, PII classification, lineage, access control
-- Change-Control: submit via standard DDL review before production apply
-- =====================================================================

BEGIN;

-- ---------------------------------------------------------------------
-- 0. Extensions (gen_random_uuid, pgp encryption, trigram fuzzy match)
-- ---------------------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- ---------------------------------------------------------------------
-- 1. Golden record: public.customer_master (Party entity)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.customer_master (
    id                      UUID            DEFAULT gen_random_uuid() PRIMARY KEY,
    party_legal_name        VARCHAR(255)    NOT NULL,
    contact_phone           VARCHAR(20),
    gov_id_ssn              BYTEA           NOT NULL,                       -- encrypted ciphertext (pgp_sym_encrypt / KMS envelope)
    gov_id_ssn_hash         CHAR(64)        NOT NULL,                       -- deterministic SHA-256 token for exact match
    source_system           VARCHAR(100)    NOT NULL,
    source_record_id        VARCHAR(255),
    source_updated_at       TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP, -- survivorship: most recent source wins
    match_confidence_score  DOUBLE PRECISION,
    merge_group_id          UUID,
    is_active               BOOLEAN         NOT NULL DEFAULT TRUE,
    record_version          INT             NOT NULL DEFAULT 1,
    created_at              TIMESTAMP       DEFAULT CURRENT_TIMESTAMP,
    updated_at              TIMESTAMP       DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_customer_master_gov_id_ssn_hash UNIQUE (gov_id_ssn_hash),
    CONSTRAINT ck_customer_master_contact_phone_digits CHECK (contact_phone IS NULL OR contact_phone ~ '^[0-9]+$'),
    CONSTRAINT ck_customer_master_legal_name_not_blank CHECK (btrim(party_legal_name) <> ''),
    CONSTRAINT ck_customer_master_match_score CHECK (match_confidence_score IS NULL OR (match_confidence_score >= 0 AND match_confidence_score <= 1))
);

-- Idempotent incremental evolution (safe re-run on partially deployed envs)
ALTER TABLE public.customer_master ADD COLUMN IF NOT EXISTS party_legal_name        VARCHAR(255);
ALTER TABLE public.customer_master ADD COLUMN IF NOT EXISTS contact_phone           VARCHAR(20);
ALTER TABLE public.customer_master ADD COLUMN IF NOT EXISTS gov_id_ssn              BYTEA;
ALTER TABLE public.customer_master ADD COLUMN IF NOT EXISTS gov_id_ssn_hash         CHAR(64);
ALTER TABLE public.customer_master ADD COLUMN IF NOT EXISTS source_system           VARCHAR(100);
ALTER TABLE public.customer_master ADD COLUMN IF NOT EXISTS source_record_id        VARCHAR(255);
ALTER TABLE public.customer_master ADD COLUMN IF NOT EXISTS source_updated_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE public.customer_master ADD COLUMN IF NOT EXISTS match_confidence_score  DOUBLE PRECISION;
ALTER TABLE public.customer_master ADD COLUMN IF NOT EXISTS merge_group_id          UUID;
ALTER TABLE public.customer_master ADD COLUMN IF NOT EXISTS is_active               BOOLEAN DEFAULT TRUE;
ALTER TABLE public.customer_master ADD COLUMN IF NOT EXISTS record_version          INT DEFAULT 1;
ALTER TABLE public.customer_master ADD COLUMN IF NOT EXISTS created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE public.customer_master ADD COLUMN IF NOT EXISTS updated_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP;

-- Indexes: exact match (primary rule), fuzzy match (secondary rule), survivorship ordering
CREATE UNIQUE INDEX IF NOT EXISTS ux_customer_master_gov_id_ssn_hash
    ON public.customer_master (gov_id_ssn_hash);
CREATE INDEX IF NOT EXISTS ix_customer_master_legal_name_trgm
    ON public.customer_master USING gin (lower(party_legal_name) gin_trgm_ops);
CREATE INDEX IF NOT EXISTS ix_customer_master_contact_phone
    ON public.customer_master (contact_phone);
CREATE INDEX IF NOT EXISTS ix_customer_master_name_phone
    ON public.customer_master (lower(party_legal_name), contact_phone);
CREATE INDEX IF NOT EXISTS ix_customer_master_source_updated_at
    ON public.customer_master (source_updated_at DESC);
CREATE INDEX IF NOT EXISTS ix_customer_master_merge_group
    ON public.customer_master (merge_group_id) WHERE merge_group_id IS NOT NULL;

-- updated_at / record_version maintenance trigger
CREATE OR REPLACE FUNCTION public.fn_customer_master_touch()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at     := CURRENT_TIMESTAMP;
    NEW.record_version := COALESCE(OLD.record_version, 0) + 1;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_customer_master_touch ON public.customer_master;
CREATE TRIGGER trg_customer_master_touch
    BEFORE UPDATE ON public.customer_master
    FOR EACH ROW EXECUTE FUNCTION public.fn_customer_master_touch();

-- Governance catalog metadata: PII classification + lineage
COMMENT ON TABLE  public.customer_master IS 'MDM golden record for KYC Party. Domain=Party; Owner=Data Governance; Lineage=customer_master_staging -> match/merge -> customer_master';
COMMENT ON COLUMN public.customer_master.party_legal_name IS 'PII:Confidential. Legal name of party. Secondary fuzzy match key (with contact_phone). Lineage: source_system.party_legal_name';
COMMENT ON COLUMN public.customer_master.contact_phone IS 'PII:Confidential. Digits only (E.164 without +). Secondary fuzzy match key (with party_legal_name). Lineage: source_system.contact_phone';
COMMENT ON COLUMN public.customer_master.gov_id_ssn IS 'PII:Restricted/Sensitive. Encrypted at rest (pgcrypto/KMS). Never exposed in plaintext; access limited to mdm_pii_reader role.';
COMMENT ON COLUMN public.customer_master.gov_id_ssn_hash IS 'PII:Restricted (derived token). SHA-256 salted hash of Gov_ID_SSN used as primary exact-match business key.';
COMMENT ON COLUMN public.customer_master.source_system IS 'Lineage: originating source system code.';
COMMENT ON COLUMN public.customer_master.source_record_id IS 'Lineage: natural key of the record in the originating source system.';
COMMENT ON COLUMN public.customer_master.source_updated_at IS 'Survivorship driver: most recent source timestamp wins on merge.';
COMMENT ON COLUMN public.customer_master.match_confidence_score IS 'Match engine score 0..1 for the surviving record.';
COMMENT ON COLUMN public.customer_master.merge_group_id IS 'Cluster identifier assigned by match/merge process.';

-- ---------------------------------------------------------------------
-- 2. ETL landing / staging table
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.customer_master_staging (
    id                      UUID            DEFAULT gen_random_uuid() PRIMARY KEY,
    batch_id                UUID            NOT NULL,
    source_system           VARCHAR(100)    NOT NULL,
    source_record_id        VARCHAR(255),
    source_updated_at       TIMESTAMP,
    party_legal_name        VARCHAR(255),
    contact_phone           VARCHAR(50),                                    -- raw; normalized to digits during cleansing
    gov_id_ssn              BYTEA,                                          -- encrypted on ingest; plaintext never persisted
    gov_id_ssn_hash         CHAR(64),
    load_status             VARCHAR(20)     NOT NULL DEFAULT 'LANDED',
    validation_errors       TEXT,
    matched_master_id       UUID,
    match_rule_applied      VARCHAR(50),
    match_confidence_score  DOUBLE PRECISION,
    is_processed            BOOLEAN         NOT NULL DEFAULT FALSE,
    loaded_at               TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP,
    processed_at            TIMESTAMP,
    created_at              TIMESTAMP       DEFAULT CURRENT_TIMESTAMP,
    updated_at              TIMESTAMP       DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ck_customer_master_staging_status CHECK (load_status IN ('LANDED','VALIDATED','REJECTED','MATCHED','MERGED','NEW')),
    CONSTRAINT fk_customer_master_staging_master FOREIGN KEY (matched_master_id) REFERENCES public.customer_master (id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS ix_cm_staging_batch        ON public.customer_master_staging (batch_id);
CREATE INDEX IF NOT EXISTS ix_cm_staging_ssn_hash     ON public.customer_master_staging (gov_id_ssn_hash);
CREATE INDEX IF NOT EXISTS ix_cm_staging_unprocessed  ON public.customer_master_staging (load_status) WHERE is_processed = FALSE;
CREATE INDEX IF NOT EXISTS ix_cm_staging_source       ON public.customer_master_staging (source_system, source_record_id);

COMMENT ON TABLE  public.customer_master_staging IS 'ETL landing zone for Party records prior to match/merge. Retention: purge after batch reconciliation.';
COMMENT ON COLUMN public.customer_master_staging.gov_id_ssn IS 'PII:Restricted. Encrypted on ingest.';
COMMENT ON COLUMN public.customer_master_staging.contact_phone IS 'PII:Confidential. Raw value; normalized to digits before promotion.';

-- ---------------------------------------------------------------------
-- 3. Match & merge / survivorship rule registry
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.mdm_match_rule (
    id                  UUID            DEFAULT gen_random_uuid() PRIMARY KEY,
    entity_name         VARCHAR(100)    NOT NULL,
    rule_code           VARCHAR(50)     NOT NULL,
    rule_type           VARCHAR(20)     NOT NULL,
    priority            INT             NOT NULL,
    match_columns       TEXT[]          NOT NULL,
    similarity_threshold DOUBLE PRECISION,
    survivorship_policy VARCHAR(50)     NOT NULL DEFAULT 'MOST_RECENT_SOURCE_WINS',
    survivorship_column VARCHAR(100)    NOT NULL DEFAULT 'source_updated_at',
    is_active           BOOLEAN         NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMP       DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP       DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_mdm_match_rule UNIQUE (entity_name, rule_code),
    CONSTRAINT ck_mdm_match_rule_type CHECK (rule_type IN ('EXACT','FUZZY')),
    CONSTRAINT ck_mdm_match_rule_threshold CHECK (similarity_threshold IS NULL OR (similarity_threshold >= 0 AND similarity_threshold <= 1))
);

INSERT INTO public.mdm_match_rule (entity_name, rule_code, rule_type, priority, match_columns, similarity_threshold)
VALUES
    ('customer_master', 'PARTY_EXACT_SSN',        'EXACT', 1, ARRAY['gov_id_ssn_hash'], NULL),
    ('customer_master', 'PARTY_FUZZY_NAME_PHONE', 'FUZZY', 2, ARRAY['party_legal_name','contact_phone'], 0.85)
ON CONFLICT (entity_name, rule_code) DO NOTHING;

COMMENT ON TABLE public.mdm_match_rule IS 'Match/merge rule registry. Rule 1: exact on gov_id_ssn_hash. Rule 2: fuzzy (trigram) on party_legal_name + contact_phone. Survivorship: most recent source_updated_at wins.';

-- ---------------------------------------------------------------------
-- 4. Access controls (role-based, column-level restriction on PII)
-- ---------------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'mdm_etl')        THEN CREATE ROLE mdm_etl NOLOGIN; END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'mdm_steward')    THEN CREATE ROLE mdm_steward NOLOGIN; END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'mdm_reader')     THEN CREATE ROLE mdm_reader NOLOGIN; END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'mdm_pii_reader') THEN CREATE ROLE mdm_pii_reader NOLOGIN; END IF;
END
$$;

REVOKE ALL ON public.customer_master, public.customer_master_staging, public.mdm_match_rule FROM PUBLIC;

GRANT SELECT, INSERT, UPDATE ON public.customer_master         TO mdm_etl;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.customer_master_staging TO mdm_etl;
GRANT SELECT ON public.mdm_match_rule                           TO mdm_etl;

GRANT SELECT, UPDATE ON public.customer_master                  TO mdm_steward;
GRANT SELECT ON public.customer_master_staging                  TO mdm_steward;
GRANT SELECT, INSERT, UPDATE ON public.mdm_match_rule           TO mdm_steward;

-- General readers: no access to encrypted SSN column
GRANT SELECT (id, party_legal_name, contact_phone, gov_id_ssn_hash, source_system, source_record_id, source_updated_at,
              match_confidence_score, merge_group_id, is_active, record_version, created_at, updated_at)
    ON public.customer_master TO mdm_reader;

-- PII readers: full access including encrypted column (decryption key managed outside DB)
GRANT SELECT ON public.customer_master TO mdm_pii_reader;

COMMIT;