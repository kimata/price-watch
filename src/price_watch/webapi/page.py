#!/usr/bin/env python3
"""API エンドポイント."""

import logging
from typing import Any

import flask
from flask_pydantic import validate

import price_watch.event
import price_watch.file_cache
import price_watch.history
import price_watch.target
import price_watch.thumbnail
import price_watch.webapi.schemas

blueprint = flask.Blueprint("page", __name__)

# target.yaml のキャッシュ（ファイル更新時刻が変わった場合のみ再読み込み）
_target_config_cache: price_watch.file_cache.FileCache[price_watch.target.TargetConfig] = (
    price_watch.file_cache.FileCache(
        price_watch.target.TARGET_FILE_PATH,
        lambda path: price_watch.target.load(path),
    )
)


def _parse_days(days_str: str | None) -> int | None:
    """期間パラメータをパース."""
    if not days_str or days_str == "all":
        return None
    try:
        return int(days_str)
    except ValueError:
        return 30


def _get_target_item_keys(target_config: price_watch.target.TargetConfig | None) -> set[str]:
    """target.yaml から監視対象アイテムキーのセットを取得."""
    if target_config is None:
        return set()

    keys = set()
    try:
        resolved_items = target_config.resolve_items()
    except Exception:
        logging.warning("Failed to resolve target items")
        return set()

    for item in resolved_items:
        # メルカリ検索の場合は keyword + cond から item_key を生成
        if item.check_method == price_watch.target.CheckMethod.MERCARI_SEARCH:
            keyword = item.search_keyword or item.name
            keys.add(price_watch.history.generate_item_key(search_keyword=keyword, search_cond=""))
        else:
            keys.add(price_watch.history.url_hash(item.url))
    return keys


def _get_target_config() -> price_watch.target.TargetConfig | None:
    """target.yaml の設定を取得（キャッシュ使用）."""
    try:
        return _target_config_cache.get()
    except Exception:
        logging.warning("Failed to load target.yaml config")
        return None


def _get_point_rate(target_config: price_watch.target.TargetConfig | None, store_name: str) -> float:
    """ストアのポイント還元率を取得."""
    if target_config is None:
        return 0.0
    store = target_config.get_store(store_name)
    return store.point_rate if store else 0.0


def _calc_effective_price(price: int | None, point_rate: float) -> int | None:
    """実質価格を計算（ポイント還元考慮）.

    price が None の場合は None を返す。
    """
    if price is None:
        return None
    return int(price * (1 - point_rate / 100))


def _build_history_entries(
    history: list[dict[str, Any]], point_rate: float
) -> list[price_watch.webapi.schemas.PriceHistoryPoint]:
    """履歴エントリリストを構築.

    price が None の場合（在庫なし）も含めて返す。
    """
    return [
        price_watch.webapi.schemas.PriceHistoryPoint(
            time=h["time"],
            price=h["price"],
            effective_price=_calc_effective_price(h["price"], point_rate),
            stock=h["stock"],
        )
        for h in history
    ]


def _build_store_entry(
    item: dict[str, Any],
    latest: dict[str, Any],
    stats: dict[str, Any],
    history: list[dict[str, Any]],
    point_rate: float,
) -> price_watch.webapi.schemas.StoreEntry:
    """ストアエントリを構築."""
    current_price = latest["price"]  # None の場合がある
    effective_price = _calc_effective_price(current_price, point_rate)

    return price_watch.webapi.schemas.StoreEntry(
        item_key=item["item_key"],
        store=item["store"],
        url=item.get("url"),
        current_price=current_price,
        effective_price=effective_price,
        point_rate=point_rate,
        lowest_price=stats["lowest_price"],
        highest_price=stats["highest_price"],
        stock=latest["stock"],
        last_updated=latest["time"],
        history=_build_history_entries(history, point_rate),
        product_url=item.get("url"),  # メルカリの場合は最安商品URL
        search_keyword=item.get("search_keyword"),
    )


