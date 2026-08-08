from app.exchange_rate import parse_rmb_jpy_line, parse_rmb_js, parse_tbl_rmbjpy_html


def test_parse_rmb_jpy_line_applies_alipay_markup() -> None:
    data = parse_rmb_jpy_line("日元,4.174,4.174,4.206,4.206,4.196,2026-07-08,07:18:11")

    assert data.currency_name == "日元"
    assert data.spot_cny_per_100_jpy == 4.196
    assert data.cny_per_100_jpy == 4.204
    assert data.updated_at == "2026-07-08 07:18:11"


def test_parse_rmb_js_extracts_rmBJPY() -> None:
    js = 'var hq_str_RMBJPY="日元,4.174,4.174,4.206,4.206,4.196,2026-07-08,07:18:11";'
    data = parse_rmb_js(js)

    assert data.cny_per_100_jpy == 4.204


def test_parse_tbl_rmbjpy_html_reads_rendered_span() -> None:
    html = '<span class="jgjg" id="tbl_RMBJPY"><span class="up">4.204</span></span>'
    assert parse_tbl_rmbjpy_html(html) == 4.204


def test_parse_tbl_rmbjpy_html_returns_none_when_empty() -> None:
    html = '<span class="jgjg" id="tbl_RMBJPY"></span>'
    assert parse_tbl_rmbjpy_html(html) is None
