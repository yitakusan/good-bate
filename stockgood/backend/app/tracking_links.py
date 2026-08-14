from __future__ import annotations

from typing import Literal, Optional
from urllib.parse import quote

# ============================================================
# SHARED MODULE
#
# [用途] Yamato / 佐川官方查询 URL
# [使用功能] FEATURE: INBOUND / OUTBOUND_BATCH
# ============================================================

Carrier = Literal["yamato", "sagawa", "other"]


def tracking_url(carrier: str, tracking_no: str) -> Optional[str]:
    """Return an official carrier lookup URL, when one is available."""
    number = quote(tracking_no.strip(), safe="")
    if not number:
        return None
    if carrier == "yamato":
        return (
            "https://jizen.kuronekoyamato.co.jp/jizen/servlet/"
            f"crjz.b.NQ0010?id={number}"
        )
    if carrier == "sagawa":
        return (
            "https://k2k.sagawa-exp.co.jp/p/web/okurijosearch.do?"
            f"okurijoNo={number}"
        )
    return None
