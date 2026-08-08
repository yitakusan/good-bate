from app.scrapers.html_news import matches_keywords, parse_published_at


def test_include_keywords_any_match():
    assert matches_keywords(
        "コラボカフェ開催のお知らせ",
        include_keywords=["カフェ", "POP UP"],
        exclude_keywords=[],
    )
    assert not matches_keywords(
        "新作グッズ入荷",
        include_keywords=["カフェ", "POP UP"],
        exclude_keywords=[],
    )


def test_exclude_keywords():
    assert not matches_keywords(
        "休業のお知らせ",
        include_keywords=[],
        exclude_keywords=["休業"],
    )


def test_empty_include_keeps_all():
    assert matches_keywords("anything", include_keywords=[], exclude_keywords=[])


def test_parse_published_at_ja_and_iso():
    assert parse_published_at("2026年7月16日") == "2026-07-16"
    assert parse_published_at("2026-07-10T12:00:00Z") == "2026-07-10"
