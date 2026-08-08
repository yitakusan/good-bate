from __future__ import annotations

import re

# 收尾常见商品形态，去掉后剩余前缀更像「系列」
_PRODUCT_TYPE_SUFFIXES = (
    "トレーディングホロ缶バッジ",
    "カラーアクリルキーホルダー",
    "アクリルキーホルダー",
    "アクリルスタンド",
    "ランダムブロマイド",
    "クリアファイル",
    "ぬいぐるみ",
    "缶バッジ",
    "マスコット",
    "ステッカー",
    "タペストリー",
    "Tシャツ",
    "タオル",
    "フィギュア",
    "ポスター",
    "キーホルダー",
    "ブローチ",
    "グラス",
    "セット",
)

_SKIP_BRACKETS = (
    "予約",
    "特典",
    "受取",
    "事後",
    "発売",
    "通販",
    "BOX",
    "ランダム",
    "限定",
)

_RE_SERIES_WORD = re.compile(r"(.+?)\s*シリーズ")
_RE_QUOTED = re.compile(r"[『「]([^』」]{2,60})[』」]")
_RE_BRACKET = re.compile(r"【([^】]{2,40})】")
_RE_SKU_TAIL = re.compile(r"[《〈].*?[》〉]\s*$")
_RE_PAREN_CHAR = re.compile(r"[（(][^）)]{1,20}[）)]\s*$")
_RE_OSHI_SET = re.compile(r"選べる推し！.+$")
_RE_SPACES = re.compile(r"\s+")


def _clean(value: str) -> str:
    return _RE_SPACES.sub(" ", value).strip(" 　/-｜|")


def _is_skipped_bracket(text: str) -> bool:
    return any(token in text for token in _SKIP_BRACKETS)


def extract_series(product_name: str) -> str | None:
    """从商品名推断系列/企划名；推断不出则返回 None。"""
    name = _clean(product_name or "")
    if len(name) < 4:
        return None

    series_word = _RE_SERIES_WORD.search(name)
    if series_word:
        candidate = _clean(series_word.group(1))
        # 只要尾部一段，避免整句过长
        parts = re.split(r"[\/｜|]", candidate)
        candidate = _clean(parts[-1])
        if 2 <= len(candidate) <= 40:
            return candidate

    quoted = _RE_QUOTED.findall(name)
    if quoted:
        # 优先较长的书名号内容（多为作品/系列名）
        candidate = max((_clean(item) for item in quoted), key=len)
        if 2 <= len(candidate) <= 50:
            return candidate

    for match in _RE_BRACKET.finditer(name):
        candidate = _clean(match.group(1))
        if _is_skipped_bracket(candidate):
            continue
        if 2 <= len(candidate) <= 40:
            return candidate

    stripped = name
    stripped = _RE_SKU_TAIL.sub("", stripped)
    stripped = _RE_OSHI_SET.sub("", stripped)
    stripped = _RE_PAREN_CHAR.sub("", stripped)
    for suffix in _PRODUCT_TYPE_SUFFIXES:
        if stripped.endswith(suffix):
            stripped = stripped[: -len(suffix)]
            break
    stripped = _clean(stripped)

    # 「第N回○○フェス」类活动前缀
    fest = re.match(r"(第?\d*回?.{0,20}(?:フェス|祭|クリスマス|ハロウィン|バレンタイン|周年).{0,20})", stripped)
    if fest:
        candidate = _clean(fest.group(1))
        if 4 <= len(candidate) <= 40:
            return candidate

    # 去掉收尾后仍足够长，取前缀作为弱系列键（同店内检索用）
    if len(stripped) >= 12:
        # 在空格/全角空格处截到合适长度
        if len(stripped) > 36:
            cut = stripped[:36]
            for sep in ("　", " ", "／", "/"):
                idx = cut.rfind(sep)
                if idx >= 10:
                    cut = cut[:idx]
                    break
            stripped = _clean(cut)
        if 8 <= len(stripped) <= 40:
            return stripped

    return None
