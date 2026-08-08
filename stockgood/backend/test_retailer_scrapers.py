import asyncio
import unittest
from unittest.mock import AsyncMock, patch

import httpx
from app.scrapers.biccamera import is_biccamera_blocked_page, is_biccamera_url
from app.scrapers.hmv import is_hmv_empty_shell, is_hmv_url
from app.scrapers.preview import _fetch_retailer_html


class RetailerScraperDetectionTests(unittest.TestCase):
    def test_hmv_empty_netfunnel_shell_is_detected(self) -> None:
        html = """
        <html><head>
          <title></title>
          <meta property="og:title" content="">
          <meta property="og:image" content="https://www.hmv.co.jp/logo.png">
          <script src="https://agent-lib.stclab.com/agent/1.0/netfunnel-javascript-agent.js"></script>
        </head><body></body></html>
        """
        self.assertTrue(is_hmv_url("https://www.hmv.co.jp/product/123"))
        self.assertTrue(is_hmv_empty_shell(html))
        self.assertFalse(
            is_hmv_empty_shell(
                "<title>商品名 | HMV&BOOKS online</title>"
                '<meta property="og:title" content="商品名">'
            )
        )

    def test_biccamera_block_page_is_detected(self) -> None:
        html = """
        <html><head><title>Access Denied</title></head>
        <body>アクセスが集中しています。しばらく時間をおいてから再度お試しください。</body>
        </html>
        """
        self.assertTrue(is_biccamera_url("https://www.biccamera.com/bc/item/15189149/"))
        self.assertTrue(is_biccamera_blocked_page(html))
        self.assertFalse(
            is_biccamera_blocked_page("<title>商品名 | ビックカメラ.com</title>")
        )

    def test_hmv_empty_shell_is_retried(self) -> None:
        attempts = 0
        empty_shell = (
            "<title></title><meta property='og:title' content=''>"
            "<script src='https://agent-lib.stclab.com/netfunnel.js'></script>"
        )

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal attempts
            attempts += 1
            body = empty_shell if attempts == 1 else "<title>商品名</title>"
            return httpx.Response(200, text=body, request=request)

        async def fetch() -> httpx.Response | None:
            async with httpx.AsyncClient(
                transport=httpx.MockTransport(handler)
            ) as client:
                return await _fetch_retailer_html(
                    client, "https://www.hmv.co.jp/product/123"
                )

        with patch(
            "app.scrapers.preview.asyncio.sleep", new=AsyncMock()
        ) as sleep:
            response = asyncio.run(fetch())

        self.assertEqual(attempts, 2)
        self.assertEqual(response.status_code if response else None, 200)
        sleep.assert_awaited_once_with(1.5)
