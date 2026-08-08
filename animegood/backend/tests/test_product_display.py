from pathlib import Path

from app.product_display import apply_glossary, load_name_glossary, resolve_display_name_zh


def test_glossary_replace(tmp_path: Path):
    glossary_file = tmp_path / "glossary.json"
    glossary_file.write_text('{"缶バッジ": "徽章", "アクリルスタンド": "亚克力立牌"}', encoding="utf-8")
    glossary = load_name_glossary(glossary_file)
    assert apply_glossary("缶バッジセット", glossary) == "徽章セット"


def test_resolve_returns_none_when_no_match(tmp_path: Path):
    glossary_file = tmp_path / "glossary.json"
    glossary_file.write_text('{"缶バッジ": "徽章"}', encoding="utf-8")
    assert resolve_display_name_zh("新作グッズ", glossary_path=glossary_file) is None


def test_resolve_uses_glossary(tmp_path: Path):
    glossary_file = tmp_path / "glossary.json"
    glossary_file.write_text('{"缶バッジ": "徽章"}', encoding="utf-8")
    assert resolve_display_name_zh("缶バッジセット", glossary_path=glossary_file) == "徽章セット"
