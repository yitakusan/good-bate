import asyncio

from app.database import connect
from app.pipeline import ScrapePipeline
from app.settings import Settings, get_settings


async def main() -> None:
    settings = Settings(scrape_concurrency=3)
    result = await ScrapePipeline(settings).run_all(limit_per_source=5)
    print("run_all", result)
    with connect(get_settings().database_path) as conn:
        row = conn.execute(
            """
            SELECT status, message, product_count
            FROM source_runs
            WHERE source_id = 'shibuyatsutaya'
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()
        print("shibuya latest", row)


if __name__ == "__main__":
    asyncio.run(main())
