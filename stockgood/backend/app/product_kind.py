from __future__ import annotations

import json
import unicodedata
from pathlib import Path


# 标准种类 → 别名。抓取品名多为日语，别名以日文为主（含常见简写 / 半角片假名经 NFKC 归一）。
DEFAULT_KINDS: dict[str, list[str]] = {
    "吧唧": [
        "吧唧",
        "缶バッジ",
        "缶バッチ",
        "缶ﾊﾞｯｼﾞ",
        "カンバッジ",
        "ピンバッジ",
        "ピンズ",
        "ブラインド缶バッジ",
        "バッジ",
        "バッヂ",
        "can badge",
        "canbadge",
    ],
    "立牌": [
        "立牌",
        "アクリルスタンド",
        "アクリルｽﾀﾝﾄﾞ",
        "アクスタ",
        "ｱｸｽﾀ",
        "アクリルフィギュアスタンド",
        "acrylic stand",
        "acrylicstand",
        "standee",
    ],
    "海报": [
        "海报",
        "海報",
        "ポスター",
        "ﾎﾟｽﾀｰ",
        "B2ポスター",
        "B3ポスター",
        "ポスターコレクション",
        "poster",
    ],
    "小卡": [
        "小卡",
        "トレカ",
        "ﾄﾚｶ",
        "トレーディングカード",
        "トレーディングｶｰﾄﾞ",
        "ブロマイド",
        "ﾌﾞﾛﾏｲﾄﾞ",
        "キャラクターカード",
        "trading card",
        "photocard",
        "photo card",
    ],
    "色纸": [
        "色纸",
        "色紙",
        "ミニ色紙",
        "複製色紙",
        "サイン色紙",
        "shikishi",
    ],
    "钥匙扣": [
        "钥匙扣",
        "鑰匙扣",
        "キーホルダー",
        "ｷｰﾎﾙﾀﾞｰ",
        "キーチェーン",
        "アクリルキーホルダー",
        "アクキー",
        "ｱｸｷｰ",
        "ラバーストラップ",
        "ラバスト",
        "メタルキーホルダー",
        "keychain",
        "key holder",
    ],
    "透卡": [
        "透卡",
        "クリアカード",
        "クリアブロマイド",
        "クリアｶｰﾄﾞ",
        "clear card",
    ],
    "挂件": [
        "挂件",
        "掛件",
        "ぬいぐるみ",
        "ぬい",
        "マスコット",
        "ﾌﾟﾗｯｼｭ",
        "plush",
        "マスコットホルダー",
    ],
    "文件袋": [
        "文件袋",
        "クリアファイル",
        "ｸﾘｱﾌｧｲﾙ",
        "クリアフォルダ",
        "クリアフォルダー",
        "clear file",
    ],
    "明信片": [
        "明信片",
        "ポストカード",
        "ﾎﾟｽﾄｶｰﾄﾞ",
        "postcard",
        "post card",
    ],
    "亚克力砖": [
        "亚克力砖",
        "壓克力磚",
        "アクリルブロック",
        "アクリルプレート",
        "アクリル砖",
        "acrylic block",
    ],
    "票根": [
        "票根",
        "チケット",
        "ﾁｹｯﾄ",
        "半券",
        "入場チケット",
        "ticket stub",
    ],
    "拍立得": [
        "拍立得",
        "チェキ",
        "ﾁｪｷ",
        "チェキ風",
        "instax",
        "polaroid",
    ],
    "贴纸": [
        "贴纸",
        "貼紙",
        "ステッカー",
        "ｽﾃｯｶｰ",
        "シール",
        "sticker",
    ],
}


def ensure_kind_file(path: Path) -> None:
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(DEFAULT_KINDS, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _merge_defaults(raw: dict[str, list[str]]) -> dict[str, list[str]]:
    """Keep user kinds/aliases; union in built-in JP/CN aliases for upgrades."""
    merged: dict[str, list[str]] = {
        str(kind): [str(a) for a in aliases] for kind, aliases in raw.items()
    }
    for kind, aliases in DEFAULT_KINDS.items():
        existing = merged.setdefault(kind, [])
        seen = {a.casefold() for a in existing}
        for alias in aliases:
            if alias.casefold() not in seen:
                existing.append(alias)
                seen.add(alias.casefold())
    return merged


class ProductKindNormalizer:
    """Match product name keywords → standard kind label (longest hit wins)."""

    def __init__(self, kind_path: Path):
        ensure_kind_file(kind_path)
        self.kind_path = kind_path
        self.kinds = self._load_kinds()

    def _load_kinds(self) -> dict[str, list[str]]:
        raw = json.loads(self.kind_path.read_text(encoding="utf-8"))
        parsed = {
            str(kind): [str(alias) for alias in aliases]
            for kind, aliases in raw.items()
        }
        return _merge_defaults(parsed)

    def reload(self) -> None:
        self.kinds = self._load_kinds()

    def known_kinds(self) -> list[str]:
        # Stable order: DEFAULT order first, then any extra user kinds
        ordered = [k for k in DEFAULT_KINDS if k in self.kinds]
        extra = sorted(k for k in self.kinds if k not in DEFAULT_KINDS)
        return ordered + extra

    @staticmethod
    def _fold(text: str) -> str:
        """NFKC folds half-width katakana / fullwidth alnum; lowercase."""
        folded = unicodedata.normalize("NFKC", text or "").lower()
        return (
            folded.replace("×", "x")
            .replace("&times;", "x")
            .replace("&#215;", "x")
        )

    def detect(self, product_name: str) -> str:
        lowered = self._fold(product_name or "")
        best_kind = ""
        best_len = 0
        for standard_kind, aliases in self.kinds.items():
            candidates = [standard_kind, *aliases]
            for candidate in candidates:
                token = self._fold(candidate).strip()
                if len(token) < 2:
                    continue
                if token in lowered and len(token) > best_len:
                    best_kind = standard_kind
                    best_len = len(token)
        return best_kind
