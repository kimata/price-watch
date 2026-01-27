#!/usr/bin/env python3
"""API エンドポイント."""

import logging
import pathlib
from typing import Any

import flask
from flask_pydantic import validate

import price_watch.config
import price_watch.event
import price_watch.file_cache
import price_watch.managers.history
import price_watch.metrics
import price_watch.models
import price_watch.target
import price_watch.thumbnail
import price_watch.webapi.ogp
import price_watch.webapi.schemas
from price_watch.managers import HistoryManager

blueprint = flask.Blueprint("page", __name__)

# HistoryManager のキャッシュ（遅延初期化）
_history_manager: HistoryManager | None = None


def _get_history_manager() -> HistoryManager:
    """HistoryManager を取得（遅延初期化）."""
    global _history_manager
    if _history_manager is not None:
        return _history_manager
    config = _get_app_config()
    if config is None:
        msg = f"App config not available (config path: {_config_cache.file_path}, cwd: {pathlib.Path.cwd()})"
        raise RuntimeError(msg)
    logging.debug("Initializing HistoryManager with data path: %s", config.data.price)
    manager = price_watch.managers.history.HistoryManager.create(config.data.price)
    manager.initialize()
    _history_manager = manager
    return _history_manager


# target.yaml のキャッシュ（ファイル更新時刻が変わった場合のみ再読み込み）
_target_config_cache: price_watch.file_cache.FileCache[price_watch.target.TargetConfig] = (
    price_watch.file_cache.FileCache(
        price_watch.target.TARGET_FILE_PATH,
        lambda path: price_watch.target.load(path),
    )
)

# config.yaml のキャッシュ
_config_cache: price_watch.file_cache.FileCache[price_watch.config.AppConfig] = (
    price_watch.file_cache.FileCache(
        price_watch.config.CONFIG_FILE_PATH,
        lambda path: price_watch.config.load(path),
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
        # 検索系ストアの場合は keyword から item_key を生成
        if item.check_method in price_watch.target.SEARCH_CHECK_METHODS:
            keyword = item.search_keyword or item.name
            keys.add(price_watch.managers.history.generate_item_key(search_keyword=keyword, search_cond=""))
        else:
            keys.add(price_watch.managers.history.url_hash(item.url))
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


def _get_price_unit(target_config: price_watch.target.TargetConfig | None, store_name: str) -> str:
    """ストアの価格通貨単位を取得."""
    if target_config is None:
        return "円"
    store = target_config.get_store(store_name)
    return store.price_unit if store else "円"


def _calc_effective_price(price: int | None, point_rate: float) -> int | None:
    """実質価格を計算（ポイント還元考慮）.

    price が None の場合は None を返す。
    """
    if price is None:
        return None
    return int(price * (1 - point_rate / 100))


def _build_history_entries(
    history: list[price_watch.models.PriceRecord], point_rate: float
) -> list[price_watch.webapi.schemas.PriceHistoryPoint]:
    """履歴エントリリストを構築.

    price が None の場合（在庫なし）も含めて返す。
    """
    return [
        price_watch.webapi.schemas.PriceHistoryPoint(
            time=h.time,
            price=h.price,
            effective_price=_calc_effective_price(h.price, point_rate),
            stock=h.stock,
        )
        for h in history
    ]


def _build_store_entry(
    item: price_watch.models.ItemRecord,
    latest: price_watch.models.LatestPriceRecord,
    stats: price_watch.models.ItemStats,
    history: list[price_watch.models.PriceRecord],
    point_rate: float,
    price_unit: str,
    *,
    include_history: bool = True,
) -> price_watch.webapi.schemas.StoreEntry:
    """ストアエントリを構築.

    Args:
        item: アイテムレコード
        latest: 最新価格レコード
        stats: 統計情報
        history: 価格履歴
        point_rate: ポイント還元率
        price_unit: 価格通貨単位
        include_history: 履歴を含めるかどうか（軽量API用）
    """
    current_price = latest.price  # None の場合がある
    effective_price = _calc_effective_price(current_price, point_rate)

    return price_watch.webapi.schemas.StoreEntry(
        item_key=item.item_key,
        store=item.store,
        url=item.url,
        current_price=current_price,
        effective_price=effective_price,
        point_rate=point_rate,
        lowest_price=stats.lowest_price,
        highest_price=stats.highest_price,
        stock=latest.stock,
        last_updated=latest.time,
        history=_build_history_entries(history, point_rate) if include_history else [],
        product_url=item.url,  # メルカリの場合は最安商品URL
        search_keyword=item.search_keyword,
        price_unit=price_unit,
    )


def _find_best_store(
    stores: list[price_watch.webapi.schemas.StoreEntry],
) -> price_watch.webapi.schemas.StoreEntry:
    """最安ストアを決定（在庫ありの中で effective_price が最小）.

    effective_price が None の場合は最後に配置する。
    """
    in_stock_stores = [
        s for s in stores if s.stock is not None and s.stock > 0 and s.effective_price is not None
    ]
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
            name=store.name,
            point_rate=store.point_rate,
            color=store.color,
            price_unit=store.price_unit,
        )
        for store in target_config.stores
    ]


