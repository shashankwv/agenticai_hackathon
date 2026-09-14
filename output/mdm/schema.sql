-- Production PostgreSQL DDL Script for Customer Master Data Management (MDM)
-- Target Schema: public
-- Target Table: customer_master

-- 1. Table Creation with Data Governance and Constraints
CREATE TABLE IF NOT EXISTS public.customer_master (
    -- Unique Primary Key using UUID v4 for distributed MDM entity resolution
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    
    -- Customer Identification Attributes
    full_name VARCHAR(255) NOT NULL,
    pan_number VARCHAR(10) NOT NULL UNIQUE, -- Permanent Account Number (India)
    aadhaar_no VARCHAR(12) NOT NULL UNIQUE, -- 12-digit Unique National ID
    masked_aadhaar VARCHAR(14),            -- PII governance masked format e.g., 'XXXX-XXXX-1098'
    
    -- Financial and Credit Risk Attributes
    monthly_income DOUBLE PRECISION,
    credit_score INT CHECK (credit_score BETWEEN 300 AND 900), -- Standard credit score rating bounds
    risk_index DOUBLE PRECISION,
    
    -- Standard MDM Audit Trail Attributes
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL
);

-- Inline Comments on Column Business Meaning and Security Requirements
COMMENT ON TABLE public.customer_master IS 'Master Data Management (MDM) table storing canonical golden customer records.';
COMMENT ON COLUMN public.customer_master.aadhaar_no IS 'Unmasked 12-digit Aadhaar number, restricted access governed by PII policies.';
COMMENT ON COLUMN public.customer_master.masked_aadhaar IS 'Masked Aadhaar representation for lower-tier reporting applications.';
COMMENT ON COLUMN public.customer_master.credit_score IS 'Credit score rating ranging from 300 to 900.';

-- 2. Index Creation for Fast Lookup and Match/Merge Operations
CREATE UNIQUE INDEX IF NOT EXISTS idx_customer_master_pan ON public.customer_master(pan_number);
CREATE UNIQUE INDEX IF NOT EXISTS idx_customer_master_aadhaar ON public.customer_master(aadhaar_no);
CREATE INDEX IF NOT EXISTS idx_customer_master_credit_score ON public.customer_master(credit_score);

-- 3. Demonstration of Atomic UPSERT Operations (PostgreSQL ON CONFLICT)
-- Inserts a new customer golden record or updates attributes if the Aadhaar number already exists.
INSERT INTO public.customer_master (
    full_name,
    pan_number,
    aadhaar_no,
    masked_aadhaar,
    monthly_income,
    credit_score,
    risk_index
) VALUES (
    'Ananya Sharma',
    'ABCDE1234F',
    '999988881098',
    'XXXX-XXXX-1098',
    85000.0,
    765,
    22.5
)
ON CONFLICT (aadhaar_no) DO UPDATE SET
    full_name = EXCLUDED.full_name,
    pan_number = EXCLUDED.pan_number,
    masked_aadhaar = EXCLUDED.masked_aadhaar,
    monthly_income = EXCLUDED.monthly_income,
    credit_score = EXCLUDED.credit_score,
    risk_index = EXCLUDED.risk_index,
    updated_at = CURRENT_TIMESTAMP;