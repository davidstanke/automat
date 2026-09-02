# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Local stand-in for the `bigquery-mcp` stdio server.

Serves the catering menu from ``data/catering/catering_menu.json`` out of an
in-memory SQLite database, so the scheduling agent works without a real BigQuery
dataset. Without it you get ``404 Not found: Dataset <project>:catering`` unless
``scripts/04-cater-agent-bq-seed.sh`` has been run, and the agent quietly invents menu items.

Drop-in: it exposes the same three tools the real server does (``run_query``,
``list_tables_in_dataset``, ``get_table``) and accepts -- and ignores -- the
``--project/--location/--datasets`` flags the agent passes.

    export BIGQUERY_MCP_COMMAND="$PWD/agents/sched_agent/scripts/mock-bigquery-mcp"

The menu table is attached under the ``catering`` schema, so the BigQuery-style
``SELECT * FROM catering.menu_items`` the agent writes resolves unchanged.

Fidelity limits: SQLite is not BigQuery. Standard SELECT/WHERE/ORDER BY/LIMIT and
aggregates work; BigQuery-specific functions (UNNEST, VECTOR_SEARCH, ML.*, STRUCT
literals) do not. Repeated fields (``meal_types``, ``ingredients``, ``allergens``,
``dietary_labels``) are stored as JSON text rather than ARRAYs, so they are
searchable with LIKE but not UNNEST.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
from pathlib import Path
from typing import Any

from fastmcp import FastMCP

DATASET = "catering"
TABLE = "menu_items"
# app/ -> sched_agent/ -> agents/ -> repo root
MENU_PATH = (
    Path(__file__).resolve().parents[3] / "data" / "catering" / "catering_menu.json"
)
# Stored as JSON text; SQLite has no ARRAY type.
_REPEATED = ("meal_types", "ingredients", "allergens", "dietary_labels")

mcp = FastMCP("bigquery-mcp")


def _load(menu_path: Path) -> sqlite3.Connection:
    """Loads the NDJSON menu into ``catering.menu_items``."""
    rows = [
        json.loads(line)
        for line in menu_path.read_text().splitlines()
        if line.strip()
    ]
    if not rows:
        raise ValueError(f"no menu rows found in {menu_path}")

    connection = sqlite3.connect(":memory:", check_same_thread=False)
    connection.row_factory = sqlite3.Row
    # Attach as a schema so BigQuery-style `catering.menu_items` resolves as written.
    connection.execute(f"ATTACH ':memory:' AS {DATASET}")

    columns = list(rows[0])
    connection.execute(
        f"CREATE TABLE {DATASET}.{TABLE} ({', '.join(f'{c} TEXT' for c in columns)})"
    )
    connection.executemany(
        f"INSERT INTO {DATASET}.{TABLE} VALUES ({', '.join('?' * len(columns))})",
        [
            tuple(
                json.dumps(row.get(c)) if c in _REPEATED else row.get(c)
                for c in columns
            )
            for row in rows
        ],
    )
    connection.commit()
    return connection


_db: sqlite3.Connection | None = None
_columns: list[str] = []


def _normalise(query: str) -> str:
    """Rewrites BigQuery table references into what SQLite will accept."""
    query = query.replace("`", "")
    # Strip a leading project qualifier: project.catering.menu_items -> catering.menu_items
    query = re.sub(rf"[\w-]+\.({DATASET}\.{TABLE})", r"\1", query)
    # A bare table name still resolves to the attached schema.
    query = re.sub(rf"(?<![.\w]){TABLE}(?![\w.])", f"{DATASET}.{TABLE}", query)
    return query


def _error(message: str) -> dict[str, Any]:
    return {"success": False, "error": message}


@mcp.tool(
    description=(
        "Execute read-only BigQuery SQL queries with safety validation. Use LIMIT in your"
        " query to control result size (recommended: start with LIMIT 20)."
    )
)
async def run_query(query: str) -> dict[str, Any]:
    """Executes a read-only SELECT against the local catering menu."""
    if not re.match(r"^\s*(SELECT|WITH)\b", query, re.IGNORECASE):
        return _error("Only read-only SELECT queries are allowed.")
    try:
        rows = [dict(r) for r in _db.execute(_normalise(query)).fetchall()]
    except sqlite3.Error as error:
        return _error(
            f"{error}. Note: this is a local SQLite stand-in for BigQuery; "
            "BigQuery-specific functions such as UNNEST are unavailable."
        )
    for row in rows:  # hand back repeated fields as real lists
        for key in _REPEATED:
            if isinstance(row.get(key), str):
                try:
                    row[key] = json.loads(row[key])
                except json.JSONDecodeError:
                    pass
    return {"success": True, "data": rows, "total_count": len(rows)}


@mcp.tool(
    description="List tables in dataset with optional search, detailed information, and dataset context"
)
async def list_tables_in_dataset(
    dataset_id: str,
    search: str = "",
    detailed: bool = False,
    max_results: int | None = None,
) -> dict[str, Any]:
    """Lists the single table this stand-in serves."""
    if dataset_id != DATASET:
        return _error(f"Access to dataset '{dataset_id}' is not allowed")
    if search and search.lower() not in TABLE:
        return {"success": True, "data": [], "total_count": 0}
    count = _db.execute(f"SELECT COUNT(*) FROM {DATASET}.{TABLE}").fetchone()[0]
    table: dict[str, Any] = {"table_id": TABLE, "dataset_id": DATASET}
    if detailed:
        table["num_rows"] = count
    return {"success": True, "data": [table], "total_count": 1}


@mcp.tool(
    description="Get detailed table information with schema and column fill rate analysis"
)
async def get_table(dataset_id: str, table_id: str) -> dict[str, Any]:
    """Returns the menu table's schema and row count."""
    if dataset_id != DATASET or table_id != TABLE:
        return _error(f"Table '{dataset_id}.{table_id}' not found")
    count = _db.execute(f"SELECT COUNT(*) FROM {DATASET}.{TABLE}").fetchone()[0]
    return {
        "success": True,
        "data": {
            "table_id": TABLE,
            "dataset_id": DATASET,
            "num_rows": count,
            "schema": [
                {
                    "name": column,
                    "type": "STRING" if column not in ("id", "price") else "NUMERIC",
                    "mode": "REPEATED" if column in _REPEATED else "NULLABLE",
                }
                for column in _columns
            ],
        },
    }


def main() -> None:
    global _db, _columns
    parser = argparse.ArgumentParser(description=__doc__)
    # Accepted for drop-in compatibility with the real server; unused locally.
    parser.add_argument("--project")
    parser.add_argument("--location")
    parser.add_argument("--datasets")
    parser.add_argument("--menu-path", type=Path, default=MENU_PATH)
    args = parser.parse_args()

    _db = _load(args.menu_path)
    _columns = [
        r[1] for r in _db.execute(f"PRAGMA {DATASET}.table_info({TABLE})").fetchall()
    ]
    mcp.run()


if __name__ == "__main__":
    main()