def _build_store_entry_without_history_from_record(
    item: price_watch.models.ItemRecord,
    point_rate: float,
    price_unit: str,
) -> price_watch.webapi.schemas.StoreEntry:
    """履歴がないアイテム用のストアエントリを構築（ItemRecord版）."""
    return price_watch.webapi.schemas.StoreEntry(
        item_key=item.item_key,
        store=item.store,
        url=item.url,
        current_price=None,  # 価格未取得
        effective_price=None,  # 価格未取得
        point_rate=point_rate,
        lowest_price=None,
        highest_price=None,
        stock=0,  # 履歴がない = まだ在庫確認できていない
        last_updated="",
        history=[],
        product_url=item.url,
        search_keyword=item.search_keyword,
        price_unit=price_unit,
    )


def _process_item(
    item: price_watch.models.ItemRecord,
    days: int | None,
    target_config: price_watch.target.TargetConfig | None,
    *,
    include_history: bool = True,
) -> dict[str, Any] | None:
    """1つのアイテムを処理してストアデータを構築.

    Args:
        item: アイテムレコード
        days: 期間（日数）
        target_config: ターゲット設定
        include_history: 履歴を含めるかどうか（軽量API用にFalseを指定）
    """
    history = _get_history_manager()

    # ポイント還元率と通貨単位を取得
    point_rate = _get_point_rate(target_config, item.store)
    price_unit = _get_price_unit(target_config, item.store)

    # 最新価格を取得
    latest = history.get_latest(item.id)
    if not latest:
        # 履歴がないアイテムも表示（在庫なしとして）
        store_entry = _build_store_entry_without_history_from_record(item, point_rate, price_unit)
        return {
            "store_entry": store_entry,
            "thumb_url": item.thumb_url,
        }

    # 統計情報を取得
    stats = history.get_stats(item.id, days)

    # 価格履歴を取得（include_history=False の場合はスキップ）
    hist: list[price_watch.models.PriceRecord] = []
    if include_history:
        _, hist = history.get_history(item.item_key, days)

    store_entry = _build_store_entry(
        item, latest, stats, hist, point_rate, price_unit, include_history=include_history
    )

    return {
        "store_entry": store_entry,
        "thumb_url": item.thumb_url,
    }


def _collect_stores_for_name(
    item_name: str,
    all_items: list[price_watch.models.ItemRecord],
    target_item_keys: set[str],
    days: int | None,
    target_config: price_watch.target.TargetConfig | None,
    *,
    include_history: bool = True,
) -> list[dict[str, Any]]:
    """指定されたアイテム名に対応する全ストアのデータを収集."""
    store_data_list: list[dict[str, Any]] = []
    for item in all_items:
        if item.name != item_name:
            continue
        if target_item_keys and item.item_key not in target_item_keys:
            continue
        store_data = _process_item(item, days, target_config, include_history=include_history)
        if store_data:
            store_data_list.append(store_data)
    return store_data_list


def _group_items_by_name(
    all_items: list[price_watch.models.ItemRecord],
    target_item_keys: set[str],
    days: int | None,
    target_config: price_watch.target.TargetConfig | None,
    *,
    include_history: bool = True,
) -> dict[str, list[dict[str, Any]]]:
    """アイテムを名前でグルーピング.

    Args:
        all_items: 全アイテムレコード
        target_item_keys: 監視対象アイテムキーのセット
        days: 期間（日数）
        target_config: ターゲット設定
        include_history: 履歴を含めるかどうか（軽量API用にFalseを指定）
    """
    items_by_name: dict[str, list[dict[str, Any]]] = {}
    processed_keys: set[str] = set()

    # DBにあるアイテムを名前でグルーピングして処理
    seen_names: set[str] = set()
    for item in all_items:
        if target_item_keys and item.item_key not in target_item_keys:
            continue
        if item.name in seen_names:
            continue
        seen_names.add(item.name)

        store_data_list = _collect_stores_for_name(
            item.name,
            all_items,
            target_item_keys,
            days,
            target_config,
            include_history=include_history,
        )
        if store_data_list:
            items_by_name[item.name] = store_data_list
            for sd in store_data_list:
                processed_keys.add(sd["store_entry"].item_key)

    # target.yaml にあるがDBにないアイテムを追加
    if target_config:
        try:
            resolved_items_list = target_config.resolve_items()
        except Exception:
            logging.warning("Failed to resolve target items in _group_items_by_name")
            resolved_items_list = []

        for resolved_item in resolved_items_list:
            # 検索系ストアの場合の item_key を生成
            if resolved_item.check_method in price_watch.target.SEARCH_CHECK_METHODS:
                keyword = resolved_item.search_keyword or resolved_item.name
                item_key = price_watch.managers.history.generate_item_key(
                    search_keyword=keyword, search_cond=""
                )
            else:
                item_key = price_watch.managers.history.url_hash(resolved_item.url)

            if item_key in processed_keys:
                continue

            # target.yaml のアイテムを ItemRecord 形式に変換（DBにないので id=0）
            item_record = price_watch.models.ItemRecord(
                id=0,
                item_key=item_key,
                url=resolved_item.url if resolved_item.url else None,
                name=resolved_item.name,
                store=resolved_item.store,
                thumb_url=getattr(resolved_item, "thumb_url", None),
                search_keyword=(
                    resolved_item.search_keyword or resolved_item.name
                    if resolved_item.check_method in price_watch.target.SEARCH_CHECK_METHODS
                    else None
                ),
            )

            store_data = _process_item_without_db(item_record, target_config)
            if not store_data:
                continue

            item_name = resolved_item.name
            if item_name not in items_by_name:
                items_by_name[item_name] = []
            items_by_name[item_name].append(store_data)

    return items_by_name