def _find_best_store(
    stores: list[price_watch.webapi.schemas.StoreEntry],
) -> price_watch.webapi.schemas.StoreEntry:
    """最安ストアを決定（在庫ありの中で effective_price が最小）.

    effective_price が None の場合は最後に配置する。
    """
    in_stock_stores = [s for s in stores if s.stock > 0 and s.effective_price is not None]
    if in_stock_stores:
        return min(in_stock_stores, key=lambda s: s.effective_price or 0)
    # 在庫なし、または全て価格なしの場合は effective_price が有効なものを優先
    stores_with_price = [s for s in stores if s.effective_price is not None]
    if stores_with_price:
        return min(stores_with_price, key=lambda s: s.effective_price or 0)
    # 全て価格なしの場合は最初のストアを返す
    return stores[0]


def _find_first_thumb_url(store_data_list: list[dict[str, Any]]) -> str | None:
    """最初に見つかったサムネイルURLを取得."""
    for sd in store_data_list:
        if sd["thumb_url"]:
            return sd["thumb_url"]
    return None


def _build_result_item(
    name: str, store_data_list: list[dict[str, Any]]
) -> price_watch.webapi.schemas.ResultItem:
    """グルーピングされたアイテムから結果アイテムを構築."""
    stores = [sd["store_entry"] for sd in store_data_list]
    best_store_entry = _find_best_store(stores)
    thumb_url = _find_first_thumb_url(store_data_list)

    return price_watch.webapi.schemas.ResultItem(
        name=name,
        thumb_url=thumb_url,
        stores=stores,
        best_store=best_store_entry.store,
        best_effective_price=best_store_entry.effective_price,
    )


def _get_store_definitions(
    target_config: price_watch.target.TargetConfig | None,
) -> list[price_watch.webapi.schemas.StoreDefinition]:
    """ストア定義を生成."""
    if not target_config:
        return []
    return [
        price_watch.webapi.schemas.StoreDefinition(
            name=store.name, point_rate=store.point_rate, color=store.color
        )
        for store in target_config.stores
    ]


def _build_store_entry_without_history(
    item: dict[str, Any],
    point_rate: float,
) -> price_watch.webapi.schemas.StoreEntry:
    """履歴がないアイテム用のストアエントリを構築."""
    return price_watch.webapi.schemas.StoreEntry(
        item_key=item.get("item_key", ""),
        store=item["store"],
        url=item.get("url"),
        current_price=None,  # 価格未取得
        effective_price=None,  # 価格未取得
        point_rate=point_rate,
        lowest_price=None,
        highest_price=None,
        stock=0,  # 履歴がない = まだ在庫確認できていない
        last_updated="",
        history=[],
        product_url=item.get("url"),
        search_keyword=item.get("search_keyword"),
    )


def _process_item(
    item: dict[str, Any],
    days: int | None,
    target_config: price_watch.target.TargetConfig | None,
) -> dict[str, Any] | None:
    """1つのアイテムを処理してストアデータを構築."""
    # ポイント還元率を取得
    point_rate = _get_point_rate(target_config, item["store"])

    # item に id がない場合（target.yaml のみにあるアイテム）
    if "id" not in item:
        store_entry = _build_store_entry_without_history(item, point_rate)
        return {
            "store_entry": store_entry,
            "thumb_url": item.get("thumb_url"),
        }

    # 最新価格を取得
    latest = price_watch.history.get_latest_price(item["id"])
    if not latest:
        # 履歴がないアイテムも表示（在庫なしとして）
        store_entry = _build_store_entry_without_history(item, point_rate)
        return {
            "store_entry": store_entry,
            "thumb_url": item.get("thumb_url"),
        }

    # 統計情報を取得
    stats = price_watch.history.get_item_stats(item["id"], days)

    # 価格履歴を取得
    _, hist = price_watch.history.get_item_history(item["item_key"], days)

    store_entry = _build_store_entry(item, latest, stats, hist, point_rate)

    return {
        "store_entry": store_entry,
        "thumb_url": item["thumb_url"],
    }


