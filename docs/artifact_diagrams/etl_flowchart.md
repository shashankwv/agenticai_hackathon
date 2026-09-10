# ETL Transformation Flowchart (etl.py)
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

