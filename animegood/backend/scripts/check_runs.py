import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.settings import get_settings

conn = sqlite3.connect(get_settings().database_path)
conn.row_factory = sqlite3.Row
rows = conn.execute(
    """
    SELECT source_id, status, message, product_count, finished_at
    FROM source_runs
    WHERE source_id IN ('mono-mo', 'shop-anique', 'shibuyatsutaya')
    ORDER BY id DESC
    LIMIT 12
    """
).fetchall()
for row in rows:
    print(dict(row))
