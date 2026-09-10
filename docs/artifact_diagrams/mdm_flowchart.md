# MDM Schema Governance & DDL Flowchart (schema.sql)
```mermaid
flowchart TD
Start([Execute MDM Migration Script]) --> TableCheck{Table 'mdm_partymaster' Exists?}

TableCheck -- No --> CreateTable["CREATE TABLE mdm_partymaster"]
CreateTable --> SetPK["Set Primary Key: id_prim VARCHAR(50)"]
SetPK --> SetConstraints["Apply NOT NULL Constraints on required fields"]
SetConstraints --> TableReady[Table Ready for Ingestion]

TableCheck -- Yes --> TableReady

TableReady --> UpsertInit([Incoming Clean Record from ETL Engine])
UpsertInit --> UpsertQuery["Execute UPSERT: INSERT INTO mdm_partymaster"]
UpsertQuery --> ConflictCheck{"ON CONFLICT (id_prim)?"}

ConflictCheck -- New Primary Key --> InsertRow[Insert New Customer Record]
ConflictCheck -- Existing Primary Key --> UpdateRow[DO UPDATE SET attributes]

InsertRow & UpdateRow --> Commit([Commit Transaction to Master Store])
