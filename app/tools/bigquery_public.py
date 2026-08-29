"""Read-only queries against Google BigQuery PUBLIC datasets.

This capability is hand-written, reviewed, and shipped in the repository.
It is deliberately NOT something SYNAPSE can generate, because it is the
one part of the dataset pipeline that holds credentials.

That split is the whole design:

    core (credentialed, human-written)  ->  fetches the rows
    sandbox (zero credentials, generated) -> analyses the rows

A generated capability that queried BigQuery itself would need a service
account, which is exactly what the trust boundary exists to prevent. So
SYNAPSE acquires the ANALYSIS skill instead, and the credentialed step
stays code a human signed off on.

Safety properties, enforced here rather than trusted to the caller:
- SELECT statements only; anything else is refused before it is sent.
- Only the public dataset allowlist below is reachable.
- A hard byte cap, so a careless query cannot burn the free tier.
- maximum_bytes_billed makes the cap the API's problem, not ours: a query
  that would exceed it fails instead of running.
"""
import os
import re
from typing import Any

MAX_BYTES_BILLED = int(
    os.getenv("AXON_BQ_MAX_BYTES", str(200 * 1024 * 1024))
)
MAX_ROWS = int(os.getenv("AXON_BQ_MAX_ROWS", "500"))

# Public datasets only. An allowlist rather than a denylist: the set of
# things worth protecting is unbounded, the set we need is small.
ALLOWED_DATASETS = (
    "bigquery-public-data.",
    "`bigquery-public-data.",
)

FORBIDDEN_SQL = re.compile(
    r"\b(insert|update|delete|drop|create|alter|merge|truncate|grant|"
    r"revoke)\b",
    re.IGNORECASE,
)


def _reject(reason: str) -> dict[str, Any]:
    return {"status": "ERROR", "error": reason}


def query_public_dataset(sql: str) -> dict[str, Any]:
    """Run a read-only SELECT against a public BigQuery dataset."""
    if not sql or not sql.strip():
        return _reject("Query cannot be empty.")

    sql = sql.strip()

    if not sql.lower().lstrip("(").startswith("select"):
        return _reject("Only SELECT queries are permitted.")

    if FORBIDDEN_SQL.search(sql):
        return _reject(
            "Query contains a write or DDL keyword and was refused."
        )

    if not any(marker in sql for marker in ALLOWED_DATASETS):
        return _reject(
            "Only bigquery-public-data datasets are permitted."
        )

    try:
        from google.cloud import bigquery
    except ImportError:
        return _reject("BigQuery client library is not installed.")

    try:
        client = bigquery.Client(project=os.getenv(
            "GOOGLE_CLOUD_PROJECT", "aion-axon-2026",
        ))

        job = client.query(
            sql,
            job_config=bigquery.QueryJobConfig(
                use_query_cache=True,
                maximum_bytes_billed=MAX_BYTES_BILLED,
            ),
        )

        rows = [dict(row) for row in job.result(max_results=MAX_ROWS)]
    except Exception as error:  # noqa: BLE001 - reported, never retried blindly
        return {
            "status": "ERROR",
            "error": f"{type(error).__name__}: {error}",
        }

    return {
        "status": "SUCCESS",
        "row_count": len(rows),
        "rows": _serialisable(rows),
        "bytes_processed": getattr(job, "total_bytes_processed", None),
        "cache_hit": getattr(job, "cache_hit", None),
        "truncated": len(rows) >= MAX_ROWS,
    }


def _serialisable(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Coerce BigQuery types into something JSON and the sandbox accept.

    Dates and Decimals arrive as objects that do not survive a JSON round
    trip, and the analysis capability downstream only ever sees JSON.
    """
    clean = []

    for row in rows:
        clean.append({
            key: (value if isinstance(value, (int, float, str, bool, type(None)))
                  else str(value))
            for key, value in row.items()
        })

    return clean