def _group_items_by_name(
    all_items: list[dict[str, Any]],
    target_item_keys: set[str],
    days: int | None,
    target_config: price_watch.target.TargetConfig | None,
) -> dict[str, list[dict[str, Any]]]:
    """アイテムを名前でグルーピング."""
    items_by_name: dict[str, list[dict[str, Any]]] = {}
    processed_keys: set[str] = set()

    # DBにあるアイテムを処理
    for item in all_items:
        # target.yaml に含まれないアイテムはスキップ
        if target_item_keys and item["item_key"] not in target_item_keys:
            continue

        store_data = _process_item(item, days, target_config)
        if not store_data:
            continue

        item_name = item["name"]
        if item_name not in items_by_name:
            items_by_name[item_name] = []
        items_by_name[item_name].append(store_data)
        processed_keys.add(item["item_key"])

    # target.yaml にあるがDBにないアイテムを追加
    if target_config:
        try:
            resolved_items_list = target_config.resolve_items()
        except Exception:
            logging.warning("Failed to resolve target items in _group_items_by_name")
            resolved_items_list = []

        for resolved_item in resolved_items_list:
            # メルカリ検索の場合の item_key を生成
            if resolved_item.check_method == price_watch.target.CheckMethod.MERCARI_SEARCH:
                keyword = resolved_item.search_keyword or resolved_item.name
                item_key = price_watch.history.generate_item_key(search_keyword=keyword, search_cond="")
            else:
                item_key = price_watch.history.url_hash(resolved_item.url)

            if item_key in processed_keys:
                continue

            # target.yaml のアイテムを dict 形式に変換
            item_dict: dict[str, Any] = {
                "name": resolved_item.name,
                "store": resolved_item.store,
                "url": resolved_item.url if resolved_item.url else None,
                "item_key": item_key,
                "thumb_url": getattr(resolved_item, "thumb_url", None),
            }

            # メルカリ検索用フィールドを追加
            if resolved_item.check_method == price_watch.target.CheckMethod.MERCARI_SEARCH:
                item_dict["search_keyword"] = resolved_item.search_keyword or resolved_item.name

            store_data = _process_item(item_dict, days, target_config)
            if not store_data:
                continue

            item_name = resolved_item.name
            if item_name not in items_by_name:
                items_by_name[item_name] = []
            items_by_name[item_name].append(store_data)

    return items_by_name


@blueprint.route("/api/items")
@validate()
def get_items(
    query: price_watch.webapi.schemas.ItemsQueryParams,
) -> flask.Response | tuple[flask.Response, int]:
    """アイテム一覧を取得（複数ストア対応・実質価格付き）."""
    try:
        days = _parse_days(query.days)

        # target.yaml の設定を取得（キャッシュ使用）
        target_config = _get_target_config()
        target_item_keys = _get_target_item_keys(target_config)

        all_items = price_watch.history.get_all_items()

        # アイテム名でグルーピング
        items_by_name = _group_items_by_name(all_items, target_item_keys, days, target_config)

        # グルーピングされたアイテムを構築
        result_items = [
            _build_result_item(name, store_data_list) for name, store_data_list in items_by_name.items()
        ]

        response = price_watch.webapi.schemas.ItemsResponse(
            items=result_items,
            store_definitions=_get_store_definitions(target_config),
        )

        return flask.jsonify(response.model_dump())

    except Exception:
        logging.exception("Error getting items")
        error = price_watch.webapi.schemas.ErrorResponse(error="Internal server error")
        return flask.jsonify(error.model_dump()), 500


@blueprint.route("/thumb/<filename>")
def serve_thumb(filename: str) -> flask.Response:
    """サムネイル画像を配信."""
    # セキュリティチェック: ファイル名が正当な形式か確認
    if not filename.endswith(".png") or "/" in filename or "\\" in filename:
        return flask.Response("Not found", status=404)

    thumb_file = price_watch.thumbnail.get_thumb_dir() / filename
    if not thumb_file.exists():
        return flask.Response("Not found", status=404)

    return flask.send_file(
        thumb_file,
        mimetype="image/png",
        max_age=86400,  # 24時間キャッシュ
    )


