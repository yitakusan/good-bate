import asyncio

from app.pipeline import ScrapePipeline
from app.settings import Settings
from app.source_config import load_sources


async def main() -> None:
    settings = Settings()
    source = next(item for item in load_sources(settings.source_config_path) if item.id == "hakusensha-shop")
    result = await ScrapePipeline(settings).run_source(source, limit=3)
    print(result)


if __name__ == "__main__":
    asyncio.run(main())
