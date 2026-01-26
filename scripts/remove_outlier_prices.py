#!/usr/bin/env python3
"""
価格履歴から外れ値（異常に安い/高い価格）を検出・削除するスクリプト。

IQR（四分位範囲）法を用いて統計的な外れ値を検出します。

Usage:
  remove_outlier_prices.py [-c CONFIG] [-m MIN_RECORDS] [--dry-run] [-D]

Options:
  -c CONFIG         : CONFIG を設定ファイルとして読み込んで実行します。
                      [default: config.yaml]
  -m MIN_RECORDS    : 外れ値検出に必要な最小レコード数。
                      [default: 100]
  --dry-run         : 削除を実行せず、検出結果のみ表示します。
  -D                : デバッグモードで動作します。
"""

from __future__ import annotations

import logging
import pathlib
import sqlite3
import statistics
from dataclasses import dataclass


@dataclass(frozen=True)
class OutlierRecord:
    """外れ値レコード."""

    history_id: int
    item_id: int
    item_name: str
    store: str
    price: int
    time: str
    outlier_type: str  # "low" or "high"
    q1: float
    q3: float
    iqr: float
    lower_bound: float
    upper_bound: float


@dataclass(frozen=True)
class ItemStats:
    """アイテム統計情報."""

    item_id: int
    name: str
    store: str
    record_count: int
    q1: float
    q3: float
    iqr: float
    lower_bound: float
    upper_bound: float
    prices: list[int]


def dict_factory(cursor: sqlite3.Cursor, row: tuple) -> dict:
    """SQLite 結果を辞書に変換."""
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d


def get_items_with_sufficient_records(conn: sqlite3.Connection, min_records: int) -> list[dict]:
    """十分な価格記録があるアイテムを取得.

    Args:
        conn: データベース接続
        min_records: 最小レコード数

    Returns:
        アイテムリスト
    """
    cur = conn.cursor()
    cur.execute(
        """
        SELECT
            i.id as item_id,
            i.name,
            i.store,
            COUNT(ph.id) as record_count
        FROM items i
        JOIN price_history ph ON i.id = ph.item_id
        WHERE ph.stock = 1
          AND ph.price IS NOT NULL
          AND ph.crawl_status = 1
        GROUP BY i.id, i.name, i.store
        HAVING COUNT(ph.id) >= ?
        ORDER BY i.name, i.store
        """,
        (min_records,),
    )
    return cur.fetchall()


