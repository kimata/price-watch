#!/usr/bin/env python3
"""
価格履歴を遡り、記録されていないイベント（最安値更新・価格下落）を補完するスクリプト。

過去のバグにより記録されなかったイベントを、価格履歴データから再現して
events テーブルに挿入します。

イベント判定ロジックは本番 (event.py) と同等です:
- LOWEST_PRICE: 過去全期間の最安値を更新した場合
- PRICE_DROP: 指定期間内の最安値から一定以上下落した場合

Usage:
  backfill_events.py [-c CONFIG] [--dry-run] [-D]

Options:
  -c CONFIG         : CONFIG を設定ファイルとして読み込んで実行します。
                      [default: config.yaml]
  --dry-run         : DB に書き込まず、検出結果のみ表示します。
  -D                : デバッグモードで動作します。
"""

from __future__ import annotations

import logging
import pathlib
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import price_watch.config
import price_watch.const
from price_watch.event import EventType


def dict_factory(cursor: sqlite3.Cursor, row: tuple) -> dict:
    """SQLite 結果を辞書に変換."""
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d


@dataclass(frozen=True)
class BackfillEvent:
    """補完対象イベント."""

    item_id: int
    item_name: str
    store: str
    event_type: str
    price: int
    old_price: int
    threshold_days: int | None
    record_time: str


@dataclass
class BackfillStats:
    """補完統計."""

    items_scanned: int = 0
    lowest_price_found: int = 0
    price_drop_found: int = 0
    already_recorded: int = 0
    inserted: int = 0


@dataclass
class BackfillContext:
    """補完処理コンテキスト."""

    conn: sqlite3.Connection
    ignore_hours: int
    windows: list[price_watch.config.PriceDropWindow] = field(default_factory=list)
    dry_run: bool = False
    stats: BackfillStats = field(default_factory=BackfillStats)


def get_all_items(conn: sqlite3.Connection) -> list[dict]:
    """全アイテムを取得."""
    cur = conn.cursor()
    cur.execute("SELECT id, name, store FROM items ORDER BY name, store")
    return cur.fetchall()


