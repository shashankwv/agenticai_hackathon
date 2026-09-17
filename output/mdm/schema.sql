-- Adding pan_no column to support Master Schema Governance and audit logging
 -- The sample payload includes pan_no which is not present in the existing customer_master schema.
 -- This ensures the table captures the alternate contact number for compliance.
 -- Added as VARCHAR(17) to accommodate the standard 17-digit PAN format.
 ALTER TABLE public.customer_master
 ADD COLUMN pan_no VARCHAR(17);