from datetime import date

from app.event_expiry import format_end_date, is_event_expired, parse_event_end_date, resolve_event_expiry


def test_parse_range_japanese():
    end = parse_event_end_date(
        "『ペルソナ』POP UP STORE 2025年3月1日(土)〜3月15日(日)",
        reference=date(2025, 3, 10),
    )
    assert end == date(2025, 3, 15)


def test_parse_range_slash():
    end = parse_event_end_date(
        "コラボカフェ開催 2025/3/1〜3/20",
        reference=date(2025, 3, 1),
    )
    assert end == date(2025, 3, 20)


def test_parse_until():
    end = parse_event_end_date(
        "期間限定ショップ〜4月30日まで",
        reference=date(2025, 4, 1),
    )
    assert end == date(2025, 4, 30)


def test_no_date_returns_none():
    assert parse_event_end_date("新作グッズ入荷のお知らせ") is None


def test_expired_after_end_date():
    assert is_event_expired("2025-03-15", reference=date(2025, 3, 16)) is True
    assert is_event_expired("2025-03-15", reference=date(2025, 3, 15)) is False


def test_parse_kaisai_period_with_weekday():
    text = "開催期間：2026年5月19日(火)～5月31日(日)"
    end = parse_event_end_date(text, reference=date(2026, 7, 8))
    assert end == date(2026, 5, 31)
    assert is_event_expired(format_end_date(end), reference=date(2026, 7, 8)) is True


def test_resolve_prefers_title():
    assert (
        resolve_event_expiry(
            "POP UP 2025年5月1日〜5月10日",
            "補足テキスト",
        )
        == "2025-05-10"
    )
