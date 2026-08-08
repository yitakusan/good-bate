import asyncio
import os

os.environ.pop("PLAYWRIGHT_BROWSERS_PATH", None)

from playwright.async_api import async_playwright


async def main() -> None:
    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            await browser.close()
        print("launch ok")
    except Exception as exc:
        print(type(exc).__name__, len(str(exc)))
        print(str(exc)[:500])


if __name__ == "__main__":
    asyncio.run(main())
