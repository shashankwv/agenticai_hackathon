from etl.api_bridge import app

"""Compatibility entry point for the active ETL/PostgreSQL ingestion API."""

import uvicorn

from etl.api_bridge import app


if __name__ == "__main__":
    uvicorn.run("api_bridge:app", host="127.0.0.1", port=8000)
