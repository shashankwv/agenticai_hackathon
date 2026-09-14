import os
import duckdb
import pandas as pd

def run_etl_in_duckdb(etl_code: str, raw_payloads: list[dict], db_path: str = "staging.duckdb") -> dict:
    """
    Generic execution runner for dynamic ETL pipelines.
    Executes generated Python transformation logic and dynamically persists 
    the results into DuckDB without hardcoding any schemas or table columns.
    """
    # 1. Save generated ETL script to project root for audit & execution
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    etl_script_path = os.path.join(project_root, "etl_pipeline.py")
    
    with open(etl_script_path, "w", encoding="utf-8") as f:
        f.write(etl_code)
    print(f"Persisted dynamic ETL script to: {etl_script_path}")

    # 2. Execute generated code in local scope to extract the transformation entry point
    local_scope = {}
    exec(etl_code, local_scope, local_scope)

    transform_fn = local_scope.get("transform_batch")
    if not transform_fn:
        # Fallback search for clean or transform callable
        for name, obj in local_scope.items():
            if callable(obj) and ("transform" in name or "clean" in name):
                transform_fn = obj
                break

    if not transform_fn:
        raise RuntimeError("No transformation entrypoint function found in generated ETL code.")

    # 3. Dynamically process raw payloads
    cleansed_records = transform_fn(raw_payloads)

    if not cleansed_records:
        return {"status": "SUCCESS", "processed_count": 0, "sample_output": {}}

    # 4. Connect to DuckDB and dynamically store cleansed output without fixed DDL
    conn = duckdb.connect(os.path.join(project_root, db_path))
    
    df_transformed = pd.DataFrame(cleansed_records)
    
    # DuckDB automatically inspects DataFrame columns and registers the structure
    conn.register("temp_cleansed_df", df_transformed)
    conn.execute("CREATE TABLE IF NOT EXISTS cleansed_staging_data AS SELECT * FROM temp_cleansed_df")
    conn.execute("INSERT INTO cleansed_staging_data SELECT * FROM temp_cleansed_df")
    
    conn.close()

    return {
        "status": "SUCCESS",
        "processed_count": len(cleansed_records),
        "sample_output": cleansed_records[0]
    }