@blueprint.route("/api/items/<item_key>/history")
@validate()
def get_item_history(
    item_key: str, query: price_watch.webapi.schemas.HistoryQueryParams
) -> flask.Response | tuple[flask.Response, int]:
    """アイテム別価格履歴を取得."""
    try:
        days = _parse_days(query.days)

        item, hist = price_watch.history.get_item_history(item_key, days)

        if item is None:
            error = price_watch.webapi.schemas.ErrorResponse(error="Item not found")
            return flask.jsonify(error.model_dump()), 404

        # ポイント還元率を取得（キャッシュ使用）
        target_config = _get_target_config()
        point_rate = _get_point_rate(target_config, item["store"])

        # 履歴を構築（effective_price 付き）
        formatted_history = _build_history_entries(hist, point_rate)

        response = price_watch.webapi.schemas.HistoryResponse(history=formatted_history)
        return flask.jsonify(response.model_dump())

    except Exception:
        logging.exception("Error getting item history")
        error = price_watch.webapi.schemas.ErrorResponse(error="Internal server error")
        return flask.jsonify(error.model_dump()), 500


@blueprint.route("/api/items/<item_key>/events")
def get_item_events(item_key: str) -> flask.Response | tuple[flask.Response, int]:
    """アイテム別イベント履歴を取得."""
    try:
        limit = flask.request.args.get("limit", 50, type=int)
        # 上限を設定
        if limit > 100:
            limit = 100
        if limit < 1:
            limit = 1

        events = price_watch.history.get_item_events(item_key, limit)

        if not events:
            # アイテムが存在しない場合も空リストを返す（404 ではなく）
            return flask.jsonify({"events": []})

        # イベントにメッセージを追加
        formatted_events = []
        for evt in events:
            formatted_event = {
                "id": evt["id"],
                "item_name": evt["item_name"],
                "store": evt["store"],
                "url": evt["url"],
                "thumb_url": evt["thumb_url"],
                "event_type": evt["event_type"],
                "price": evt["price"],
                "old_price": evt["old_price"],
                "threshold_days": evt["threshold_days"],
                "created_at": evt["created_at"],
                "message": price_watch.event.format_event_message(evt),
                "title": price_watch.event.format_event_title(evt["event_type"]),
            }
            formatted_events.append(formatted_event)

        return flask.jsonify({"events": formatted_events})

    except Exception:
        logging.exception("Error getting item events")
        error = price_watch.webapi.schemas.ErrorResponse(error="Internal server error")
        return flask.jsonify(error.model_dump()), 500


@blueprint.route("/api/events")
def get_events() -> flask.Response | tuple[flask.Response, int]:
    """最新イベント一覧を取得."""
    try:
        limit = flask.request.args.get("limit", 10, type=int)
        # 上限を設定
        if limit > 100:
            limit = 100
        if limit < 1:
            limit = 1

        events = price_watch.event.get_recent_events(limit)

        # イベントにメッセージを追加
        formatted_events = []
        for evt in events:
            formatted_event = {
                "id": evt["id"],
                "item_name": evt["item_name"],
                "store": evt["store"],
                "url": evt["url"],
                "thumb_url": evt["thumb_url"],
                "event_type": evt["event_type"],
                "price": evt["price"],
                "old_price": evt["old_price"],
                "threshold_days": evt["threshold_days"],
                "created_at": evt["created_at"],
                "message": price_watch.event.format_event_message(evt),
                "title": price_watch.event.format_event_title(evt["event_type"]),
            }
            formatted_events.append(formatted_event)

        return flask.jsonify({"events": formatted_events})

    except Exception:
        logging.exception("Error getting events")
        error = price_watch.webapi.schemas.ErrorResponse(error="Internal server error")
        return flask.jsonify(error.model_dump()), 500
