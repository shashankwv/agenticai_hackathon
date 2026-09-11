-- Drop table if it already exists to ensure a clean creation (idempotency)
DROP TABLE IF EXISTS Party CASCADE;

-- Create the Party Master Data table
CREATE TABLE Party (
    -- Primary Key for the Party entity
    id_prim             VARCHAR(50)     PRIMARY KEY, -- Primary Party Identifier
    
    -- Core Party Attributes
    plss                VARCHAR(20)     NOT NULL,    -- Prospect or Active Status
    first_name          VARCHAR(100)    NOT NULL,    -- First Name
    last_name           VARCHAR(100)    NOT NULL,    -- Last Name
    tax_id_type         VARCHAR(20),                 -- Tax Identification Type
    tax_id              VARCHAR(50),                 -- Tax Identification Number
    dob                 DATE,                        -- Date of Birth
    legal_addr          VARCHAR(255),                -- Legal Address
    prim_addr           VARCHAR(255),                -- Primary Address
    phone_number        VARCHAR(20),                 -- Phone Number
    email_id            VARCHAR(100),                -- Email Address
    aadhaar_no          VARCHAR(12)     NOT NULL,    -- Aadhaar Number (Indian unique identification number)
    alternate_phone     VARCHAR(20),                 -- Alternate Phone Number

    -- Standard MDM Metadata for auditing and tracking
    created_at          TIMESTAMP       DEFAULT CURRENT_TIMESTAMP NOT NULL, -- Timestamp when the record was created
    updated_at          TIMESTAMP       DEFAULT CURRENT_TIMESTAMP NOT NULL  -- Timestamp when the record was last updated
);

-- Add comments to the table and columns for better documentation
COMMENT ON TABLE Party IS 'Master Data Management table for Banking Party entities.';
COMMENT ON COLUMN Party.id_prim IS 'Primary Party Identifier, unique across all parties.';
COMMENT ON COLUMN Party.plss IS 'Status of the party: e.g., ''Prospect'', ''Active'', ''Inactive''.';
COMMENT ON COLUMN Party.first_name IS 'Legal first name of the party.';
COMMENT ON COLUMN Party.last_name IS 'Legal last name of the party.';
COMMENT ON COLUMN Party.tax_id_type IS 'Type of tax identification (e.g., ''PAN'', ''SSN'').';
COMMENT ON COLUMN Party.tax_id IS 'Tax identification number.';
COMMENT ON COLUMN Party.dob IS 'Date of birth of the party.';
COMMENT ON COLUMN Party.legal_addr IS 'Official legal address of the party.';
COMMENT ON COLUMN Party.prim_addr IS 'Primary mailing or contact address of the party.';
COMMENT ON COLUMN Party.phone_number IS 'Primary contact phone number.';
COMMENT ON COLUMN Party.email_id IS 'Primary contact email address.';
COMMENT ON COLUMN Party.aadhaar_no IS 'Aadhaar Number, a unique identification number issued by the Indian government.';
COMMENT ON COLUMN Party.alternate_phone IS 'Alternate contact phone number.';
COMMENT ON COLUMN Party.created_at IS 'Timestamp when this master record was first created.';
COMMENT ON COLUMN Party.updated_at IS 'Timestamp when this master record was last updated.';

-- Create a function to update the 'updated_at' column automatically
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create a trigger to call the function before each UPDATE operation on the Party table
CREATE TRIGGER update_party_updated_at
BEFORE UPDATE ON Party
FOR EACH ROW
EXECUTE FUNCTION update_updated_at_column();

-- Example UPSERT (INSERT OR UPDATE) query for master record synchronization
-- This query attempts to insert a new party record. If a record with the same id_prim
-- already exists, it updates the existing record with the new values.
INSERT INTO Party (
    id_prim, plss, first_name, last_name, tax_id_type, tax_id, dob,
    legal_addr, prim_addr, phone_number, email_id, aadhaar_no, alternate_phone
) VALUES (
    'PARTY_001', 'Active', 'John', 'Doe', 'PAN', 'ABCDE1234F', '1980-01-15',
    '123 Main St, Anytown', '123 Main St, Anytown', '555-123-4567', 'john.doe@example.com', '123456789012', NULL
)
ON CONFLICT (id_prim) DO UPDATE SET
    plss = EXCLUDED.plss,
    first_name = EXCLUDED.first_name,
    last_name = EXCLUDED.last_name,
    tax_id_type = EXCLUDED.tax_id_type,
    tax_id = EXCLUDED.tax_id,
    dob = EXCLUDED.dob,
    legal_addr = EXCLUDED.legal_addr,
    prim_addr = EXCLUDED.prim_addr,
    phone_number = EXCLUDED.phone_number,
    email_id = EXCLUDED.email_id,
    aadhaar_no = EXCLUDED.aadhaar_no,
    alternate_phone = EXCLUDED.alternate_phone,
    updated_at = NOW(); -- Explicitly update updated_at, though trigger would also handle it.
                         -- Explicitly setting it here ensures it's updated even if the trigger is temporarily disabled.