# agents/agent_04_mdm/step_05_postgres_executor.py
import os
import subprocess
import time
import psycopg2


def ensure_postgres_running(container_name: str = "mdm-postgres") -> bool:
  """Checks if PostgreSQL is running, and attempts to start or launch it if offline."""
  try:
    check_cmd = f"docker inspect -f '{{{{.State.Running}}}}' {container_name}"
    result = subprocess.run(
        check_cmd, shell=True, capture_output=True, text=True
    )

    if result.stdout.strip() == "true":
      return True

    print(
        f"⚠️ [Self-Healing Engine] PostgreSQL container '{container_name}' is"
        " not running."
    )

    exists_cmd = (
        f"docker ps -a --format '{{{{.Names}}}}' | grep -w {container_name}"
    )
    exists_result = subprocess.run(
        exists_cmd, shell=True, capture_output=True, text=True
    )

    if container_name in exists_result.stdout:
      print(
          "🔄 [Self-Healing Engine] Attempting to start existing container"
          f" '{container_name}'..."
      )
      subprocess.run(
          f"docker start {container_name}",
          shell=True,
          check=True,
          capture_output=True,
      )
    else:
      print(
          "🚀 [Self-Healing Engine] Container"
          f" '{container_name}' not found. Spawning new PostgreSQL container..."
      )
      run_cmd = (
          f"docker run --name {container_name} -e POSTGRES_DB=mdm_db -e"
          " POSTGRES_USER=postgres -e POSTGRES_PASSWORD=postgres -p 5432:5432"
          " -d postgres:latest"
      )
      subprocess.run(run_cmd, shell=True, check=True, capture_output=True)

    print(
        "⏳ [Self-Healing Engine] Waiting for PostgreSQL service to accept"
        " connections..."
    )
    for _ in range(10):
      time.sleep(1)
      try:
        conn = psycopg2.connect(
            "postgresql://postgres:postgres@localhost:5432/mdm_db"
        )
        conn.close()
        print(
            "✅ [Self-Healing Engine] PostgreSQL connection restored"
            " successfully!"
        )
        return True
      except psycopg2.OperationalError:
        continue

    return False

  except Exception as e:
    print(
        f"❌ [Self-Healing Engine] Failed to self-heal PostgreSQL container: {e}"
    )
    return False


def execute_mdm_on_postgres(
    ddl_sql: str, db_uri: str = None, auto_heal: bool = True
) -> dict:
  """Connects to target PostgreSQL DB and executes DDL.

  Includes self-healing capabilities if connection is refused.
  """
  if not ddl_sql:
    return {"status": "FAILED", "error": "No DDL SQL provided for execution."}

  connection_string = db_uri or os.getenv(
      "POSTGRES_CONNECTION_URI",
      "postgresql://postgres:postgres@localhost:5432/mdm_db",
  )

  for attempt in range(2):
    try:
      conn = psycopg2.connect(connection_string)
      conn.autocommit = True
      cursor = conn.cursor()

      statements = [stmt.strip() for stmt in ddl_sql.split(";") if stmt.strip()]
      executed_count = 0

      for statement in statements:
        cursor.execute(statement)
        executed_count += 1

      cursor.close()
      conn.close()

      return {
          "status": "SUCCESS",
          "message": (
              f"Successfully executed {executed_count} SQL statements on"
              " PostgreSQL."
          ),
          "target": connection_string.split("@")[-1],
      }

    except psycopg2.OperationalError as e:
      if "Connection refused" in str(e) and auto_heal and attempt == 0:
        print(
            "\n🔧 [Self-Healing Triggered] Connection refused on port 5432."
            " Initiating auto-recovery..."
        )
        healed = ensure_postgres_running("mdm-postgres")
        if healed:
          print(
              "🔄 [Self-Healing Engine] Retrying execution after recovery..."
          )
          continue

      return {
          "status": "FAILED",
          "error": str(e),
          "message": (
              "Execution failed on target PostgreSQL instance after"
              " self-healing attempt."
          ),
      }
    except Exception as e:
      return {
          "status": "FAILED",
          "error": str(e),
          "message": "Execution failed due to SQL or schema error.",
      }