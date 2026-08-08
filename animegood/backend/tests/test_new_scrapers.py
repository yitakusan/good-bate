from app.scrapers.color_me import SHOP_ITEM_PATH
from app.scrapers.ec_cube import EcCubeHtmlScraper
from app.scrapers.ochanoko import ITEM_PATH


def test_ochanoko_item_path():
    html = '<a href="/view/item/000000000887?category_page_id=all_items">item</a>'
    assert ITEM_PATH.findall(html) == ["000000000887"]


def test_colorme_shop_path_ignores_sitemap():
    html = '<a href="/shop/sitemap.html"></a><a href="/SHOP/IR-DOR-001.html"></a>'
    assert SHOP_ITEM_PATH.findall(html) == ["/SHOP/IR-DOR-001.html"]


def test_eccube_extract_detail_urls():
    scraper = EcCubeHtmlScraper()
    html = (
        '<a href="/products/detail/188388"></a>'
        '<a href="/products/detail.php?product_id=194"></a>'
        '<a href="/products/detail/${p.id}"></a>'
    )
    urls = scraper._extract_detail_urls("https://vvstore.jp/", html)
    assert urls == [
        "https://vvstore.jp/products/detail/188388",
        "https://vvstore.jp/products/detail.php?product_id=194",
    ]
