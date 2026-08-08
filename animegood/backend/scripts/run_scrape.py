import asyncio

from app.database import init_db
from app.pipeline import ScrapePipeline
from app.settings import get_settings


async def main() -> None:
    settings = get_settings()
    init_db(settings.database_path)
    result = await ScrapePipeline(settings).run_all()
    print(
        f"抓取完成：数据源 {result['sources']} 个，"
        f"入库 {result['stored']} 条，失败 {result['failed']} 个"
    )


if __name__ == "__main__":
    asyncio.run(main())
