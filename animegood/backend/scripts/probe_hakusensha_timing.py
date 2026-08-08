import time

import httpx

BASE = "https://goods.hakusensha-shop.jp/"
headers = {"User-Agent": "Mozilla/5.0 Chrome/126"}

with httpx.Client(timeout=90, follow_redirects=True, headers=headers) as client:
    for url in [
        BASE + "products/list",
        BASE + "products/detail/10001",
    ]:
        start = time.perf_counter()
        try:
            response = client.get(url)
            elapsed = time.perf_counter() - start
            print(url, response.status_code, f"{elapsed:.1f}s", len(response.text))
        except Exception as exc:
            print(url, "ERR", exc, f"{time.perf_counter() - start:.1f}s")