def _process_item_without_db(
    item: price_watch.models.ItemRecord,
    target_config: price_watch.target.TargetConfig | None,
) -> dict[str, Any] | None:
    """DB に存在しないアイテムを処理してストアデータを構築."""
    # ポイント還元率と通貨単位を取得
    point_rate = _get_point_rate(target_config, item.store)
    price_unit = _get_price_unit(target_config, item.store)

    # 履歴がないアイテムとして表示
    store_entry = _build_store_entry_without_history_from_record(item, point_rate, price_unit)
    return {
        "store_entry": store_entry,
        "thumb_url": item.thumb_url,
    }


@blueprint.route("/api/items")
@validate()
def get_items(
    query: price_watch.webapi.schemas.ItemsQueryParams,
) -> flask.Response | tuple[flask.Response, int]:
    """アイテム一覧を取得（複数ストア対応・実質価格付き）.

    履歴データはペイロード削減のため含まれません。
    履歴が必要な場合は /api/items/<item_key>/history を使用してください。
    """
    try:
        days = _parse_days(query.days)

        # target.yaml の設定を取得（キャッシュ使用）
        target_config = _get_target_config()
        target_item_keys = _get_target_item_keys(target_config)

        all_items = _get_history_manager().get_all_items()

        # アイテム名でグルーピング（履歴なしで軽量化）
        items_by_name = _group_items_by_name(
            all_items, target_item_keys, days, target_config, include_history=False
        )

        # グルーピングされたアイテムを構築
        result_items = [
            _build_result_item(name, store_data_list) for name, store_data_list in items_by_name.items()
        ]

        response = price_watch.webapi.schemas.ItemsResponse(
            items=result_items,
            store_definitions=_get_store_definitions(target_config),
        )

        return flask.jsonify(response.model_dump())

    except Exception as e:
        logging.exception("Error getting items")
        # デバッグ用にエラー詳細を含める（CI でエラー原因を特定するため）
        error_detail = f"Internal server error: {type(e).__name__}: {e}"
        error = price_watch.webapi.schemas.ErrorResponse(error=error_detail)
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

        item, hist = _get_history_manager().get_history(item_key, days)

        if item is None:
            error = price_watch.webapi.schemas.ErrorResponse(error="Item not found")
            return flask.jsonify(error.model_dump()), 404

        # ポイント還元率を取得（キャッシュ使用）
        target_config = _get_target_config()
        point_rate = _get_point_rate(target_config, item.store)

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

        events = _get_history_manager().get_item_events(item_key, limit)

        if not events:
            # アイテムが存在しない場合も空リストを返す（404 ではなく）
            return flask.jsonify({"events": []})

        # イベントにメッセージを追加
        formatted_events = []
        for evt in events:
            formatted_event = {
                "id": evt.id,
                "item_name": evt.item_name,
                "store": evt.store,
                "url": evt.url,
                "thumb_url": evt.thumb_url,
                "event_type": evt.event_type,
                "price": evt.price,
                "old_price": evt.old_price,
                "threshold_days": evt.threshold_days,
                "created_at": evt.created_at,
                "message": price_watch.event.format_event_message(evt),
                "title": price_watch.event.format_event_title(evt.event_type),
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

        events = _get_history_manager().get_recent_events(limit)

        # イベントにメッセージを追加
        formatted_events = []
        for evt in events:
            formatted_event = {
                "id": evt.id,
                "item_name": evt.item_name,
                "store": evt.store,
                "url": evt.url,
                "thumb_url": evt.thumb_url,
                "event_type": evt.event_type,
                "price": evt.price,
                "old_price": evt.old_price,
                "threshold_days": evt.threshold_days,
                "created_at": evt.created_at,
                "message": price_watch.event.format_event_message(evt),
                "title": price_watch.event.format_event_title(evt.event_type),
            }
            formatted_events.append(formatted_event)

        return flask.jsonify({"events": formatted_events})

    except Exception:
        logging.exception("Error getting events")
        error = price_watch.webapi.schemas.ErrorResponse(error="Internal server error")
        return flask.jsonify(error.model_dump()), 500


def _get_app_config() -> price_watch.config.AppConfig | None:
    """config.yaml の設定を取得（キャッシュ使用）."""
    try:
        config = _config_cache.get()
        if config is None:
            logging.warning(
                "config.yaml not found at path: %s (cwd: %s)",
                _config_cache.file_path,
                pathlib.Path.cwd(),
            )
        return config
    except Exception:
        logging.exception("Failed to load config.yaml from %s", _config_cache.file_path)
        return None


def _build_ogp_data(
    item_name: str,
    stores: list[price_watch.webapi.schemas.StoreEntry],
    target_config: price_watch.target.TargetConfig | None,
    thumb_dir: pathlib.Path,
) -> price_watch.webapi.ogp.OgpData:
    """OGP 用データを構築."""
    # 最安ストアを特定
    best_store = _find_best_store(stores)

    # 全ストアの最安値を取得
    all_lowest = [s.lowest_price for s in stores if s.lowest_price is not None]
    lowest_price = min(all_lowest) if all_lowest else None

    # サムネイルパスを取得（item_name から生成されたハッシュファイル名を使用）
    thumb_path: pathlib.Path | None = None
    thumb_filename = price_watch.thumbnail.get_thumb_filename(item_name)
    potential_path = thumb_dir / thumb_filename
    if potential_path.exists():
        thumb_path = potential_path

    # ストアごとの履歴を構築
    store_histories: list[price_watch.webapi.ogp.StoreHistory] = []
    for i, s in enumerate(stores):
        # ストアの色を取得
        color = price_watch.webapi.ogp.DEFAULT_COLORS[i % len(price_watch.webapi.ogp.DEFAULT_COLORS)]
        if target_config:
            store_def = target_config.get_store(s.store)
            if store_def and store_def.color:
                color = store_def.color

        # 履歴を変換
        history = [
            {"time": h.time, "price": h.price, "effective_price": h.effective_price} for h in s.history
        ]

        store_histories.append(
            price_watch.webapi.ogp.StoreHistory(
                store_name=s.store,
                color=color,
                history=history,
            )
        )

    return price_watch.webapi.ogp.OgpData(
        item_name=item_name,
        best_price=best_store.effective_price,
        best_store=best_store.store,
        lowest_price=lowest_price,
        thumb_path=thumb_path,
        store_histories=store_histories,
    )


def _get_item_data_for_ogp(
    item_key: str,
    days: int | None = 30,
) -> tuple[str | None, list[price_watch.webapi.schemas.StoreEntry]]:
    """OGP 用のアイテムデータを取得.

    item_key からアイテム名を特定し、同名の全ストアのデータを返す。

    Returns:
        (アイテム名, ストアエントリリスト) のタプル。アイテムが見つからない場合は (None, [])
    """
    target_config = _get_target_config()
    all_items = _get_history_manager().get_all_items()

    # item_key からアイテム名を特定
    primary = next((item for item in all_items if item.item_key == item_key), None)
    if primary is None:
        return None, []

    item_name = primary.name
    target_item_keys = _get_target_item_keys(target_config)

    # 同名の全ストアのデータを収集
    store_data_list = _collect_stores_for_name(
        item_name,
        all_items,
        target_item_keys,
        days,
        target_config,
        include_history=True,
    )

    stores = [sd["store_entry"] for sd in store_data_list]
    return item_name, stores


def _is_facebook_crawler(user_agent: str) -> bool:
    """Facebook クローラーかどうかを判定."""
    return "facebookexternalhit" in user_agent.lower()


def _render_ogp_html(
    item_key: str,
    item_name: str,
    best_store: price_watch.webapi.schemas.StoreEntry,
    ogp_image_url: str,
    ogp_image_square_url: str,
    page_url: str,
    static_dir: pathlib.Path | None,
    *,
    is_facebook: bool = False,
) -> str:
    """OGP メタタグ付き HTML を生成.

    ビルド済みの index.html をベースに、OGP メタタグを挿入する。

    Args:
        item_key: アイテムキー
        item_name: アイテム名
        best_store: 最安ストア情報
        ogp_image_url: OGP 画像 URL（1200x630、Facebook 用）
        ogp_image_square_url: 正方形 OGP 画像 URL（1200x1200、LINE/はてな/Twitter 用）
        page_url: ページ URL
        static_dir: 静的ファイルディレクトリ
        is_facebook: Facebook クローラーからのアクセスかどうか
    """
    # 価格のフォーマット
    price_text = f"¥{best_store.effective_price:,}" if best_store.effective_price else "価格未取得"
    description = f"最安値: {price_text} ({best_store.store})"

    # og:image の URL を決定（Facebook は横長、それ以外は正方形）
    og_image_url = ogp_image_url if is_facebook else ogp_image_square_url

    # OGP メタタグ
    ogp_tags = f"""
    <!-- OGP メタタグ -->
    <meta property="og:title" content="{_escape_html(item_name)}">
    <meta property="og:description" content="{_escape_html(description)}">
    <meta property="og:image" content="{_escape_html(og_image_url)}">
    <meta property="og:url" content="{_escape_html(page_url)}">
    <meta property="og:type" content="product">
    <meta property="og:site_name" content="Price Watch">

    <!-- Twitter Card（正方形画像を使用） -->
    <meta name="twitter:card" content="summary">
    <meta name="twitter:title" content="{_escape_html(item_name)}">
    <meta name="twitter:description" content="{_escape_html(description)}">
    <meta name="twitter:image" content="{_escape_html(ogp_image_square_url)}">
"""

    # item_key を渡すスクリプト
    item_key_script = f"""
    <script>
        // React アプリに item_key を渡す
        window.__ITEM_KEY__ = "{_escape_js(item_key)}";
    </script>
"""

    # ビルド済み index.html を読み込む
    index_html = None
    if static_dir and (static_dir / "index.html").exists():
        try:
            index_html = (static_dir / "index.html").read_text(encoding="utf-8")
        except Exception:
            logging.warning("Failed to read index.html")

    if index_html:
        # タイトルを更新
        index_html = index_html.replace(
            "<title>Price Watch</title>",
            f"<title>{_escape_html(item_name)} - Price Watch</title>",
        )
        # </head> の前に OGP タグを挿入
        index_html = index_html.replace("</head>", ogp_tags + "</head>")
        # <div id="root"></div> の前に item_key スクリプトを挿入
        index_html = index_html.replace(
            '<div id="root"></div>',
            item_key_script + '<div id="root"></div>',
        )
        return index_html

    # フォールバック: 最小限の HTML を生成
    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{_escape_html(item_name)} - Price Watch</title>
    {ogp_tags}
    <link rel="icon" type="image/svg+xml" href="/price/favicon.svg">
</head>
<body>
    {item_key_script}
    <div id="root">
        <p>フロントエンド未ビルド: <code>cd frontend && npm run build</code></p>
    </div>
</body>
</html>"""


def _escape_html(text: str) -> str:
    """HTML エスケープ."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#x27;")
    )


