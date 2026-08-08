import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.settings import get_settings

conn = sqlite3.connect(get_settings().database_path)
rows = conn.execute(
    """
    SELECT product_name, price, stock_status, source_url
    FROM products
    WHERE shop = 'SHIBUYA TSUTAYA'
    ORDER BY id DESC
    LIMIT 5
    """
).fetchall()
for index, row in enumerate(rows, start=1):
    name, price, stock, url = row
    print(f"{index}. {name}")
    print(f"   价格: {price} 円 | 库存: {stock}")
    print(f"   {url}")
