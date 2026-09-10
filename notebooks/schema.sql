-- Drop table if it already exists to ensure a clean creation (idempotency)
DROP TABLE IF EXISTS Party CASCADE;

-- Create the Party Master Data table
CREATE TABLE Party (
    -- Primary Key for the Party entity, ensuring uniqueness and referential integrity
    id_prim             VARCHAR(50)     PRIMARY KEY,
    -- Prospect or Active Status, indicating the party's current engagement state
    plss                VARCHAR(20)     NOT NULL,
    -- First Name of the party
    first_name          VARCHAR(100)    NOT NULL,
    -- Last Name of the party
    last_name           VARCHAR(100)    NOT NULL,
    -- Type of Tax Identification (e.g., PAN, SSN)
    tax_id_type         VARCHAR(20),
    -- Tax Identification Number
    tax_id              VARCHAR(50),
    -- Date of Birth of the party
    dob                 DATE,
    -- Legal Address of the party
    legal_addr          VARCHAR(255),
    -- Primary Correspondence Address of the party
    prim_addr           VARCHAR(255),
    -- Primary Phone Number
    phone_number        VARCHAR(20),
    -- Email Address
    email_id            VARCHAR(100),
    -- Aadhaar Number (Indian unique identification number)
    aadhaar_no          VARCHAR(12)     NOT NULL,
    -- Alternate Phone Number
    alternate_phone     VARCHAR(20),
    -- Standard MDM metadata: Timestamp when the record was created
    created_at          TIMESTAMP       DEFAULT CURRENT_TIMESTAMP NOT NULL,
    -- Standard MDM metadata: Timestamp when the record was last updated
    updated_at          TIMESTAMP       DEFAULT CURRENT_TIMESTAMP NOT NULL
);

-- Add comments to the table and columns for better documentation
COMMENT ON TABLE Party IS 'Master Data Management table for Banking Party entities.';
COMMENT ON COLUMN Party.id_prim IS 'Primary Party Identifier (Surrogate Key).';
COMMENT ON COLUMN Party.plss IS 'Prospect or Active Status of the party.';
COMMENT ON COLUMN Party.first_name IS 'First Name of the party.';
COMMENT ON COLUMN Party.last_name IS 'Last Name of the party.';
COMMENT ON COLUMN Party.tax_id_type IS 'Type of Tax Identification (e.g., PAN, SSN).';
COMMENT ON COLUMN Party.tax_id IS 'Tax Identification Number.';
COMMENT ON COLUMN Party.dob IS 'Date of Birth of the party.';
COMMENT ON COLUMN Party.legal_addr IS 'Legal Address of the party.';
COMMENT ON COLUMN Party.prim_addr IS 'Primary Correspondence Address of the party.';
COMMENT ON COLUMN Party.phone_number IS 'Primary Phone Number.';
COMMENT ON COLUMN Party.email_id IS 'Email Address.';
COMMENT ON COLUMN Party.aadhaar_no IS 'Aadhaar Number (Indian unique identification number).';
COMMENT ON COLUMN Party.alternate_phone IS 'Alternate Phone Number.';
COMMENT ON COLUMN Party.created_at IS 'Timestamp when the record was first created.';
COMMENT ON COLUMN Party.updated_at IS 'Timestamp when the record was last updated.';

-- Create a function to update the 'updated_at' column automatically
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create a trigger that calls the function before each UPDATE operation on the Party table
CREATE TRIGGER update_party_updated_at
BEFORE UPDATE ON Party
FOR EACH ROW
EXECUTE FUNCTION update_updated_at_column();

-- Example UPSERT (INSERT OR UPDATE) query for master record synchronization
-- This query attempts to insert a new party record.
-- If a record with the same 'id_prim' already exists, it updates the existing record
-- with the new values for specified columns, excluding 'created_at'.
INSERT INTO Party (
    id_prim, plss, first_name, last_name, tax_id_type, tax_id, dob,
    legal_addr, prim_addr, phone_number, email_id, aadhaar_no, alternate_phone
) VALUES (
    'PARTY_001', 'ACTIVE', 'John', 'Doe', 'PAN', 'ABCDE1234F', '1980-01-15',
    '123 Main St, Anytown', '123 Main St, Anytown', '555-123-4567', 'john.doe@example.com', '123456789012', '555-987-6543'
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
    updated_at = CURRENT_TIMESTAMP; -- Explicitly update updated_at, though trigger handles it too