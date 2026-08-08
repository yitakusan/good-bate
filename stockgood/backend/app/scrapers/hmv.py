"""HMV.co.jp access-wall detection helpers."""

from __future__ import annotations

import re
from urllib.parse import urlparse


def is_hmv_url(url: str) -> bool:
    host = urlparse(url).netloc.lower().split(":", 1)[0]
    return host == "hmv.co.jp" or host.endswith(".hmv.co.jp")


def is_hmv_empty_shell(html: str) -> bool:
    """Return whether NetFunnel served an empty page rather than product HTML."""
    lowered = (html or "").lower()
    if "netfunnel" not in lowered and "agent-lib.stclab.com" not in lowered:
        return False

    title = re.search(r"<title[^>]*>\s*(.*?)\s*</title>", html, re.I | re.S)
    og_title = ""
    for tag in re.findall(r"<meta\b[^>]*>", html, re.I):
        if "og:title" not in tag.lower():
            continue
        content = re.search(r"content=[\"']([^\"']*)", tag, re.I)
        og_title = content.group(1).strip() if content else ""
        break
    return not (title and title.group(1).strip()) and not (
        og_title
    )
