import sqlite3
from pathlib import Path

conn = sqlite3.connect(Path(__file__).resolve().parents[1] / "data" / "animegood.sqlite")
rows = conn.execute(
    """
    SELECT source_id, shop, source_platform, status, message, finished_at
    FROM source_runs
    WHERE message LIKE '%NotImplemented%' OR message LIKE '%未实现%'
    ORDER BY id DESC
    LIMIT 20
    """
).fetchall()
for row in rows:
    print(row)
