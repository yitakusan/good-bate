# -*- coding: utf-8 -*-
"""Shadow-DB smoke: product kind JP keyword detection + override."""
from __future__ import annotations

import os
import sys

os.environ["STOCKGOOD_DB_MODE"] = "shadow"
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.database import get_conn, get_db_path, init_db
from app.models import ItemUpdate, LineCreate, OrderCreate
from app.product_kind import ProductKindNormalizer
from app.services import items as items_svc
from app.services import orders as orders_svc
from app.settings import get_settings


CASES = [
    ("【予約】キャラクター缶バッジ", "吧唧"),
    ("缶ﾊﾞｯｼﾞ 半角片仮名", "吧唧"),
    ("アクリルスタンド 描き下ろし", "立牌"),
    ("ｱｸｽﾀ 半角", "立牌"),
    ("A3ポスター", "海报"),
    ("トレーディングカード セット", "小卡"),
    ("ﾄﾚｶ", "小卡"),
    ("キーホルダー", "钥匙扣"),
    ("アクリルキーホルダー", "钥匙扣"),
    ("クリアファイル", "文件袋"),
    ("ぬいぐるみマスコット", "玩偶"),
    ("ぬいぐるみ", "玩偶"),
    ("ステッカーシート", "贴纸"),
    ("チェキ風ブロマイド", "小卡"),
    ("チェキ", "拍立得"),
    ("无关品名 XYZ", ""),
]


def main() -> None:
    print("DB:", get_db_path())
    assert "shadow" in str(get_db_path()), "must use shadow DB"
    init_db()

    detector = ProductKindNormalizer(get_settings().product_kind_path)
    for name, expect in CASES:
        got = detector.detect(name)
        print(f"detect {got} == {expect}? {got == expect}")
        assert got == expect, (name, got, expect)

    with get_conn() as conn:
        refs = conn.execute(
            "SELECT id FROM orders WHERE order_ref LIKE 'KIND-SMOKE%'"
        ).fetchall()
        for row in refs:
            conn.execute("DELETE FROM orders WHERE id = ?", (row["id"],))

    order = orders_svc.create_order(
        OrderCreate(
            order_ref="KIND-SMOKE-JP",
            shop="kind-test",
            lines=[
                LineCreate(name=name, qty=1, barcode=f"KJ{i}")
                for i, (name, _) in enumerate(CASES, start=1)
            ],
        )
    )
    for line, (name, expect) in zip(order["lines"], CASES):
        assert line["product_kind"] == expect, (name, line["product_kind"], expect)

    target = order["lines"][0]
    updated = items_svc.update_item(
        target["id"], ItemUpdate(product_kind="立牌")
    )
    assert updated["product_kind"] == "立牌"
    print("dropdown override ok")

    labels = detector.known_kinds()
    assert "吧唧" in labels and "贴纸" in labels
    print("labels count:", len(labels))
    print("OK")


if __name__ == "__main__":
    main()
