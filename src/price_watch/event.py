#!/usr/bin/env python3
"""イベント管理モジュール.

価格変動や在庫復活などのイベントを検出・記録・通知します。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import price_watch.config
    from price_watch.managers import HistoryManager
    from price_watch.models import EventRecord


class EventType(str, Enum):
    """イベントタイプ."""

    BACK_IN_STOCK = "back_in_stock"  # 在庫復活
    CRAWL_FAILURE = "crawl_failure"  # クロール失敗継続
    DATA_RETRIEVAL_FAILURE = "data_retrieval_failure"  # 情報取得エラー（価格・在庫両方なし継続）
    LOWEST_PRICE = "lowest_price"  # 過去最安値更新
    PRICE_DROP = "price_drop"  # 価格下落


@dataclass
class EventResult:
    """イベント判定結果."""

    event_type: EventType
    should_notify: bool
    price: int | None = None
    old_price: int | None = None
    threshold_days: int | None = None
    url: str | None = None


def check_back_in_stock(
    history: HistoryManager,
    item_id: int,
    current_stock: int | None,
    last_stock: int | None,
    ignore_hours: int,
    min_out_of_stock_hours: float = 3.0,
) -> EventResult | None:
    """在庫復活イベントを判定.

    在庫なしが min_out_of_stock_hours 以上継続した後に在庫が復活した場合に
    イベントを発生させる。クロール失敗は在庫なし継続時間に含めない。

    Args:
        history: HistoryManager インスタンス
        item_id: アイテム ID
        current_stock: 現在の在庫状態（None: 不明, 0: なし, 1: あり）
        last_stock: 前回の在庫状態（None: 不明, 0: なし, 1: あり）
        ignore_hours: 無視する時間数（重複通知防止）
        min_out_of_stock_hours: 在庫復活と判定するための最小在庫なし継続時間（時間）

    Returns:
        イベント結果。該当しない場合は None。
    """
    # 現在の在庫状態が不明（クロール失敗）の場合はスキップ
    if current_stock is None:
        return None

    # 在庫なし → 在庫あり の変化がない場合はスキップ
    # last_stock が None（前回クロール失敗）の場合も、在庫復活とは判定しない
    if last_stock is None or last_stock != 0 or current_stock != 1:
        return None

    # 在庫なしの継続時間を確認
    out_of_stock_hours = history.get_out_of_stock_duration_hours(item_id)
    if out_of_stock_hours is None or out_of_stock_hours < min_out_of_stock_hours:
        logging.debug(
            "Skipping back_in_stock event: out of stock duration %.1f hours < %.1f hours",
            out_of_stock_hours or 0,
            min_out_of_stock_hours,
        )
        return None

    # 無視区間内に同じイベントがあるかチェック
    if history.has_event_in_hours(item_id, EventType.BACK_IN_STOCK.value, ignore_hours):
        logging.debug("Skipping back_in_stock event: recent event exists within %d hours", ignore_hours)
        return EventResult(event_type=EventType.BACK_IN_STOCK, should_notify=False)

    logging.info("Back in stock detected: out of stock for %.1f hours", out_of_stock_hours)
    return EventResult(event_type=EventType.BACK_IN_STOCK, should_notify=True)


def check_crawl_failure(history: HistoryManager, item_id: int) -> EventResult | None:
    """クロール失敗イベントを判定.

    過去24時間、一度も正常にクロールできていない場合にイベント発生。
    前回の判定から24時間経過していれば再通知。

    Args:
        history: HistoryManager インスタンス
        item_id: アイテム ID

    Returns:
        イベント結果。該当しない場合は None。
    """
    # 過去24時間に成功したクロールがあるかチェック
    if history.has_successful_crawl_in_hours(item_id, 24):
        return None

    # 過去24時間以内にこのイベントが既に発生しているかチェック
    if history.has_event_in_hours(item_id, EventType.CRAWL_FAILURE.value, 24):
        logging.debug("Skipping crawl_failure event: recent event exists within 24 hours")
        return EventResult(event_type=EventType.CRAWL_FAILURE, should_notify=False)

    return EventResult(event_type=EventType.CRAWL_FAILURE, should_notify=True)


def check_data_retrieval_failure(
    history: HistoryManager,
    item_id: int,
    min_failure_hours: float = 6.0,
    ignore_hours: int = 6,
) -> EventResult | None:
    """情報取得エラーイベントを判定.

    価格・在庫両方の情報が min_failure_hours 以上取得できていない場合にイベント発生。

    Args:
        history: HistoryManager インスタンス
        item_id: アイテム ID
        min_failure_hours: イベント発生の最小失敗継続時間（時間）
        ignore_hours: 無視する時間数（重複通知防止）

    Returns:
        イベント結果。該当しない場合は None。
    """
    # データ取得失敗の継続時間を取得
    no_data_hours = history.get_no_data_duration_hours(item_id)

    if no_data_hours is None or no_data_hours < min_failure_hours:
        return None

    # 無視区間内に同じイベントがあるかチェック
    if history.has_event_in_hours(item_id, EventType.DATA_RETRIEVAL_FAILURE.value, ignore_hours):
        logging.debug(
            "Skipping data_retrieval_failure event: recent event exists within %d hours",
            ignore_hours,
        )
        return EventResult(event_type=EventType.DATA_RETRIEVAL_FAILURE, should_notify=False)

    logging.info("Data retrieval failure detected: no data for %.1f hours", no_data_hours)
    return EventResult(event_type=EventType.DATA_RETRIEVAL_FAILURE, should_notify=True)


def check_lowest_price(
    history: HistoryManager,
    item_id: int,
    current_price: int,
    ignore_hours: int,
    *,
    lowest_config: price_watch.config.LowestConfig | None = None,
    currency_rate: float = 1.0,
) -> EventResult | None:
    """過去最安値更新イベントを判定.

    Args:
        history: HistoryManager インスタンス
        item_id: アイテム ID
        current_price: 現在の価格
        ignore_hours: 無視する時間数
        lowest_config: 最安値更新の閾値設定（None の場合は従来通り即発火）
        currency_rate: 通貨換算レート（value 判定用、デフォルト 1.0）

    Returns:
        イベント結果。該当しない場合は None。
    """
    # 過去全期間の最安値を取得
    lowest_price = history.get_lowest_in_period(item_id, days=None)

    if lowest_price is None:
        # 初めての価格記録の場合は最安値イベントを発生させない
        return None

    if current_price >= lowest_price:
        return None

    # 閾値判定
    if lowest_config is not None and (lowest_config.rate is not None or lowest_config.value is not None):
        # ベースラインの決定: 直近の LOWEST_PRICE イベントの price、なければ全期間最安値
        last_event = history.get_last_event(item_id, EventType.LOWEST_PRICE.value)
        baseline = (
            last_event.price if last_event is not None and last_event.price is not None else lowest_price
        )

        drop_amount = baseline - current_price
        if drop_amount <= 0:
            return None

        effective_drop = drop_amount * currency_rate
        threshold_met = False

        if lowest_config.rate is not None:
            drop_rate = (drop_amount / baseline) * 100
            if drop_rate >= lowest_config.rate:
                threshold_met = True
                logging.info(
                    "Lowest price threshold met: %.1f%% drop (threshold: %.1f%%)",
                    drop_rate,
                    lowest_config.rate,
                )

        if lowest_config.value is not None and effective_drop >= lowest_config.value:
            threshold_met = True
            logging.info(
                "Lowest price threshold met: %.0f drop (threshold: %d, currency_rate: %.1f)",
                effective_drop,
                lowest_config.value,
                currency_rate,
            )

        if not threshold_met:
            return None

    # 無視区間内に同じイベントがあるかチェック
    if history.has_event_in_hours(item_id, EventType.LOWEST_PRICE.value, ignore_hours):
        logging.debug("Skipping lowest_price event: recent event exists within %d hours", ignore_hours)
        return EventResult(
            event_type=EventType.LOWEST_PRICE,
            should_notify=False,
            price=current_price,
            old_price=lowest_price,
        )

    return EventResult(
        event_type=EventType.LOWEST_PRICE,
        should_notify=True,
        price=current_price,
        old_price=lowest_price,
    )


def check_price_drop(
    history: HistoryManager,
    item_id: int,
    current_price: int,
    windows: list[price_watch.config.PriceDropWindow],
    *,
    currency_rate: float = 1.0,
) -> EventResult | None:
    """価格下落イベントを判定.

    Args:
        history: HistoryManager インスタンス
        item_id: アイテム ID
        current_price: 現在の価格
        windows: 価格下落判定ウィンドウのリスト
        currency_rate: 通貨換算レート（value 判定用、デフォルト 1.0）

    Returns:
        イベント結果。該当しない場合は None。
    """
    for window in windows:
        # 指定期間内の最安値を取得
        lowest_in_period = history.get_lowest_in_period(item_id, days=window.days)

        if lowest_in_period is None:
            continue

        # 価格下落量を計算
        drop_amount = lowest_in_period - current_price

        if drop_amount <= 0:
            continue

        effective_drop = drop_amount * currency_rate

        # 条件判定
        should_notify = False

        if window.rate is not None:
            # パーセンテージでの判定
            drop_rate = (drop_amount / lowest_in_period) * 100
            if drop_rate >= window.rate:
                should_notify = True
                logging.info(
                    "Price drop detected: %d%% drop (threshold: %d%%) in %d days",
                    int(drop_rate),
                    int(window.rate),
                    window.days,
                )

        # 絶対値での判定（通貨換算後の値で比較）
        if window.value is not None and effective_drop >= window.value:
            should_notify = True
            logging.info(
                "Price drop detected: %.0f drop (threshold: %d, currency_rate: %.1f) in %d days",
                effective_drop,
                window.value,
                currency_rate,
                window.days,
            )

        if should_notify:
            return EventResult(
                event_type=EventType.PRICE_DROP,
                should_notify=True,
                price=current_price,
                old_price=lowest_in_period,
                threshold_days=window.days,
            )

    return None


def record_event(
    history: HistoryManager,
    result: EventResult,
    item_id: int,
    *,
    notified: bool = False,
) -> int:
    """イベントを記録.

    Args:
        history: HistoryManager インスタンス
        result: イベント判定結果
        item_id: アイテム ID
        notified: 通知済みフラグ

    Returns:
        イベント ID
    """
    return history.insert_event(
        item_id=item_id,
        event_type=result.event_type.value,
        price=result.price,
        old_price=result.old_price,
        threshold_days=result.threshold_days,
        url=result.url,
        notified=notified,
    )


def format_event_message(event: EventRecord) -> str:
    """イベントからメッセージを生成.

    Args:
        event: イベント情報

    Returns:
        フォーマットされたメッセージ
    """
    event_type = event.event_type
    item_name = event.item_name or "不明"
    price = event.price
    old_price = event.old_price
    threshold_days = event.threshold_days

    match event_type:
        case EventType.BACK_IN_STOCK.value:
            return f"{item_name} の在庫が復活しました"

        case EventType.CRAWL_FAILURE.value:
            return f"{item_name} のクロールが24時間失敗しています"

        case EventType.DATA_RETRIEVAL_FAILURE.value:
            return f"{item_name} の情報取得が6時間以上失敗しています"

        case EventType.LOWEST_PRICE.value:
            if price is not None and old_price is not None:
                return f"{item_name} が過去最安値を更新: {old_price:,}円 → {price:,}円"
            return f"{item_name} が過去最安値を更新しました"

        case EventType.PRICE_DROP.value:
            if price is not None and old_price is not None and threshold_days is not None:
                drop = old_price - price
                return f"{item_name} が{threshold_days}日間で{drop:,}円値下げ: {old_price:,}円 → {price:,}円"
            return f"{item_name} の価格が下がりました"

        case _:
            return f"{item_name} でイベントが発生しました"


def format_event_title(event_type: str) -> str:
    """イベントタイプからタイトルを生成.

    Args:
        event_type: イベントタイプ

    Returns:
        タイトル
    """
    match event_type:
        case EventType.BACK_IN_STOCK.value:
            return "在庫復活"
        case EventType.CRAWL_FAILURE.value:
            return "クロール失敗"
        case EventType.DATA_RETRIEVAL_FAILURE.value:
            return "エラー"
        case EventType.LOWEST_PRICE.value:
            return "過去最安値"
        case EventType.PRICE_DROP.value:
            return "価格下落"
        case _:
            return "イベント"
