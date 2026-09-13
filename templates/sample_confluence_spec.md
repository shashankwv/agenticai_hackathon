# Core Banking Customer 360 - Feature Specification: Aadhaar & Credit Scoring Integration

## 1. Overview
As part of our Core Banking Customer 360 initiative, we need to extend our customer onboarding and credit risk assessment models to capture mandatory Indian regulatory identifiers and automated credit health metrics.

## 2. Business Requirements

### UI Component (Frontend)
- Add a new input field for **Aadhaar Number** in the customer KYC registration form.
- The field must enforce a strict validation rule: exactly 12 numeric digits (`^\d{12}$`).
- Include a real-time validation error message if the format is invalid.
- Add a read-only display element for **Calculated Credit Score** retrieved from the bureau.

### ETL Pipeline (Data Engineering)
- Update the data ingestion script (`customer_onboarding_etl.py`) to parse and sanitize the incoming `aadhaar_no` field.
- Mask the middle 8 digits of the Aadhaar number when logging or outputting to non-secure streams (e.g., store as `XXXX-XXXX-1234`).
- Compute a preliminary risk index based on the customer's monthly income and credit history.

### MDM & Schema Governance (Database)
- Alter the `customer_master` relational table to include the new columns:
  - `aadhaar_no` VARCHAR(12) NOT NULL UNIQUE
  - `credit_score` INT CHECK (credit_score BETWEEN 300 AND 900)
- Update data governance DDL scripts and ensure migration validation rules pass before deployment.