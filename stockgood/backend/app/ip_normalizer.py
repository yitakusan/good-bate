from __future__ import annotations

import json
from pathlib import Path


DEFAULT_ALIASES: dict[str, list[str]] = {
    "女神异闻录": ["女神異聞録", "persona", "p3", "p4", "p5", "p30th", "p5x"],
    "明日方舟": ["arknights", "アークナイツ", "明日方舟"],
    "初音未来": ["初音", "ミク", "miku", "vocaloid", "重音", "巡音", "鏡音"],
}


def ensure_alias_file(path: Path) -> None:
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(DEFAULT_ALIASES, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


class IpNormalizer:
    def __init__(self, alias_path: Path):
        ensure_alias_file(alias_path)
        self.alias_path = alias_path
        self.aliases = self._load_aliases()

    def _load_aliases(self) -> dict[str, list[str]]:
        raw = json.loads(self.alias_path.read_text(encoding="utf-8"))
        return {str(ip): [str(alias) for alias in aliases] for ip, aliases in raw.items()}

    @staticmethod
    def _fold(text: str) -> str:
        """Lowercase + fold fullwidth alphanumerics / common separators."""
        out: list[str] = []
        for ch in text:
            code = ord(ch)
            if 0xFF01 <= code <= 0xFF5E:
                ch = chr(code - 0xFEE0)
            out.append(ch)
        folded = "".join(out).lower()
        return (
            folded.replace("×", "x")
            .replace("ｘ", "x")
            .replace("&times;", "x")
            .replace("&#215;", "x")
        )

    def normalize(self, product_name: str) -> str:
        lowered = self._fold(product_name)
        # Prefer longer alias hits to avoid short false positives (e.g. old "p5").
        best_ip = ""
        best_len = 0
        for standard_ip, aliases in self.aliases.items():
            candidates = [standard_ip, *aliases]
            for candidate in candidates:
                token = self._fold(candidate).strip()
                if len(token) < 2:
                    continue
                if token in lowered and len(token) > best_len:
                    best_ip = standard_ip
                    best_len = len(token)
        return best_ip
