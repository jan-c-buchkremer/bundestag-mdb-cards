"""tests/schema.sql must be the foundation's SCHEMA; skipped when no foundation checkout is next to this repo."""

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "schema_sql.py"
_spec = importlib.util.spec_from_file_location("schema_sql", SCRIPT)
schema_sql = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(schema_sql)


def test_schema_matches_foundation():
    repo = schema_sql.foundation_repo()
    if not (repo / "src" / "bdf" / "db.py").exists():
        pytest.skip(f"no foundation checkout at {repo}")
    expected = schema_sql.render(schema_sql.load_schema(repo))
    assert schema_sql.TARGET.read_text(encoding="utf-8") == expected, (
        "tests/schema.sql differs from the foundation's SCHEMA: run `uv run python scripts/schema_sql.py`"
    )