def _escape_js(text: str) -> str:
    """JavaScript 文字列エスケープ."""
    return text.replace("\\", "\\\\").replace('"', '\\"').replace("'", "\\'").replace("\n", "\\n")


@blueprint.route("/items/<item_key>")
def item_detail_page(item_key: str) -> flask.Response | tuple[flask.Response, int]:
    """アイテム詳細ページ（OGP メタタグ付き）."""
    try:
        # アイテムデータを取得
        item_name, stores = _get_item_data_for_ogp(item_key)

        if item_name is None or not stores:
            return flask.Response("Item not found", status=404)

        # 最安ストアを特定
        best_store = _find_best_store(stores)

        # URL を構築
        base_url = flask.request.url_root.rstrip("/")
        page_url = flask.request.url
        ogp_image_url = f"{base_url}/price/ogp/{item_key}.png"
        ogp_image_square_url = f"{base_url}/price/ogp/{item_key}_square.png"

        # User-Agent から Facebook クローラーかどうかを判定
        user_agent = flask.request.headers.get("User-Agent", "")
        is_facebook = _is_facebook_crawler(user_agent)

        # 設定からstatic_dirを取得
        app_config = _get_app_config()
        static_dir = app_config.webapp.static_dir_path if app_config else None

        # HTML を生成
        html = _render_ogp_html(
            item_key,
            item_name,
            best_store,
            ogp_image_url,
            ogp_image_square_url,
            page_url,
            static_dir,
            is_facebook=is_facebook,
        )

        return flask.Response(html, mimetype="text/html")

    except Exception:
        logging.exception("Error rendering item detail page")
        return flask.Response("Internal server error", status=500)


