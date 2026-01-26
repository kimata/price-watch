#!/usr/bin/env python3
"""イベント管理モジュール.

価格変動や在庫復活などのイベントを検出・記録・通知します。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any

import price_watch.history

if TYPE_CHECKING:
    import price_watch.config


class EventType(str, Enum):
    """イベントタイプ."""

    BACK_IN_STOCK = "back_in_stock"  # 在庫復活
    CRAWL_FAILURE = "crawl_failure"  # クロール失敗継続
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


def check_back_in_stock(
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
    out_of_stock_hours = price_watch.history.get_out_of_stock_duration_hours(item_id)
    if out_of_stock_hours is None or out_of_stock_hours < min_out_of_stock_hours:
        logging.debug(
            "Skipping back_in_stock event: out of stock duration %.1f hours < %.1f hours",
            out_of_stock_hours or 0,
            min_out_of_stock_hours,
        )
        return None

    # 無視区間内に同じイベントがあるかチェック
    if price_watch.history.has_event_in_hours(item_id, EventType.BACK_IN_STOCK.value, ignore_hours):
        logging.debug("Skipping back_in_stock event: recent event exists within %d hours", ignore_hours)
        return EventResult(event_type=EventType.BACK_IN_STOCK, should_notify=False)

    logging.info("Back in stock detected: out of stock for %.1f hours", out_of_stock_hours)
    return EventResult(event_type=EventType.BACK_IN_STOCK, should_notify=True)


def check_crawl_failure(item_id: int) -> EventResult | None:
    """クロール失敗イベントを判定.

    過去24時間、一度も正常にクロールできていない場合にイベント発生。
    前回の判定から24時間経過していれば再通知。

    Args:
        item_id: アイテム ID

    Returns:
        イベント結果。該当しない場合は None。
    """
    # 過去24時間に成功したクロールがあるかチェック
    if price_watch.history.has_successful_crawl_in_hours(item_id, 24):
        return None

    # 過去24時間以内にこのイベントが既に発生しているかチェック
    if price_watch.history.has_event_in_hours(item_id, EventType.CRAWL_FAILURE.value, 24):
        logging.debug("Skipping crawl_failure event: recent event exists within 24 hours")
        return EventResult(event_type=EventType.CRAWL_FAILURE, should_notify=False)

    return EventResult(event_type=EventType.CRAWL_FAILURE, should_notify=True)


def check_lowest_price(
    item_id: int,
    current_price: int,
    ignore_hours: int,
) -> EventResult | None:
    """過去最安値更新イベントを判定.

    Args:
        item_id: アイテム ID
        current_price: 現在の価格
        ignore_hours: 無視する時間数

    Returns:
        イベント結果。該当しない場合は None。
    """
    # 過去全期間の最安値を取得
    lowest_price = price_watch.history.get_lowest_price_in_period(item_id, days=None)

    if lowest_price is None:
        # 初めての価格記録の場合は最安値イベントを発生させない
        return None

    if current_price >= lowest_price:
        return None

    # 無視区間内に同じイベントがあるかチェック
    if price_watch.history.has_event_in_hours(item_id, EventType.LOWEST_PRICE.value, ignore_hours):
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
    item_id: int,
    current_price: int,
    windows: list[price_watch.config.PriceDropWindow],
) -> EventResult | None:
    """価格下落イベントを判定.

    Args:
        item_id: アイテム ID
        current_price: 現在の価格
        windows: 価格下落判定ウィンドウのリスト

    Returns:
        イベント結果。該当しない場合は None。
    """
    for window in windows:
        # 指定期間内の最安値を取得
        lowest_in_period = price_watch.history.get_lowest_price_in_period(item_id, days=window.days)

        if lowest_in_period is None:
            continue

        # 価格下落量を計算
        drop_amount = lowest_in_period - current_price

        if drop_amount <= 0:
            continue

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

        # 絶対値での判定
        if window.value is not None and drop_amount >= window.value:
            should_notify = True
            logging.info(
                "Price drop detected: %d yen drop (threshold: %d yen) in %d days",
                drop_amount,
                window.value,
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


def record_event(result: EventResult, item_id: int, *, notified: bool = False) -> int:
    """イベントを記録.

    Args:
        result: イベント判定結果
        item_id: アイテム ID
        notified: 通知済みフラグ

    Returns:
        イベント ID
    """
    return price_watch.history.insert_event(
        item_id=item_id,
        event_type=result.event_type.value,
        price=result.price,
        old_price=result.old_price,
        threshold_days=result.threshold_days,
        notified=notified,
    )


def get_recent_events(limit: int = 10) -> list[dict[str, Any]]:
    """最新のイベントを取得.

    Args:
        limit: 取得件数

    Returns:
        イベントリスト
    """
    return price_watch.history.get_recent_events(limit)


def format_event_message(event: dict[str, Any]) -> str:
    """イベントからメッセージを生成.

    Args:
        event: イベント情報

    Returns:
        フォーマットされたメッセージ
    """
    event_type = event.get("event_type", "")
    item_name = event.get("item_name", "不明")
    price = event.get("price")
    old_price = event.get("old_price")
    threshold_days = event.get("threshold_days")

    match event_type:
        case EventType.BACK_IN_STOCK.value:
            return f"{item_name} の在庫が復活しました"

        case EventType.CRAWL_FAILURE.value:
            return f"{item_name} のクロールが24時間失敗しています"

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
        case EventType.LOWEST_PRICE.value:
            return "過去最安値"
        case EventType.PRICE_DROP.value:
            return "価格下落"
        case _:
            return "イベント"
