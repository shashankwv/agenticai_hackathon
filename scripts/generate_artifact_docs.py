# scripts/generate_artifact_docs.py
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from core.state import ProjectState


def generate_ui_flowchart() -> str:
    """Generates a visual flowchart of the UI layout logic (Agent 02 output)."""
    return """# UI Architecture Flowchart (`app.py`)

```mermaid
flowchart TD
Start([User opens Streamlit App]) --> FormInit[Initialize Streamlit Form: 'party_form']
    
subgraph Inputs ["Dynamic Input Fields"]
FormInit --> PrimaryFields["Render Core Fields: id_prim, first_name, last_name"]
FormInit --> DateFields["Render Date Inputs: dob"]
FormInit --> IdentityFields["Render Gov IDs: aadhaar_no, tax_id"]
FormInit --> ContactFields["Render Contact Info: email_id, phone_number"]
end

Inputs --> Submit[User clicks 'Submit Record']
Submit --> CheckValid{Is Data Valid?}
CheckValid -- Yes --> JSONPayload[Display JSON Payload: st.json]
CheckValid -- No --> DisplayError[Show Streamlit Validation Error]
JSONPayload --> ForwardETL([Pass Payload to Agent 03 ETL Engine])
"""

def generate_etl_flowchart() -> str:
    """Generates a visual flowchart of the data transformation logic (Agent 03 output)."""
    return """# ETL Transformation Flowchart (etl.py)
```mermaid

flowchart TD
Start([Receive Raw Payload List]) --> LoopRecords[Iterate through records]

subgraph Cleansing ["Data Quality & Cleansing Engine"]
    LoopRecords --> TrimWhitespace["Strip Whitespace from Strings"]
    TrimWhitespace --> LowerEmail["Convert email_id to lowercase"]
    LowerEmail --> CleanPhone["Remove Non-Numeric Characters from Phone Numbers"]
    CleanPhone --> CleanAadhaar["Remove Spaces & Formatting from aadhaar_no"]
end

Cleansing --> DateCheck{Parse 'dob' Date?}
DateCheck -- Valid YYYY-MM-DD --> SetDate[Cast to datetime.date]
DateCheck -- Malformed/Invalid --> WarnDate[Log Warning & Set 'dob' = None]

SetDate & WarnDate --> MandatoryCheck{Contains Mandatory 'id_prim' & 'aadhaar_no'?}
MandatoryCheck -- Missing Required Field --> SkipRecord[Log Error & Skip Record]
MandatoryCheck -- Valid Required Fields --> CleanRecord[Append to Cleaned Dataset]

CleanRecord --> FinalOutput([Return Clean Payload to Target Store])

"""

def generate_mdm_flowchart() -> str:
    """Generates a visual flowchart of the MDM database governance logic (Agent 04 output)."""
    return """# MDM Schema Governance & DDL Flowchart (schema.sql)
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
"""

def main():
    docs_dir = PROJECT_ROOT / "docs" / "artifact_diagrams"
    docs_dir.mkdir(parents=True, exist_ok=True)

    # Write separate Markdown files for each generated code artifact
    (docs_dir / "ui_flowchart.md").write_text(generate_ui_flowchart())
    (docs_dir / "etl_flowchart.md").write_text(generate_etl_flowchart())
    (docs_dir / "mdm_flowchart.md").write_text(generate_mdm_flowchart())

    print(f"Successfully auto-generated artifact flowcharts in: {docs_dir}")

if __name__ == "__main__":
    main()