def get_price_history_asc(conn: sqlite3.Connection, item_id: int) -> list[dict]:
    """アイテムの価格履歴を古い順に取得.

    本番ロジックと同じ条件: crawl_status=1, price IS NOT NULL, stock=1
    """
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, price, stock, time
        FROM price_history
        WHERE item_id = ?
          AND crawl_status = 1
          AND price IS NOT NULL
          AND stock = 1
        ORDER BY time ASC
        """,
        (item_id,),
    )
    return cur.fetchall()


def get_existing_events(conn: sqlite3.Connection, item_id: int) -> list[dict]:
    """アイテムの既存イベントを取得."""
    cur = conn.cursor()
    cur.execute(
        """
        SELECT event_type, price, old_price, threshold_days, created_at
        FROM events
        WHERE item_id = ?
        ORDER BY created_at ASC
        """,
        (item_id,),
    )
    return cur.fetchall()


def has_event_near(
    existing_events: list[dict],
    event_type: str,
    record_time: str,
    ignore_hours: int,
) -> bool:
    """指定時刻の前後 ignore_hours 以内に同じタイプのイベントが存在するか判定.

    本番では「現在時刻から ignore_hours 以内」で判定するが、
    バックフィルでは「レコード時刻の前後 ignore_hours 以内」で判定する。
    """
    record_dt = datetime.fromisoformat(record_time)
    window_start = record_dt - timedelta(hours=ignore_hours)
    window_end = record_dt + timedelta(hours=ignore_hours)

    for ev in existing_events:
        if ev["event_type"] != event_type:
            continue
        ev_dt = datetime.fromisoformat(ev["created_at"])
        if window_start <= ev_dt <= window_end:
            return True
    return False


def get_lowest_in_period_before(
    conn: sqlite3.Connection,
    item_id: int,
    before_time: str,
    days: int,
) -> int | None:
    """指定時刻より前の指定日数間における最安値を取得.

    PRICE_DROP 判定で使用。本番の get_lowest_in_period と同等だが、
    「現在時刻」の代わりに「レコード時刻」を基準にする。
    """
    cur = conn.cursor()
    before_dt = datetime.fromisoformat(before_time)
    window_start = before_dt - timedelta(days=days)
    window_start_str = window_start.strftime("%Y-%m-%d %H:%M:%S")

    cur.execute(
        """
        SELECT MIN(price)
        FROM price_history
        WHERE item_id = ?
          AND time >= ?
          AND time < ?
          AND price IS NOT NULL
          AND crawl_status = 1
          AND stock = 1
        """,
        (item_id, window_start_str, before_time),
    )
    row = cur.fetchone()
    if row:
        values = list(row.values())
        return values[0] if values and values[0] is not None else None
    return None


def check_lowest_price_backfill(
    ctx: BackfillContext,
    item_id: int,
    current_price: int,
    running_min: int,
    record_time: str,
    existing_events: list[dict],
) -> bool:
    """最安値更新イベントを判定（本番 event.check_lowest_price と同等ロジック）.

    Returns:
        イベントを検出した場合 True
    """
    # 本番ロジック: current_price >= lowest_price → スキップ
    if current_price >= running_min:
        return False

    # 近辺に既存イベントがあるかチェック
    if has_event_near(existing_events, EventType.LOWEST_PRICE.value, record_time, ctx.ignore_hours):
        ctx.stats.already_recorded += 1
        return False

    return True


def check_price_drop_backfill(
    ctx: BackfillContext,
    item_id: int,
    current_price: int,
    record_time: str,
    existing_events: list[dict],
) -> BackfillEvent | None:
    """価格下落イベントを判定（本番 event.check_price_drop と同等ロジック）.

    Args:
        ctx: 補完処理コンテキスト
        item_id: アイテム ID
        current_price: 現在の価格
        record_time: レコードの時刻
        existing_events: 既存イベントのリスト

    Returns:
        検出したイベント、または None
    """
    for window in ctx.windows:
        lowest_in_period = get_lowest_in_period_before(ctx.conn, item_id, record_time, window.days)

        if lowest_in_period is None:
            continue

        drop_amount = lowest_in_period - current_price
        if drop_amount <= 0:
            continue

        should_fire = False

        if window.rate is not None:
            drop_rate = (drop_amount / lowest_in_period) * 100
            if drop_rate >= window.rate:
                should_fire = True

        if window.value is not None and drop_amount >= window.value:
            should_fire = True

        if not should_fire:
            continue

        # 近辺に既存イベントがあるかチェック
        if has_event_near(existing_events, EventType.PRICE_DROP.value, record_time, ctx.ignore_hours):
            ctx.stats.already_recorded += 1
            return None

        # 最初にマッチした window で返す（本番と同じ: 最初の match で return）
        return BackfillEvent(
            item_id=item_id,
            item_name="",  # 呼び出し側で設定
            store="",
            event_type=EventType.PRICE_DROP.value,
            price=current_price,
            old_price=lowest_in_period,
            threshold_days=window.days,
            record_time=record_time,
        )

    return None


def process_item(
    ctx: BackfillContext,
    item: dict,
) -> list[BackfillEvent]:
    """アイテムの価格履歴をスキャンしてイベントを検出."""
    item_id = item["id"]
    item_name = item["name"]
    store = item["store"]

    records = get_price_history_asc(ctx.conn, item_id)
    if len(records) < 2:
        return []

    existing_events = get_existing_events(ctx.conn, item_id)
    events_to_insert: list[BackfillEvent] = []

    running_min: int | None = None

    for record in records:
        current_price = record["price"]
        record_time = record["time"]

        if running_min is None:
            # 最初のレコード: 最安値を初期化（本番でも初回はイベント発生させない）
            running_min = current_price
            continue

        # LOWEST_PRICE チェック
        if check_lowest_price_backfill(
            ctx, item_id, current_price, running_min, record_time, existing_events
        ):
            ev = BackfillEvent(
                item_id=item_id,
                item_name=item_name,
                store=store,
                event_type=EventType.LOWEST_PRICE.value,
                price=current_price,
                old_price=running_min,
                threshold_days=None,
                record_time=record_time,
            )
            events_to_insert.append(ev)
            # 挿入予定のイベントも既存とみなす（重複防止）
            existing_events.append(
                {
                    "event_type": EventType.LOWEST_PRICE.value,
                    "price": current_price,
                    "old_price": running_min,
                    "threshold_days": None,
                    "created_at": record_time,
                }
            )
            ctx.stats.lowest_price_found += 1

        # PRICE_DROP チェック
        if ctx.windows:
            drop_event = check_price_drop_backfill(ctx, item_id, current_price, record_time, existing_events)
            if drop_event is not None:
                drop_event = BackfillEvent(
                    item_id=drop_event.item_id,
                    item_name=item_name,
                    store=store,
                    event_type=drop_event.event_type,
                    price=drop_event.price,
                    old_price=drop_event.old_price,
                    threshold_days=drop_event.threshold_days,
                    record_time=drop_event.record_time,
                )
                events_to_insert.append(drop_event)
                existing_events.append(
                    {
                        "event_type": EventType.PRICE_DROP.value,
                        "price": drop_event.price,
                        "old_price": drop_event.old_price,
                        "threshold_days": drop_event.threshold_days,
                        "created_at": drop_event.record_time,
                    }
                )
                ctx.stats.price_drop_found += 1

        # running_min を更新
        if current_price < running_min:
            running_min = current_price

    return events_to_insert


def insert_events(conn: sqlite3.Connection, events: list[BackfillEvent]) -> int:
    """イベントを DB に挿入."""
    cur = conn.cursor()
    for ev in events:
        cur.execute(
            """
            INSERT INTO events
                (item_id, event_type, price, old_price, threshold_days, created_at, notified)
            VALUES (?, ?, ?, ?, ?, ?, 0)
            """,
            (ev.item_id, ev.event_type, ev.price, ev.old_price, ev.threshold_days, ev.record_time),
        )
    conn.commit()
    return len(events)


def format_price(price: int) -> str:
    """価格をフォーマット."""
    return f"¥{price:,}"


def print_events(events: list[BackfillEvent]) -> None:
    """検出したイベントを表示."""
    for i, ev in enumerate(events, 1):
        event_label = "最安値更新" if ev.event_type == EventType.LOWEST_PRICE.value else "価格下落"
        days_info = f" ({ev.threshold_days}日間)" if ev.threshold_days is not None else ""
        print(
            f"  {i:4d}. [{event_label}{days_info}] {ev.item_name} ({ev.store}): "
            f"{format_price(ev.old_price)} → {format_price(ev.price)} @ {ev.record_time}"
        )


def main(config_file: pathlib.Path, dry_run: bool) -> None:
    """メイン処理."""
    config = price_watch.config.load(config_file)
    db_path = config.data.price / price_watch.const.DB_FILE

    if not db_path.exists():
        logging.error("データベースファイルが見つかりません: %s", db_path)
        raise SystemExit(1)

    # イベント判定設定を取得
    judge_config = config.check.judge
    ignore_hours = judge_config.ignore.hour if judge_config else 24
    windows = judge_config.windows if judge_config else []

    logging.info("データベース: %s", db_path)
    logging.info("ignore_hours: %d", ignore_hours)
    logging.info("price_drop windows: %d 個", len(windows))
    for w in windows:
        parts = []
        if w.rate is not None:
            parts.append(f"rate={w.rate}%")
        if w.value is not None:
            parts.append(f"value={w.value}円")
        logging.info("  - %d日間: %s", w.days, ", ".join(parts))
    if dry_run:
        logging.info("ドライランモード: DB への書き込みは行いません")

    all_events: list[BackfillEvent] = []

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = dict_factory  # type: ignore[assignment]

        ctx = BackfillContext(
            conn=conn,
            ignore_hours=ignore_hours,
            windows=windows,
            dry_run=dry_run,
        )

        items = get_all_items(conn)
        logging.info("対象アイテム数: %d", len(items))

        for item in items:
            ctx.stats.items_scanned += 1
            events = process_item(ctx, item)
            all_events.extend(events)

        # 結果表示
        print(f"\n{'=' * 70}")
        print("イベント補完結果")
        print(f"{'=' * 70}")
        print(f"スキャンしたアイテム数: {ctx.stats.items_scanned}")
        print(f"検出した最安値更新イベント: {ctx.stats.lowest_price_found}")
        print(f"検出した価格下落イベント: {ctx.stats.price_drop_found}")
        print(f"既に記録済み（スキップ）: {ctx.stats.already_recorded}")
        print(f"補完対象イベント合計: {len(all_events)}")

        if all_events:
            print(f"\n{'─' * 70}")
            print("補完対象イベント一覧:")
            print(f"{'─' * 70}")
            print_events(all_events)

            if dry_run:
                print(f"\n[ドライラン] {len(all_events)} 件のイベントが補完対象です（DB 未変更）")
            else:
                inserted = insert_events(conn, all_events)
                ctx.stats.inserted = inserted
                logging.info("DB に %d 件のイベントを挿入しました", inserted)
                print(f"\n{inserted} 件のイベントを DB に挿入しました")
        else:
            print("\n補完が必要なイベントはありません")


if __name__ == "__main__":
    import docopt
    import my_lib.logger

    assert __doc__ is not None  # noqa: S101
    args = docopt.docopt(__doc__)

    config_file = pathlib.Path(args["-c"])
    dry_run = args["--dry-run"]
    debug_mode = args["-D"]

    my_lib.logger.init("backfill-events", level=logging.DEBUG if debug_mode else logging.INFO)

    main(config_file, dry_run)