@blueprint.route("/ogp/<item_key>.png")
def ogp_image(item_key: str) -> flask.Response:
    """OGP 画像を配信."""
    try:
        # 設定を取得
        app_config = _get_app_config()
        if app_config is None:
            return flask.Response("Configuration not found", status=500)

        cache_dir = app_config.data.cache
        thumb_dir = app_config.data.thumb

        # フォント設定を取得
        font_paths = price_watch.webapi.ogp.FontPaths.from_config(app_config.font)

        # アイテムデータを取得
        item_name, stores = _get_item_data_for_ogp(item_key)

        if item_name is None or not stores:
            return flask.Response("Item not found", status=404)

        # target.yaml の設定を取得
        target_config = _get_target_config()

        # OGP データを構築
        ogp_data = _build_ogp_data(item_name, stores, target_config, thumb_dir)

        # 画像を生成/キャッシュから取得
        image_path = price_watch.webapi.ogp.get_or_generate_ogp_image(
            item_key,
            ogp_data,
            cache_dir,
            font_paths=font_paths,
        )

        return flask.send_file(
            image_path,
            mimetype="image/png",
            max_age=3600,  # 1時間キャッシュ
        )

    except Exception:
        logging.exception("Error generating OGP image")
        return flask.Response("Internal server error", status=500)


@blueprint.route("/ogp/<item_key>_square.png")
def ogp_image_square(item_key: str) -> flask.Response:
    """正方形 OGP 画像を配信."""
    try:
        # 設定を取得
        app_config = _get_app_config()
        if app_config is None:
            return flask.Response("Configuration not found", status=500)

        cache_dir = app_config.data.cache
        thumb_dir = app_config.data.thumb

        # フォント設定を取得
        font_paths = price_watch.webapi.ogp.FontPaths.from_config(app_config.font)

        # アイテムデータを取得
        item_name, stores = _get_item_data_for_ogp(item_key)

        if item_name is None or not stores:
            return flask.Response("Item not found", status=404)

        # target.yaml の設定を取得
        target_config = _get_target_config()

        # OGP データを構築
        ogp_data = _build_ogp_data(item_name, stores, target_config, thumb_dir)

        # 正方形画像を生成/キャッシュから取得
        image_path = price_watch.webapi.ogp.get_or_generate_ogp_image_square(
            item_key,
            ogp_data,
            cache_dir,
            font_paths=font_paths,
        )

        return flask.send_file(
            image_path,
            mimetype="image/png",
            max_age=3600,  # 1時間キャッシュ
        )

    except Exception:
        logging.exception("Error generating square OGP image")
        return flask.Response("Internal server error", status=500)


