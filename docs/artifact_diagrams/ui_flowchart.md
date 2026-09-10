# UI Architecture Flowchart (`app.py`)

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
