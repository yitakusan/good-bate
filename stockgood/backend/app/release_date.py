from __future__ import annotations

from typing import Optional

PERIOD_MAP = {
    "上旬": "early",
    "中旬": "mid",
    "下旬": "late",
    "early": "early",
    "mid": "mid",
    "late": "late",
}


def map_release_to_expected_ship(
    release_date: Optional[str],
) -> tuple[Optional[str], Optional[str]]:
    """
    Map animegood-style release strings to stockgood fields.

    Examples:
      2026-07-上旬 → ("2026-07", "early")
      2026-07-15   → ("2026-07", None)
      2026-07      → ("2026-07", None)
    """
    if not release_date:
        return None, None
    text = release_date.strip()
    if not text:
        return None, None

    # YYYY-MM-上旬 / YYYY-MM-中旬 / YYYY-MM-下旬
    for jp, code in (("上旬", "early"), ("中旬", "mid"), ("下旬", "late")):
        if text.endswith(f"-{jp}") or text.endswith(jp):
            month_part = text[:7] if len(text) >= 7 and text[4] == "-" else None
            if month_part and len(month_part) == 7:
                return month_part, code

    # YYYY-MM-DD
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        return text[:7], None

    # YYYY-MM
    if len(text) >= 7 and text[4] == "-":
        return text[:7], None

    return None, None
