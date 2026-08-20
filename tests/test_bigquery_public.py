"""BigQuery public-dataset tool — the refusals, not the happy path.

This is the one capability in the pipeline that holds credentials, so what
matters is what it REFUSES to send. The live query is a manual probe; a
unit test that hit BigQuery would bill the owner on every CI run.
"""
import os

os.environ.setdefault("AXON_FIRESTORE_MODE", "memory")

import pytest  # noqa: E402

from app.capabilities.registry import registry  # noqa: E402
from app.tools.bigquery_public import query_public_dataset  # noqa: E402

PUBLIC = (
    "SELECT name FROM `bigquery-public-data.usa_names.usa_1910_2013` "
    "LIMIT 5"
)


def test_registered_as_an_implemented_capability():
    import app.capabilities.bootstrap  # noqa: F401

    assert registry.is_implemented("read_dataset")


def test_empty_query_is_refused():
    assert query_public_dataset("  ")["status"] == "ERROR"


@pytest.mark.parametrize("sql", [
    "DELETE FROM `bigquery-public-data.usa_names.usa_1910_2013`",
    "DROP TABLE `bigquery-public-data.usa_names.usa_1910_2013`",
    "UPDATE `bigquery-public-data.x.y` SET a = 1",
    "INSERT INTO `bigquery-public-data.x.y` VALUES (1)",
    "CREATE TABLE `bigquery-public-data.x.z` AS SELECT 1",
    "TRUNCATE TABLE `bigquery-public-data.x.y`",
])
def test_write_and_ddl_statements_are_refused(sql):
    result = query_public_dataset(sql)

    assert result["status"] == "ERROR"


def test_select_with_a_hidden_write_keyword_is_refused():
    """A SELECT prefix must not smuggle a write past the check."""
    result = query_public_dataset(
        "SELECT 1 FROM `bigquery-public-data.x.y`; DROP TABLE users"
    )

    assert result["status"] == "ERROR"
    assert "write or DDL" in result["error"]


def test_non_public_dataset_is_refused():
    """Allowlist, not denylist: private tables are simply unreachable."""
    result = query_public_dataset(
        "SELECT * FROM `aion-axon-2026.private.customers`"
    )

    assert result["status"] == "ERROR"
    assert "bigquery-public-data" in result["error"]


def test_public_select_passes_validation(monkeypatch):
    """A legitimate query reaches the client rather than being refused.

    The client itself is stubbed -- a real call would bill the owner on
    every CI run.
    """
    sent = {}

    class FakeJob:
        total_bytes_processed = 1234
        cache_hit = True

        def result(self, max_results=None):
            return [{"name": "Mary"}, {"name": "John"}]

    class FakeClient:
        def __init__(self, project=None):
            sent["project"] = project

        def query(self, sql, job_config=None):
            sent["sql"] = sql
            sent["max_bytes"] = job_config.maximum_bytes_billed
            return FakeJob()

    import google.cloud.bigquery as bq

    monkeypatch.setattr(bq, "Client", FakeClient)

    result = query_public_dataset(PUBLIC)

    assert result["status"] == "SUCCESS"
    assert result["row_count"] == 2
    assert sent["sql"] == PUBLIC
    assert sent["max_bytes"] > 0, "byte cap must be sent to the API"


def test_rows_are_json_safe(monkeypatch):
    """Dates and Decimals must survive the trip to the sandbox."""
    from datetime import date
    from decimal import Decimal

    class FakeJob:
        total_bytes_processed = 1
        cache_hit = False

        def result(self, max_results=None):
            return [{"d": date(2026, 8, 20), "v": Decimal("1.50")}]

    class FakeClient:
        def __init__(self, project=None):
            pass

        def query(self, sql, job_config=None):
            return FakeJob()

    import json

    import google.cloud.bigquery as bq

    monkeypatch.setattr(bq, "Client", FakeClient)

    result = query_public_dataset(PUBLIC)

    json.dumps(result["rows"])  # must not raise
    assert result["rows"][0]["d"] == "2026-08-20"
