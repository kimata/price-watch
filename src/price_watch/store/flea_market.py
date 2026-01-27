#!/usr/bin/env python3
"""フリマ検索（メルカリ・ラクマ・PayPayフリマ）による価格チェック."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

import my_lib.store.flea_market
import my_lib.store.mercari.search
import my_lib.store.paypay.search
import my_lib.store.rakuma.search
import selenium.webdriver.support.wait

import price_watch.history
import price_watch.models
import price_watch.target

if TYPE_CHECKING:
    from collections.abc import Callable

    from selenium.webdriver.remote.webdriver import WebDriver

    from price_watch.config import AppConfig
    from price_watch.target import ResolvedItem

# 検索結果の最大取得件数
MAX_SEARCH_RESULTS = 40

# ストアごとの検索関数とログ表示名
_STORE_SEARCH_FUNCS: dict[
    price_watch.target.CheckMethod,
    tuple[
        Callable[..., list[my_lib.store.flea_market.SearchResult]],
        str,
    ],
] = {
    price_watch.target.CheckMethod.MERCARI_SEARCH: (my_lib.store.mercari.search.search, "メルカリ検索"),
    price_watch.target.CheckMethod.RAKUMA_SEARCH: (my_lib.store.rakuma.search.search, "ラクマ検索"),
    price_watch.target.CheckMethod.PAYPAY_SEARCH: (my_lib.store.paypay.search.search, "PayPay検索"),
}


def _parse_cond(cond_str: str | None) -> list[my_lib.store.flea_market.ItemCondition] | None:
    """商品状態文字列をパース.

    "NEW|LIKE_NEW" 形式から ItemCondition のリストに変換。

    Args:
        cond_str: 商品状態文字列（"NEW|LIKE_NEW" 形式）

    Returns:
        ItemCondition のリスト、または None
    """
    if not cond_str:
        return [
            my_lib.store.flea_market.ItemCondition.NEW,
            my_lib.store.flea_market.ItemCondition.LIKE_NEW,
        ]

    cond_map = {
        "NEW": my_lib.store.flea_market.ItemCondition.NEW,
        "LIKE_NEW": my_lib.store.flea_market.ItemCondition.LIKE_NEW,
        "GOOD": my_lib.store.flea_market.ItemCondition.GOOD,
        "FAIR": my_lib.store.flea_market.ItemCondition.FAIR,
        "POOR": my_lib.store.flea_market.ItemCondition.POOR,
        "BAD": my_lib.store.flea_market.ItemCondition.BAD,
    }

    result = []
    for cond_name in cond_str.split("|"):
        cond_name = cond_name.strip().upper()
        if cond_name in cond_map:
            result.append(cond_map[cond_name])
        else:
            logging.warning("Unknown condition: %s", cond_name)

    return result if result else None


def _build_search_condition(item: ResolvedItem) -> my_lib.store.flea_market.SearchCondition:
    """アイテム情報から検索条件を構築.

    Args:
        item: 監視対象アイテム

    Returns:
        SearchCondition
    """
    # キーワード: search_keyword がなければ name を使用
    keyword = item.search_keyword or item.name

    # 価格範囲
    price_min = None
    price_max = None
    if item.price_range:
        if len(item.price_range) >= 1:
            price_min = item.price_range[0]
        if len(item.price_range) >= 2:
            price_max = item.price_range[1]

    # 商品状態
    item_conditions = _parse_cond(item.cond)

    return my_lib.store.flea_market.SearchCondition(
        keyword=keyword,
        exclude_keyword=item.exclude_keyword,
        price_min=price_min,
        price_max=price_max,
        item_conditions=item_conditions,
    )


def _build_search_cond_json(condition: my_lib.store.flea_market.SearchCondition) -> str:
    """検索条件を JSON 文字列に変換（item_key 生成用）.

    Args:
        condition: 検索条件

    Returns:
        JSON 文字列
    """
    data: dict[str, Any] = {}

    if condition.exclude_keyword:
        data["exclude"] = condition.exclude_keyword
    if condition.price_min is not None:
        data["price_min"] = condition.price_min
    if condition.price_max is not None:
        data["price_max"] = condition.price_max
    if condition.item_conditions:
        data["cond"] = [c.value for c in condition.item_conditions]

    return json.dumps(data, sort_keys=True, ensure_ascii=False) if data else ""


def _get_store_label(item: ResolvedItem) -> str:
    """ストアのログ表示名を取得."""
    entry = _STORE_SEARCH_FUNCS.get(item.check_method)
    if entry is not None:
        return entry[1]
    return "フリマ検索"


def check(
    config: AppConfig,
    driver: WebDriver,
    item: ResolvedItem,
) -> price_watch.models.CheckedItem:
    """フリマ検索で最安値商品を取得.

    Args:
        config: アプリケーション設定
        driver: WebDriver インスタンス
        item: 監視対象アイテム

    Returns:
        チェック結果（CheckedItem）
    """
    wait = selenium.webdriver.support.wait.WebDriverWait(driver, 10)

    label = _get_store_label(item)

    # 結果を格納する CheckedItem を作成
    result = price_watch.models.CheckedItem.from_resolved_item(item)

    # 検索条件を構築
    condition = _build_search_condition(item)

    logging.info("[%s] %s: キーワード='%s'", label, item.name, condition.keyword)

    # 検索関数を取得
    entry = _STORE_SEARCH_FUNCS.get(item.check_method)
    if entry is None:
        logging.error("[%s] %s: 未対応のチェックメソッド: %s", label, item.name, item.check_method)
        result.crawl_status = price_watch.models.CrawlStatus.FAILURE
        return result

    search_func = entry[0]

    # 検索実行
    # 20件以上取得する場合は scroll_to_load=True
    scroll_to_load = MAX_SEARCH_RESULTS > 20
    results = search_func(
        driver,
        wait,
        condition,
        max_items=MAX_SEARCH_RESULTS,
        scroll_to_load=scroll_to_load,
    )

    # item_key 生成用のデータを設定
    result.search_keyword = condition.keyword
    result.search_cond = _build_search_cond_json(condition)

    if not results:
        logging.info("[%s] %s: 検索結果なし", label, item.name)
        result.stock = price_watch.models.StockStatus.OUT_OF_STOCK
        result.crawl_status = price_watch.models.CrawlStatus.SUCCESS
        return result

    # 価格範囲でフィルタリング（ページに表示する「関連商品」等を除外）
    filtered_results = results
    if condition.price_min is not None or condition.price_max is not None:
        original_count = len(results)
        filtered_results = [
            r
            for r in results
            if (condition.price_min is None or r.price >= condition.price_min)
            and (condition.price_max is None or r.price <= condition.price_max)
        ]
        if len(filtered_results) < original_count:
            logging.info(
                "[%s] %s: 価格範囲外の商品を除外 (%d件 -> %d件)",
                label,
                item.name,
                original_count,
                len(filtered_results),
            )

    if not filtered_results:
        logging.info("[%s] %s: 価格範囲内の商品なし", label, item.name)
        result.stock = price_watch.models.StockStatus.OUT_OF_STOCK
        result.crawl_status = price_watch.models.CrawlStatus.SUCCESS
        return result

    # 最安値を探す
    cheapest = min(filtered_results, key=lambda r: r.price)

    logging.info(
        "[%s] %s: %d件中最安値 ¥%s - %s",
        label,
        item.name,
        len(filtered_results),
        f"{cheapest.price:,}",
        cheapest.title,
    )

    # 結果を設定
    result.url = cheapest.url
    result.price = cheapest.price
    result.stock = price_watch.models.StockStatus.IN_STOCK
    result.crawl_status = price_watch.models.CrawlStatus.SUCCESS

    return result


def generate_item_key(item: price_watch.models.CheckedItem) -> str:
    """フリマアイテム用の item_key を生成.

    Args:
        item: チェック済みアイテム

    Returns:
        item_key
    """
    return price_watch.history.generate_item_key(
        search_keyword=item.search_keyword,
        search_cond=item.search_cond,
    )
