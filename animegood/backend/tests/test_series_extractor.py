from app.series_extractor import extract_series


def test_quoted_series():
    name = "【渋谷店受取】『アオペラ -aoppella!?- 8』豪華初回限定盤　選べる推し！宗円寺雨夜セット《MJSS09421》"
    assert extract_series(name) == "アオペラ -aoppella!?- 8"


def test_bracket_series_skips_shipping():
    name = "【ノラネコぐんだん】 フロートグラス　うみ"
    assert extract_series(name) == "ノラネコぐんだん"
    skip = "【渋谷店受取】&TEAM『Mark on Me』通常盤《HYBJ10029》"
    assert extract_series(skip) == "Mark on Me"


def test_series_word():
    assert extract_series("クリスマスシリーズ アクリルスタンド") == "クリスマス"


def test_festival_prefix():
    name = "第2回ゆるフェス△　富士山アクリルスタンド（土岐綾乃）"
    assert "ゆるフェス" in (extract_series(name) or "")


def test_none_for_short():
    assert extract_series("abc") is None
