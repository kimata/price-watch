#!/usr/bin/env python3
"""メルカリ検索による価格チェック."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

import my_lib.store.mercari.search
import selenium.webdriver.support.wait

import price_watch.history

if TYPE_CHECKING:
    from selenium.webdriver.remote.webdriver import WebDriver

    from price_watch.config import AppConfig

# 検索結果の最大取得件数
MAX_SEARCH_RESULTS = 40


def _parse_cond(cond_str: str | None) -> list[my_lib.store.mercari.search.ItemCondition] | None:
    """商品状態文字列をパース.

    "NEW|LIKE_NEW" 形式から ItemCondition のリストに変換。

    Args:
        cond_str: 商品状態文字列（"NEW|LIKE_NEW" 形式）

    Returns:
        ItemCondition のリスト、または None
    """
    if not cond_str:
        return None

    cond_map = {
        "NEW": my_lib.store.mercari.search.ItemCondition.NEW,
        "LIKE_NEW": my_lib.store.mercari.search.ItemCondition.LIKE_NEW,
        "GOOD": my_lib.store.mercari.search.ItemCondition.GOOD,
        "FAIR": my_lib.store.mercari.search.ItemCondition.FAIR,
        "POOR": my_lib.store.mercari.search.ItemCondition.POOR,
        "BAD": my_lib.store.mercari.search.ItemCondition.BAD,
    }

    result = []
    for cond_name in cond_str.split("|"):
        cond_name = cond_name.strip().upper()
        if cond_name in cond_map:
            result.append(cond_map[cond_name])
        else:
            logging.warning("Unknown condition: %s", cond_name)

    return result if result else None


def _build_search_condition(item: dict[str, Any]) -> my_lib.store.mercari.search.SearchCondition:
    """アイテム情報から検索条件を構築.

    Args:
        item: アイテム情報（search_keyword, exclude_keyword, price_range, cond を含む）

    Returns:
        SearchCondition
    """
    # キーワード: search_keyword がなければ name を使用
    keyword = item.get("search_keyword") or item["name"]

    # 価格範囲
    price_range = item.get("price_range")
    price_min = None
    price_max = None
    if price_range:
        if len(price_range) >= 1:
            price_min = price_range[0]
        if len(price_range) >= 2:
            price_max = price_range[1]

    # 商品状態
    item_conditions = _parse_cond(item.get("cond"))

    return my_lib.store.mercari.search.SearchCondition(
        keyword=keyword,
        exclude_keyword=item.get("exclude_keyword"),
        price_min=price_min,
        price_max=price_max,
        item_conditions=item_conditions,
    )


def _build_search_cond_json(condition: my_lib.store.mercari.search.SearchCondition) -> str:
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


def check(
    config: AppConfig,
    driver: WebDriver,
    item: dict[str, Any],
) -> None:
    """メルカリ検索で最安値商品を取得.

    - 最大40件取得して最安値を選定
    - item["url"] を最安商品の URL で更新
    - item["price"], item["stock"] を設定
    - item["search_keyword"], item["search_cond"] を設定（item_key 生成用）

    Args:
        config: アプリケーション設定
        driver: WebDriver インスタンス
        item: アイテム情報（name, search_keyword, exclude_keyword, price_range, cond を含む）
    """
    wait = selenium.webdriver.support.wait.WebDriverWait(driver, 10)

    # 検索条件を構築
    condition = _build_search_condition(item)

    logging.info("[メルカリ検索] %s: キーワード='%s'", item["name"], condition.keyword)

    # 検索実行
    # 20件以上取得する場合は scroll_to_load=True
    scroll_to_load = MAX_SEARCH_RESULTS > 20
    results = my_lib.store.mercari.search.search(
        driver,
        wait,
        condition,
        max_items=MAX_SEARCH_RESULTS,
        scroll_to_load=scroll_to_load,
    )

    # item_key 生成用のデータを設定
    item["search_keyword"] = condition.keyword
    item["search_cond"] = _build_search_cond_json(condition)

    if not results:
        logging.info("[メルカリ検索] %s: 検索結果なし", item["name"])
        item["stock"] = 0
        item["crawl_success"] = True
        # price は設定しない（None 扱い）
        # url は空のまま
        return

    # 最安値を探す
    cheapest = min(results, key=lambda r: r.price)

    logging.info(
        "[メルカリ検索] %s: %d件中最安値 ¥%s - %s",
        item["name"],
        len(results),
        f"{cheapest.price:,}",
        cheapest.title,
    )

    # アイテム情報を更新
    item["url"] = cheapest.url
    item["price"] = cheapest.price
    item["stock"] = 1
    item["crawl_success"] = True


def generate_item_key(item: dict[str, Any]) -> str:
    """メルカリアイテム用の item_key を生成.

    Args:
        item: アイテム情報（search_keyword, search_cond を含む）

    Returns:
        item_key
    """
    return price_watch.history.generate_item_key(
        search_keyword=item.get("search_keyword"),
        search_cond=item.get("search_cond"),
    )