def get_price_records(conn: sqlite3.Connection, item_id: int) -> list[dict]:
    """アイテムの価格履歴を取得.

    Args:
        conn: データベース接続
        item_id: アイテム ID

    Returns:
        価格履歴リスト
    """
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, price, time
        FROM price_history
        WHERE item_id = ?
          AND stock = 1
          AND price IS NOT NULL
          AND crawl_status = 1
        ORDER BY time ASC
        """,
        (item_id,),
    )
    return cur.fetchall()


def calculate_iqr_bounds(
    prices: list[int], low_multiplier: float = 1.5, high_multiplier: float = 3.0
) -> tuple[float, float, float, float, float]:
    """IQR 法で境界値を計算.

    Args:
        prices: 価格リスト
        low_multiplier: 下限の IQR 係数（デフォルト 1.5）
        high_multiplier: 上限の IQR 係数（デフォルト 3.0、厳しめ）

    Returns:
        (Q1, Q3, IQR, 下限, 上限)
    """
    sorted_prices = sorted(prices)

    # 四分位数を計算
    q1 = statistics.quantiles(sorted_prices, n=4)[0]  # 25%
    q3 = statistics.quantiles(sorted_prices, n=4)[2]  # 75%
    iqr = q3 - q1

    lower_bound = q1 - low_multiplier * iqr
    upper_bound = q3 + high_multiplier * iqr

    return q1, q3, iqr, lower_bound, upper_bound


def find_outliers(
    conn: sqlite3.Connection, item: dict, low_multiplier: float = 1.5, high_multiplier: float = 3.0
) -> list[OutlierRecord]:
    """アイテムの外れ値を検出.

    Args:
        conn: データベース接続
        item: アイテム情報
        low_multiplier: 下限の IQR 係数
        high_multiplier: 上限の IQR 係数

    Returns:
        外れ値レコードのリスト
    """
    records = get_price_records(conn, item["item_id"])
    prices = [r["price"] for r in records]

    if len(prices) < 4:  # 四分位数計算には最低 4 件必要
        return []

    q1, q3, iqr, lower_bound, upper_bound = calculate_iqr_bounds(prices, low_multiplier, high_multiplier)

    outliers = []
    for record in records:
        price = record["price"]
        outlier_type = None

        if price < lower_bound:
            outlier_type = "low"
        elif price > upper_bound:
            outlier_type = "high"

        if outlier_type:
            outliers.append(
                OutlierRecord(
                    history_id=record["id"],
                    item_id=item["item_id"],
                    item_name=item["name"],
                    store=item["store"],
                    price=price,
                    time=record["time"],
                    outlier_type=outlier_type,
                    q1=q1,
                    q3=q3,
                    iqr=iqr,
                    lower_bound=lower_bound,
                    upper_bound=upper_bound,
                )
            )

    return outliers


def format_price(price: int | float) -> str:
    """価格をフォーマット."""
    return f"¥{int(price):,}"


def print_outlier_info(outlier: OutlierRecord, prices: list[int]) -> None:
    """外れ値情報を表示."""
    median = statistics.median(prices)
    mean = statistics.mean(prices)
    min_price = min(prices)
    max_price = max(prices)

    type_label = "安すぎ" if outlier.outlier_type == "low" else "高すぎ"

    print(f"\n{'=' * 60}")
    print(f"アイテム: {outlier.item_name}")
    print(f"ストア: {outlier.store}")
    print(f"日時: {outlier.time}")
    print(f"価格: {format_price(outlier.price)} ({type_label})")
    print("-" * 60)
    print("統計情報:")
    print(f"  記録数: {len(prices)}")
    print(f"  最小値: {format_price(min_price)}")
    print(f"  Q1 (25%): {format_price(outlier.q1)}")
    print(f"  中央値: {format_price(median)}")
    print(f"  平均値: {format_price(mean)}")
    print(f"  Q3 (75%): {format_price(outlier.q3)}")
    print(f"  最大値: {format_price(max_price)}")
    print(f"  IQR: {format_price(outlier.iqr)}")
    print("-" * 60)
    print("判定基準:")
    print(f"  下限: {format_price(outlier.lower_bound)} (Q1 - 1.5*IQR)")
    print(f"  上限: {format_price(outlier.upper_bound)} (Q3 + 3.0*IQR)")


def ask_confirmation(prompt: str) -> bool:
    """確認を求める."""
    while True:
        response = input(f"{prompt} [y/N]: ").strip().lower()
        if response in ("", "n", "no"):
            return False
        if response in ("y", "yes"):
            return True
        print("y または N を入力してください。")


def delete_records(conn: sqlite3.Connection, history_ids: list[int]) -> int:
    """レコードを削除.

    Args:
        conn: データベース接続
        history_ids: 削除する履歴 ID のリスト

    Returns:
        削除したレコード数
    """
    if not history_ids:
        return 0

    cur = conn.cursor()
    placeholders = ",".join("?" * len(history_ids))
    cur.execute(
        f"DELETE FROM price_history WHERE id IN ({placeholders})",  # noqa: S608
        history_ids,
    )
    conn.commit()
    return cur.rowcount


def main(config_file: pathlib.Path, min_records: int, dry_run: bool) -> None:
    """メイン処理."""
    import price_watch.config
    import price_watch.const

    # 設定を読み込む
    config = price_watch.config.load(config_file)
    db_path = config.data.price / price_watch.const.DB_FILE

    if not db_path.exists():
        logging.error("データベースファイルが見つかりません: %s", db_path)
        raise SystemExit(1)

    logging.info("データベース: %s", db_path)
    logging.info("最小レコード数: %d", min_records)
    if dry_run:
        logging.info("ドライランモード: 削除は実行しません")

    # 削除対象のリスト
    records_to_delete: list[OutlierRecord] = []

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = dict_factory  # type: ignore[assignment]

        # 十分な記録があるアイテムを取得
        items = get_items_with_sufficient_records(conn, min_records)
        logging.info("対象アイテム数: %d", len(items))

        if not items:
            logging.info("外れ値検出の対象となるアイテムがありません。")
            return

        # 各アイテムの外れ値を検出
        for item in items:
            outliers = find_outliers(conn, item)

            if not outliers:
                continue

            # このアイテムの価格リストを取得
            records = get_price_records(conn, item["item_id"])
            prices = [r["price"] for r in records]

            logging.info(
                "アイテム '%s' (%s): %d 件の外れ値を検出",
                item["name"],
                item["store"],
                len(outliers),
            )

            for outlier in outliers:
                print_outlier_info(outlier, prices)

                if dry_run:
                    print("\n[ドライラン] このレコードは削除候補です")
                    records_to_delete.append(outlier)
                elif ask_confirmation("このレコードを削除しますか?"):
                    records_to_delete.append(outlier)
                    logging.info("削除対象に追加: ID=%d", outlier.history_id)
                else:
                    logging.info("スキップ: ID=%d", outlier.history_id)

        # 最終確認と削除
        if records_to_delete:
            print(f"\n{'=' * 60}")
            print("削除対象レコード一覧:")
            print(f"{'=' * 60}")

            for i, record in enumerate(records_to_delete, 1):
                type_label = "安" if record.outlier_type == "low" else "高"
                print(
                    f"{i:3d}. [{type_label}] {record.item_name} ({record.store}): "
                    f"{format_price(record.price)} @ {record.time}"
                )

            print(f"\n合計: {len(records_to_delete)} 件")

            if dry_run:
                print("\n[ドライラン] 削除は実行されません")
            elif ask_confirmation("\nこれらのレコードを削除しますか?"):
                history_ids = [r.history_id for r in records_to_delete]
                deleted = delete_records(conn, history_ids)
                logging.info("削除完了: %d 件", deleted)
            else:
                logging.info("削除をキャンセルしました")
        else:
            logging.info("削除対象のレコードはありません")


if __name__ == "__main__":
    import docopt
    import my_lib.logger

    assert __doc__ is not None  # noqa: S101
    args = docopt.docopt(__doc__)

    config_file = pathlib.Path(args["-c"])
    min_records = int(args["-m"])
    dry_run = args["--dry-run"]
    debug_mode = args["-D"]

    my_lib.logger.init("remove-outlier-prices", level=logging.DEBUG if debug_mode else logging.INFO)

    main(config_file, min_records, dry_run)