def _render_top_page_html(static_dir: pathlib.Path | None) -> str:
    """トップページ用の OGP メタタグ付き HTML を生成."""
    title = "Price Watch"
    description = (
        "複数のオンラインショップから商品価格を自動収集。価格変動や在庫復活をリアルタイムで通知します。"
    )

    # OGP メタタグ
    ogp_tags = f"""
    <!-- OGP メタタグ -->
    <meta property="og:title" content="{_escape_html(title)}">
    <meta property="og:description" content="{_escape_html(description)}">
    <meta property="og:type" content="website">
    <meta property="og:site_name" content="Price Watch">
    <meta name="description" content="{_escape_html(description)}">

    <!-- Twitter Card -->
    <meta name="twitter:card" content="summary">
    <meta name="twitter:title" content="{_escape_html(title)}">
    <meta name="twitter:description" content="{_escape_html(description)}">
"""

    # ビルド済み index.html を読み込む
    index_html = None
    if static_dir and (static_dir / "index.html").exists():
        try:
            index_html = (static_dir / "index.html").read_text(encoding="utf-8")
        except Exception:
            logging.warning("Failed to read index.html")

    if index_html:
        # </head> の前に OGP タグを挿入
        index_html = index_html.replace("</head>", ogp_tags + "</head>")
        return index_html

    # フォールバック: 最小限の HTML を生成
    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{_escape_html(title)}</title>
    {ogp_tags}
    <link rel="icon" type="image/svg+xml" href="/price/favicon.svg">
</head>
<body>
    <div id="root">
        <p>フロントエンド未ビルド: <code>cd frontend && npm run build</code></p>
    </div>
