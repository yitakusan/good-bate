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

    def normalize(self, product_name: str) -> str:
        lowered = product_name.lower()
        for standard_ip, aliases in self.aliases.items():
            candidates = [standard_ip, *aliases]
            if any(candidate.lower() in lowered for candidate in candidates):
                return standard_ip
        return "未分类"
