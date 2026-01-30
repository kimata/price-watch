#!/usr/bin/env python3
"""
価格履歴を遡り、記録されていないイベント（最安値更新・価格下落）を補完するスクリプト。

過去のバグにより記録されなかったイベントを、価格履歴データから再現して
events テーブルに挿入します。

イベント判定ロジックは本番 (event.py) と同等です:
- LOWEST_PRICE: 過去全期間の最安値を更新した場合（lowest_config の閾値判定対応）
- PRICE_DROP: 指定期間内の最安値から一定以上下落した場合

Usage:
  backfill_events.py [-c CONFIG] [-t TARGET] [--dry-run] [--rebuild] [--backfill-urls] [-D]

Options:
  -c CONFIG         : CONFIG を設定ファイルとして読み込んで実行します。
                      [default: config.yaml]
  -t TARGET         : TARGET をターゲット設定ファイルとして読み込みます。
                      [default: target.yaml]
  --dry-run         : DB に書き込まず、検出結果のみ表示します。
  --rebuild         : 価格変動イベント（lowest_price, price_drop）を全削除してから
                      再生成します。再構築できないイベントは削除しません。
  --backfill-urls   : 既存イベントの url カラムを現在のアイテム URL で埋めます。
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
import price_watch.target
from price_watch.event import EventType

# 再構築対象のイベントタイプ（価格履歴から再生成可能なもの）
REBUILDABLE_EVENT_TYPES = (EventType.LOWEST_PRICE.value, EventType.PRICE_DROP.value)


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
    url: str | None = None


@dataclass
class BackfillStats:
    """補完統計."""

    items_scanned: int = 0
    lowest_price_found: int = 0
    price_drop_found: int = 0
    already_recorded: int = 0
    inserted: int = 0
    cleared: int = 0
    urls_backfilled: int = 0


@dataclass
class BackfillContext:
    """補完処理コンテキスト."""

    conn: sqlite3.Connection
    ignore_hours: int
    windows: list[price_watch.config.PriceDropWindow] = field(default_factory=list)
    lowest_config: price_watch.config.LowestConfig | None = None
    currency_rates: list[price_watch.config.CurrencyRate] = field(default_factory=list)
    store_price_units: dict[str, str] = field(default_factory=dict)
    dry_run: bool = False
    rebuild: bool = False
    stats: BackfillStats = field(default_factory=BackfillStats)

    def get_currency_rate(self, store: str) -> float:
        """ストアの通貨レートを取得."""
        price_unit = self.store_price_units.get(store, "円")
        for cr in self.currency_rates:
            if cr.label == price_unit:
                return cr.rate
        return 1.0


def get_all_items(conn: sqlite3.Connection) -> list[dict]:
    """全アイテムを取得."""
    cur = conn.cursor()
    cur.execute("SELECT id, name, store, url FROM items ORDER BY name, store")
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
    current_price: int,
    running_min: int,
    last_lowest_event_price: int | None,
    record_time: str,
    existing_events: list[dict],
    currency_rate: float,
) -> bool:
    """最安値更新イベントを判定（本番 event.check_lowest_price と同等ロジック）.

    Args:
        ctx: 補完処理コンテキスト
        current_price: 現在の価格
        running_min: これまでの全期間最安値
        last_lowest_event_price: 直近の LOWEST_PRICE イベントの price（ベースライン算出用）
        record_time: レコードの時刻
        existing_events: 既存イベントのリスト
        currency_rate: 通貨換算レート

    Returns:
        イベントを検出した場合 True
    """
    # 本番ロジック: current_price >= lowest_price → スキップ
    if current_price >= running_min:
        return False

    # 閾値判定（lowest_config がある場合）
    lowest_config = ctx.lowest_config
    if lowest_config is not None and (lowest_config.rate is not None or lowest_config.value is not None):
        # ベースラインの決定: 直近の LOWEST_PRICE イベントの price、なければ全期間最安値
        baseline = last_lowest_event_price if last_lowest_event_price is not None else running_min

        drop_amount = baseline - current_price
        if drop_amount <= 0:
            return False

        effective_drop = drop_amount * currency_rate
        threshold_met = False

        if lowest_config.rate is not None:
            drop_rate = (drop_amount / baseline) * 100
            if drop_rate >= lowest_config.rate:
                threshold_met = True

        if lowest_config.value is not None and effective_drop >= lowest_config.value:
            threshold_met = True

        if not threshold_met:
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
    currency_rate: float,
) -> BackfillEvent | None:
    """価格下落イベントを判定（本番 event.check_price_drop と同等ロジック）.

    Args:
        ctx: 補完処理コンテキスト
        item_id: アイテム ID
        current_price: 現在の価格
        record_time: レコードの時刻
        existing_events: 既存イベントのリスト
        currency_rate: 通貨換算レート

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

        effective_drop = drop_amount * currency_rate

        should_fire = False

        if window.rate is not None:
            drop_rate = (drop_amount / lowest_in_period) * 100
            if drop_rate >= window.rate:
                should_fire = True

        if window.value is not None and effective_drop >= window.value:
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
    item_url = item.get("url")

    records = get_price_history_asc(ctx.conn, item_id)
    if len(records) < 2:
        return []

    existing_events = get_existing_events(ctx.conn, item_id)
    events_to_insert: list[BackfillEvent] = []

    currency_rate = ctx.get_currency_rate(store)

    running_min: int | None = None
    # 直近の LOWEST_PRICE イベントの price をトラッキング（閾値判定用）
    last_lowest_event_price: int | None = _find_last_lowest_event_price(existing_events)

    for record in records:
        current_price = record["price"]
        record_time = record["time"]

        if running_min is None:
            # 最初のレコード: 最安値を初期化（本番でも初回はイベント発生させない）
            running_min = current_price
            continue

        # LOWEST_PRICE チェック
        if check_lowest_price_backfill(
            ctx,
            current_price,
            running_min,
            last_lowest_event_price,
            record_time,
            existing_events,
            currency_rate,
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
                url=item_url,
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
            # ベースラインを更新
            last_lowest_event_price = current_price
            ctx.stats.lowest_price_found += 1

        # PRICE_DROP チェック
        if ctx.windows:
            drop_event = check_price_drop_backfill(
                ctx, item_id, current_price, record_time, existing_events, currency_rate
            )
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
                    url=item_url,
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


def _find_last_lowest_event_price(existing_events: list[dict]) -> int | None:
    """既存イベントから直近の LOWEST_PRICE イベントの price を取得."""
    last_price = None
    for ev in existing_events:
        if ev["event_type"] == EventType.LOWEST_PRICE.value and ev["price"] is not None:
            last_price = ev["price"]
    return last_price


def clear_rebuildable_events(conn: sqlite3.Connection) -> int:
    """再構築可能なイベント（lowest_price, price_drop）を全削除.

    再構築できないイベント（back_in_stock, crawl_failure, data_retrieval_failure）は
    削除しない。

    Returns:
        削除した件数
    """
    cur = conn.cursor()
    placeholders = ", ".join("?" for _ in REBUILDABLE_EVENT_TYPES)
    cur.execute(
        f"DELETE FROM events WHERE event_type IN ({placeholders})",  # noqa: S608
        REBUILDABLE_EVENT_TYPES,
    )
    deleted = cur.rowcount
    conn.commit()
    return deleted


def insert_events(conn: sqlite3.Connection, events: list[BackfillEvent]) -> int:
    """イベントを DB に挿入."""
    cur = conn.cursor()
    for ev in events:
        cur.execute(
            """
            INSERT INTO events
                (item_id, event_type, price, old_price, threshold_days, url, created_at, notified)
            VALUES (?, ?, ?, ?, ?, ?, ?, 0)
            """,
            (ev.item_id, ev.event_type, ev.price, ev.old_price, ev.threshold_days, ev.url, ev.record_time),
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


def _build_store_price_units(target_config: price_watch.target.TargetConfig) -> dict[str, str]:
    """ターゲット設定からストア名 → price_unit のマッピングを構築."""
    result: dict[str, str] = {}
    for store in target_config.stores:
        result[store.name] = store.price_unit
    return result


def ensure_url_column(conn: sqlite3.Connection) -> bool:
    """events テーブルに url カラムが存在することを確認し、なければ追加する.

    Args:
        conn: データベース接続

    Returns:
        カラムを追加した場合 True
    """
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(events)")
    columns = [row["name"] for row in cur.fetchall()]

    if "url" not in columns:
        logging.info("events テーブルに url カラムを追加します")
        cur.execute("ALTER TABLE events ADD COLUMN url TEXT")
        conn.commit()
        return True
    return False


def backfill_urls(conn: sqlite3.Connection, *, dry_run: bool = False) -> int:
    """既存イベントの url カラムを現在のアイテム URL で埋める.

    url が NULL のイベントについて、関連するアイテムの現在の URL で更新する。
    過去のイベント URL のスナップショットとしては不正確だが、NULL よりはマシ。

    Args:
        conn: データベース接続
        dry_run: True の場合は DB に書き込まない

    Returns:
        更新した件数
    """
    cur = conn.cursor()

    # url カラムがなければ追加
    if not dry_run:
        ensure_url_column(conn)

    # url が NULL のイベントをアイテム URL で更新
    cur.execute(
        """
        SELECT e.id, i.url
        FROM events e
        JOIN items i ON e.item_id = i.id
        WHERE e.url IS NULL AND i.url IS NOT NULL
        """
    )
    events_to_update = cur.fetchall()

    if dry_run:
        return len(events_to_update)

    for event in events_to_update:
        event_id = event["id"]
        item_url = event["url"]
        cur.execute("UPDATE events SET url = ? WHERE id = ?", (item_url, event_id))

    conn.commit()
    return len(events_to_update)


def main(
    config_file: pathlib.Path,
    target_file: pathlib.Path,
    *,
    dry_run: bool,
    rebuild: bool,
    backfill_urls_mode: bool = False,
) -> None:
    """メイン処理."""
    config = price_watch.config.load(config_file)
    db_path = config.data.price / price_watch.const.DB_FILE

    if not db_path.exists():
        logging.error("データベースファイルが見つかりません: %s", db_path)
        raise SystemExit(1)

    logging.info("データベース: %s", db_path)

    # URL バックフィルモード
    if backfill_urls_mode:
        logging.info("URL バックフィルモード: 既存イベントの url カラムを埋めます")
        if dry_run:
            logging.info("ドライランモード: DB への書き込みは行いません")

        with sqlite3.connect(db_path) as conn:
            conn.row_factory = dict_factory  # type: ignore[assignment]
            count = backfill_urls(conn, dry_run=dry_run)

        print(f"\n{'=' * 70}")
        print("URL バックフィル結果")
        print(f"{'=' * 70}")
        if dry_run:
            print(f"[ドライラン] {count} 件のイベントの URL を更新対象（DB 未変更）")
        else:
            print(f"{count} 件のイベントの URL を更新しました")
        return

    # ターゲット設定を読み込み（通貨レート解決用）
    try:
        target_config = price_watch.target.load(target_file)
        store_price_units = _build_store_price_units(target_config)
    except Exception:
        logging.warning("ターゲット設定の読み込みに失敗しました。通貨レートはデフォルト(1.0)を使用します")
        store_price_units = {}

    # イベント判定設定を取得
    drop_config = config.check.drop
    ignore_hours = drop_config.ignore.hour if drop_config else 24
    windows = drop_config.windows if drop_config else []

    lowest_config = config.check.lowest
    currency_rates = list(config.check.currency)

    logging.info("ignore_hours: %d", ignore_hours)
    logging.info("price_drop windows: %d 個", len(windows))
    for w in windows:
        parts = []
        if w.rate is not None:
            parts.append(f"rate={w.rate}%")
        if w.value is not None:
            parts.append(f"value={w.value}")
        logging.info("  - %d日間: %s", w.days, ", ".join(parts))

    if lowest_config is not None:
        parts = []
        if lowest_config.rate is not None:
            parts.append(f"rate={lowest_config.rate}%")
        if lowest_config.value is not None:
            parts.append(f"value={lowest_config.value}")
        logging.info("lowest_config: %s", ", ".join(parts))
    else:
        logging.info("lowest_config: なし（即発火）")

    if currency_rates:
        for cr in currency_rates:
            logging.info("currency: %s = %.1f", cr.label, cr.rate)

    if dry_run:
        logging.info("ドライランモード: DB への書き込みは行いません")
    if rebuild:
        logging.info("再構築モード: 価格変動イベントを全削除してから再生成します")

    all_events: list[BackfillEvent] = []

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = dict_factory  # type: ignore[assignment]

        # url カラムがなければ追加（既存DB対応）
        if not dry_run:
            ensure_url_column(conn)

        ctx = BackfillContext(
            conn=conn,
            ignore_hours=ignore_hours,
            windows=windows,
            lowest_config=lowest_config,
            currency_rates=currency_rates,
            store_price_units=store_price_units,
            dry_run=dry_run,
            rebuild=rebuild,
        )

        # rebuild モード: 価格変動イベントをクリア
        if rebuild and not dry_run:
            cleared = clear_rebuildable_events(conn)
            ctx.stats.cleared = cleared
            logging.info("価格変動イベントを %d 件削除しました", cleared)

        items = get_all_items(conn)
        logging.info("対象アイテム数: %d", len(items))

        for item in items:
            ctx.stats.items_scanned += 1
            events = process_item(ctx, item)
            all_events.extend(events)

        # 結果表示
        print(f"\n{'=' * 70}")
        title = "イベント再構築結果" if rebuild else "イベント補完結果"
        print(title)
        print(f"{'=' * 70}")
        print(f"スキャンしたアイテム数: {ctx.stats.items_scanned}")
        if rebuild:
            print(f"削除した価格変動イベント: {ctx.stats.cleared}")
        print(f"検出した最安値更新イベント: {ctx.stats.lowest_price_found}")
        print(f"検出した価格下落イベント: {ctx.stats.price_drop_found}")
        if not rebuild:
            print(f"既に記録済み（スキップ）: {ctx.stats.already_recorded}")
        print(f"挿入対象イベント合計: {len(all_events)}")

        if all_events:
            print(f"\n{'─' * 70}")
            print("挿入対象イベント一覧:")
            print(f"{'─' * 70}")
            print_events(all_events)

            if dry_run:
                if rebuild:
                    # rebuild + dry-run: クリア対象件数を表示
                    cur = conn.cursor()
                    placeholders = ", ".join("?" for _ in REBUILDABLE_EVENT_TYPES)
                    cur.execute(
                        f"SELECT COUNT(*) FROM events WHERE event_type IN ({placeholders})",  # noqa: S608
                        REBUILDABLE_EVENT_TYPES,
                    )
                    row = cur.fetchone()
                    count = next(iter(row.values())) if row else 0
                    print(
                        f"\n[ドライラン] 削除対象: {count} 件 / 挿入対象: {len(all_events)} 件（DB 未変更）"
                    )
                else:
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
    target_file = pathlib.Path(args["-t"])
    dry_run = args["--dry-run"]
    rebuild = args["--rebuild"]
    backfill_urls_flag = args["--backfill-urls"]
    debug_mode = args["-D"]

    my_lib.logger.init("backfill-events", level=logging.DEBUG if debug_mode else logging.INFO)

    main(config_file, target_file, dry_run=dry_run, rebuild=rebuild, backfill_urls_mode=backfill_urls_flag)