</body>
</html>"""


@blueprint.route("/")
def top_page() -> flask.Response:
    """トップページ（OGP メタタグ付き）."""
    try:
        # 設定からstatic_dirを取得
        app_config = _get_app_config()
        static_dir = app_config.webapp.static_dir_path if app_config else None

        # HTML を生成
        html = _render_top_page_html(static_dir)

        return flask.Response(html, mimetype="text/html")

    except Exception:
        logging.exception("Error rendering top page")
        return flask.Response("Internal server error", status=500)


@blueprint.route("/metrics")
def metrics_page() -> flask.Response:
    """メトリクスページ（SPA ルーティング対応）."""
    try:
        # 設定からstatic_dirを取得
        app_config = _get_app_config()
        static_dir = app_config.webapp.static_dir_path if app_config else None

        # トップページと同じ HTML を返す（React Router が /metrics を処理）
        html = _render_top_page_html(static_dir)

        return flask.Response(html, mimetype="text/html")

    except Exception:
        logging.exception("Error rendering metrics page")
        return flask.Response("Internal server error", status=500)


# === メトリクス API ===


def _get_metrics_db() -> price_watch.metrics.MetricsDB | None:
    """メトリクス DB を取得."""
    try:
        app_config = _get_app_config()
        if app_config is None:
            return None
        metrics_db_path = app_config.data.metrics / "metrics.db"
        if not metrics_db_path.exists():
            return None
        return price_watch.metrics.MetricsDB(metrics_db_path)
    except Exception:
        logging.warning("Failed to get metrics DB")
        return None


@blueprint.route("/api/metrics/status")
def api_metrics_status() -> flask.Response:
    """現在のクローラ状態を取得."""
    metrics_db = _get_metrics_db()
    if metrics_db is None:
        return flask.make_response(flask.jsonify({"error": "Metrics DB not available"}), 503)

    status = metrics_db.get_current_session_status()
    return flask.jsonify(
        {
            "is_running": status.is_running,
            "session_id": status.session_id,
            "started_at": status.started_at.isoformat() if status.started_at else None,
            "last_heartbeat_at": status.last_heartbeat_at.isoformat() if status.last_heartbeat_at else None,
            "uptime_sec": status.uptime_sec,
            "total_items": status.total_items,
            "success_items": status.success_items,
            "failed_items": status.failed_items,
        }
    )


@blueprint.route("/api/metrics/sessions")
def api_metrics_sessions() -> flask.Response:
    """セッション一覧を取得."""
    metrics_db = _get_metrics_db()
    if metrics_db is None:
        return flask.make_response(flask.jsonify({"error": "Metrics DB not available"}), 503)

    start_date = flask.request.args.get("start_date")
    end_date = flask.request.args.get("end_date")
    limit = int(flask.request.args.get("limit", "100"))

    sessions = metrics_db.get_sessions(start_date=start_date, end_date=end_date, limit=limit)
    return flask.jsonify(
        {
            "sessions": [
                {
                    "id": s.id,
                    "started_at": s.started_at.isoformat(),
                    "ended_at": s.ended_at.isoformat() if s.ended_at else None,
                    "duration_sec": s.duration_sec,
                    "total_items": s.total_items,
                    "success_items": s.success_items,
                    "failed_items": s.failed_items,
                    "exit_reason": s.exit_reason,
                }
                for s in sessions
            ]
        }
    )


@blueprint.route("/api/metrics/stores")
def api_metrics_stores() -> flask.Response:
    """ストア統計一覧を取得."""
    metrics_db = _get_metrics_db()
    if metrics_db is None:
        return flask.make_response(flask.jsonify({"error": "Metrics DB not available"}), 503)

    store_name = flask.request.args.get("store_name")
    start_date = flask.request.args.get("start_date")
    end_date = flask.request.args.get("end_date")
    limit = int(flask.request.args.get("limit", "1000"))

    stats = metrics_db.get_store_stats(
        store_name=store_name, start_date=start_date, end_date=end_date, limit=limit
    )
    return flask.jsonify(
        {
            "store_stats": [
                {
                    "id": s.id,
                    "session_id": s.session_id,
                    "store_name": s.store_name,
                    "started_at": s.started_at.isoformat(),
                    "ended_at": s.ended_at.isoformat() if s.ended_at else None,
                    "duration_sec": s.duration_sec,
                    "item_count": s.item_count,
                    "success_count": s.success_count,
                    "failed_count": s.failed_count,
                }
                for s in stats
            ]
        }
    )


@blueprint.route("/api/metrics/heatmap")
def api_metrics_heatmap() -> flask.Response:
    """稼働率ヒートマップを取得."""
    metrics_db = _get_metrics_db()
    if metrics_db is None:
        return flask.make_response(flask.jsonify({"error": "Metrics DB not available"}), 503)

    # デフォルト: 過去7日間
    from datetime import timedelta

    import my_lib.time

    now = my_lib.time.now()
    end_date = flask.request.args.get("end_date", now.strftime("%Y-%m-%d"))
    start_date = flask.request.args.get("start_date", (now - timedelta(days=6)).strftime("%Y-%m-%d"))

    heatmap = metrics_db.get_uptime_heatmap(start_date, end_date)
    return flask.jsonify(
        {
            "dates": heatmap.dates,
            "hours": heatmap.hours,
            "cells": [{"date": c.date, "hour": c.hour, "uptime_rate": c.uptime_rate} for c in heatmap.cells],
        }
    )


def _generate_heatmap_svg(heatmap: price_watch.metrics.HeatmapData) -> bytes:
    """GitHubスタイルのヒートマップSVGを直接生成.

    横幅を固定し、日数に応じてセル幅を自動調整。縦は24時間固定。
    """
    from datetime import datetime as dt

    dates = heatmap.dates
    hours = heatmap.hours
    day_names = ["月", "火", "水", "木", "金", "土", "日"]

    # カラーパレット（5段階：灰色→黄色→緑）
    colors = ["#e0e0e0", "#fff59d", "#ffee58", "#a5d610", "#4caf50"]

    def get_color(ratio: float | None) -> str:
        """稼働率から色を取得."""
        if ratio is None:
            return "#ebedf0"
        if ratio < 0.2:
            return colors[0]
        elif ratio < 0.4:
            return colors[1]
        elif ratio < 0.6:
            return colors[2]
        elif ratio < 0.8:
            return colors[3]
        else:
            return colors[4]

    # 固定横幅とマージン
    target_width = 1000.0  # px
    margin_left = 25.0  # 時間ラベル用
    margin_right = 4.0
    margin_top = 18.0  # 日付ラベル用
    margin_bottom = 10.0  # 24時ラベル用
    cell_gap = 1.0  # px

    # 縦方向は固定（24時間）
    cell_height = 6.0  # px
    cell_step_y = cell_height + cell_gap

    if not dates:
        return (
            b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 30" '
            b'width="100%" preserveAspectRatio="xMidYMid meet">'
            b'<text x="500" y="20" text-anchor="middle" font-size="12">No data</text></svg>'
        )

    num_dates = len(dates)
    num_hours = len(hours)

    # セルデータをマップ化
    cell_map = {(c.date, c.hour): c.uptime_rate for c in heatmap.cells}

    # セル幅を計算（横幅固定）
    available_width = target_width - margin_left - margin_right
    cell_step_x = available_width / num_dates
    cell_width = max(1, cell_step_x - cell_gap)

    # SVGサイズ計算
    svg_width = target_width
    svg_height = margin_top + num_hours * cell_step_y + margin_bottom

    # SVG構築開始（viewBoxでレスポンシブ対応）
    svg_parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {svg_width} {svg_height}" '
        f'width="100%" preserveAspectRatio="xMidYMid meet">',
        "<style>",
        "  .label { font-family: sans-serif; font-size: 10px; fill: #57606a; }",
        "  .label-sat { font-family: sans-serif; font-size: 10px; fill: #2196f3; }",
        "  .label-sun { font-family: sans-serif; font-size: 10px; fill: #cf222e; }",
        "  .heatmap-cell { cursor: pointer; }",
        "  .heatmap-cell.selected { stroke: #ff6b00; stroke-width: 2; }",
        "</style>",
    ]

    # 日付ラベル（間引いて表示）
    label_width_estimate = 85  # "1月23日(水)" の推定幅
    label_step = max(1, int(label_width_estimate / cell_step_x) + 1)

    # 表示するラベルのインデックスを収集
    label_indices = [j for j in range(num_dates) if j % label_step == 0]

    label_half_width = label_width_estimate / 2  # ラベル幅の半分
    # 許容される最小x座標（左端から少し余裕を持たせつつ、時刻ラベルエリアも活用）
    min_label_x = 4.0

    for j in label_indices:
        date_str = dates[j]
        date_obj = dt.strptime(date_str, "%Y-%m-%d")
        dow = day_names[date_obj.weekday()]
        label = f"{date_obj.month}月{date_obj.day}日({dow})"

        # 位置とアンカーを決定
        cell_center_x = margin_left + j * cell_step_x + cell_width / 2

        if j == label_indices[0] and cell_center_x - label_half_width < min_label_x:
            # 最初のラベル: 見切れる場合のみ左寄せ（時刻ラベルエリアも活用）
            x = min_label_x
            anchor = "start"
        elif j == label_indices[-1] and cell_center_x + label_half_width > svg_width:
            # 最後のラベル: 見切れる場合のみ右寄せ
            x = margin_left + j * cell_step_x + cell_width
            anchor = "end"
        else:
            # 中央揃え
            x = cell_center_x
            anchor = "middle"

        weekday = date_obj.weekday()
        if weekday == 5:  # 土曜日
            css_class = "label-sat"
        elif weekday == 6:  # 日曜日
            css_class = "label-sun"
        else:
            css_class = "label"
        svg_parts.append(
            f'<text x="{x}" y="{margin_top - 5}" class="{css_class}" text-anchor="{anchor}">{label}</text>'
        )

    # 時間ラベル（左側: 0, 6, 12, 18, 24）
    time_labels = [0, 6, 12, 18, 24]
    for hour_label in time_labels:
        if hour_label == 24:
            # 24時は最下部（23時台セルの下端）
            y = margin_top + (num_hours - 1) * cell_step_y + cell_height
        else:
            # 各時間の行のセンターに配置
            y = margin_top + hour_label * cell_step_y + cell_height / 2
        svg_parts.append(
            f'<text x="{margin_left - 4}" y="{y}" class="label" text-anchor="end" '
            f'dominant-baseline="middle">{hour_label}</text>'
        )

    # セル描画（縦:24時間、横:日付）
    for i, hour in enumerate(hours):
        y = margin_top + i * cell_step_y
        for j, date_str in enumerate(dates):
            x = margin_left + j * cell_step_x
            ratio = cell_map.get((date_str, hour))
            color = get_color(ratio)
            # ツールチップ用のテキスト
            date_obj = dt.strptime(date_str, "%Y-%m-%d")
            dow = day_names[date_obj.weekday()]
            ratio_text = f"{ratio * 100:.1f}%" if ratio is not None else "データなし"
            tooltip = f"{date_obj.month}月{date_obj.day}日({dow}) {hour}時台: {ratio_text}"
            svg_parts.append(
                f'<rect x="{x}" y="{y}" width="{cell_width}" height="{cell_height}" '
                f'fill="{color}" data-tooltip="{tooltip}" class="heatmap-cell" '
                f'style="cursor: pointer;"/>'
            )

    svg_parts.append("</svg>")

    return "\n".join(svg_parts).encode("utf-8")


@blueprint.route("/api/metrics/heatmap.svg")
def api_metrics_heatmap_svg() -> flask.Response:
    """稼働率ヒートマップ画像（SVG）を取得."""
    metrics_db = _get_metrics_db()
    if metrics_db is None:
        return flask.Response("Metrics DB not available", status=503)

    from datetime import timedelta

    import my_lib.time

    now = my_lib.time.now()
    days = int(flask.request.args.get("days", "7"))
    end_date = now.strftime("%Y-%m-%d")
    start_date = (now - timedelta(days=days - 1)).strftime("%Y-%m-%d")

    try:
        heatmap = metrics_db.get_uptime_heatmap(start_date, end_date)
        svg_data = _generate_heatmap_svg(heatmap)
        return flask.Response(svg_data, mimetype="image/svg+xml")
    except Exception:
        logging.exception("Failed to generate heatmap SVG")
        return flask.Response("Internal server error", status=500)


@blueprint.route("/api/sysinfo")
def api_sysinfo() -> flask.Response:
    """システム情報を取得."""
    import os
    import platform

    import my_lib.time

    now = my_lib.time.now()

    # イメージビルド日時（環境変数から取得）
    image_build_date = os.environ.get("IMAGE_BUILD_DATE", None)

    # load average（Linux のみ）
    load_average = None
    if platform.system() == "Linux":
        try:
            load = os.getloadavg()
            load_average = f"{load[0]:.2f}, {load[1]:.2f}, {load[2]:.2f}"
        except OSError:
            pass

    return flask.jsonify(
        {
            "date": now.isoformat(),
            "timezone": str(my_lib.time.get_zoneinfo()),
            "image_build_date": image_build_date,
            "load_average": load_average,
        }
    )
