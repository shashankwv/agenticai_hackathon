-- Production Master Table DDL for Customer KYC Records with Risk Scoring
-- Schema: public
-- Table: customer_master

-- Ensure UUID extension is available
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Create Customer KYC Master Data Table
CREATE TABLE IF NOT EXISTS public.customer_master (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    full_name VARCHAR(255) NOT NULL,
    pan_number VARCHAR(10) NOT NULL UNIQUE,
    masked_aadhaar VARCHAR(14) NOT NULL,
    monthly_income NUMERIC(15, 2) NOT NULL CHECK (monthly_income >= 0),
    credit_score INT CHECK (credit_score BETWEEN 300 AND 900),
    risk_index NUMERIC(5, 2) NOT NULL CHECK (risk_index >= 0 AND risk_index <= 100),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL
);

-- Performance Indexes for MDM queries and filtering
CREATE INDEX IF NOT EXISTS idx_customer_master_risk_index ON public.customer_master (risk_index);
CREATE INDEX IF NOT EXISTS idx_customer_master_credit_score ON public.customer_master (credit_score);

-- Column Comments for Schema Documentation
COMMENT ON TABLE public.customer_master IS 'Master table holding customer KYC data, risk scores, and financial profile.';
COMMENT ON COLUMN public.customer_master.pan_number IS 'Permanent Account Number - unique identifier for tax/identity matching.';
COMMENT ON COLUMN public.customer_master.masked_aadhaar IS 'Masked Aadhaar identifier in format XXXX-XXXX-1234 for compliance.';
COMMENT ON COLUMN public.customer_master.risk_index IS 'Calculated operational risk scoring index (0 to 100).';

-- Sample UPSERT Statement (Master Data Ingestion Logic based on PAN Number)
INSERT INTO public.customer_master (
    full_name,
    pan_number,
    masked_aadhaar,
    monthly_income,
    credit_score,
    risk_index
) VALUES (
    'Ananya Sharma',
    'ABCDE1234F',
    'XXXX-XXXX-1098',
    85000.00,
    765,
    22.50
)
ON CONFLICT (pan_number) 
DO UPDATE SET
    full_name = EXCLUDED.full_name,
    masked_aadhaar = EXCLUDED.masked_aadhaar,
    monthly_income = EXCLUDED.monthly_income,
    credit_score = EXCLUDED.credit_score,
    risk_index = EXCLUDED.risk_index,
    updated_at = CURRENT_TIMESTAMP;