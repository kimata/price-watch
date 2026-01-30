#!/usr/bin/env python3
"""API エンドポイント."""

import logging
import pathlib
from dataclasses import dataclass

import flask
from flask_pydantic import validate

import price_watch.event
import price_watch.managers.history
import price_watch.metrics
import price_watch.models
import price_watch.target
import price_watch.thumbnail
import price_watch.webapi.cache
import price_watch.webapi.metrics
import price_watch.webapi.ogp
import price_watch.webapi.schemas

blueprint = flask.Blueprint("page", __name__)


@dataclass(frozen=True)
class ProcessedStoreData:
    """ストア処理の中間結果."""

    store_entry: price_watch.webapi.schemas.StoreEntry
    thumb_url: str | None


# キャッシュ関連は cache モジュールに移動
# 互換性のためのエイリアス
init_file_paths = price_watch.webapi.cache.init_file_paths


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
            keys.add(
                price_watch.managers.history.generate_item_key(
                    search_keyword=keyword, search_cond="", store_name=item.store
                )
            )
        else:
            keys.add(price_watch.managers.history.url_hash(item.url))
    return keys


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


def _find_first_thumb_url(store_data_list: list[ProcessedStoreData]) -> str | None:
    """最初に見つかったサムネイルURLを取得."""
    for sd in store_data_list:
        if sd.thumb_url:
            return sd.thumb_url
    return None


def _build_result_item(
    name: str,
    store_data_list: list[ProcessedStoreData],
    category: str = "その他",
) -> price_watch.webapi.schemas.ResultItem:
    """グルーピングされたアイテムから結果アイテムを構築."""
    stores = [sd.store_entry for sd in store_data_list]
    best_store_entry = _find_best_store(stores)
    thumb_url = _find_first_thumb_url(store_data_list)

    return price_watch.webapi.schemas.ResultItem(
        name=name,
        thumb_url=thumb_url,
        stores=stores,
        best_store=best_store_entry.store,
        best_effective_price=best_store_entry.effective_price,
        category=category,
    )


def _build_category_map(
    target_config: price_watch.target.TargetConfig | None,
) -> dict[str, str]:
    """target.yaml の resolved_items からアイテム名→カテゴリーのマッピングを構築."""
    if target_config is None:
        return {}

    category_map: dict[str, str] = {}
    try:
        resolved_items = target_config.resolve_items()
    except Exception:
        logging.warning("Failed to resolve target items for category map")
        return {}

    for item in resolved_items:
        if item.category and item.name not in category_map:
            category_map[item.name] = item.category
    return category_map


def _build_category_order(
    target_config: price_watch.target.TargetConfig | None,
    category_map: dict[str, str],
    item_names: set[str],
) -> list[str]:
    """カテゴリーの表示順を構築.

    順序:
    1. category_list に指定されたカテゴリー（指定順）
    2. category_list にないカテゴリー（アルファベット順）
    3. 「その他」は category_list に含まれていればその位置、含まれていなければ末尾
    """
    # 実際に使用されているカテゴリーを収集
    used_categories: set[str] = set()
    for name in item_names:
        used_categories.add(category_map.get(name, "その他"))

    if not used_categories:
        return []

    configured_categories = target_config.categories if target_config else []

    # category_list に「その他」が含まれているか確認
    has_other_in_list = "その他" in configured_categories

    # 1. category_list に指定されたカテゴリー（使用されているもののみ）
    ordered: list[str] = []
    listed_set: set[str] = set()
    for cat in configured_categories:
        if cat in used_categories:
            ordered.append(cat)
            listed_set.add(cat)

    # 2. category_list にないカテゴリー（「その他」を除く）をアルファベット順で追加
    unlisted = sorted(used_categories - listed_set - {"その他"})

    # 「その他」が category_list に含まれている場合: unlisted を ordered の末尾に追加
    # 「その他」が category_list に含まれていない場合: unlisted を追加した後に「その他」を末尾に追加
    ordered.extend(unlisted)

    if not has_other_in_list and "その他" in used_categories:
        ordered.append("その他")

    return ordered


def _get_store_definitions(
    target_config: price_watch.target.TargetConfig | None,
) -> list[price_watch.webapi.schemas.StoreDefinition]:
    """ストア定義を生成."""
    if not target_config:
        return []

    # 通貨換算レートを取得（price_unit → rate のマッピング）
    app_config = price_watch.webapi.cache.get_app_config()
    currency_rates: dict[str, float] = {}
    if app_config and app_config.check.currency:
        for cr in app_config.check.currency:
            currency_rates[cr.label] = cr.rate

    return [
        price_watch.webapi.schemas.StoreDefinition(
            name=store.name,
            point_rate=store.point_rate,
            color=store.color,
            price_unit=store.price_unit,
            currency_rate=currency_rates.get(store.price_unit, 1.0),
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
) -> ProcessedStoreData | None:
    """1つのアイテムを処理してストアデータを構築.

    Args:
        item: アイテムレコード
        days: 期間（日数）
        target_config: ターゲット設定
        include_history: 履歴を含めるかどうか（軽量API用にFalseを指定）
    """
    history = price_watch.webapi.cache.get_history_manager()

    # ポイント還元率と通貨単位を取得
    point_rate = _get_point_rate(target_config, item.store)
    price_unit = _get_price_unit(target_config, item.store)

    # 最新価格を取得
    latest = history.get_latest(item.id)
    if not latest:
        # 履歴がないアイテムも表示（在庫なしとして）
        store_entry = _build_store_entry_without_history_from_record(item, point_rate, price_unit)
        return ProcessedStoreData(store_entry=store_entry, thumb_url=item.thumb_url)

    # 統計情報を取得
    stats = history.get_stats(item.id, days)

    # 価格履歴を取得（include_history=False の場合はスキップ）
    hist: list[price_watch.models.PriceRecord] = []
    if include_history:
        _, hist = history.get_history(item.item_key, days)

    store_entry = _build_store_entry(
        item, latest, stats, hist, point_rate, price_unit, include_history=include_history
    )

    return ProcessedStoreData(store_entry=store_entry, thumb_url=item.thumb_url)


def _collect_stores_for_name(
    item_name: str,
    all_items: list[price_watch.models.ItemRecord],
    target_item_keys: set[str],
    days: int | None,
    target_config: price_watch.target.TargetConfig | None,
    *,
    include_history: bool = True,
) -> list[ProcessedStoreData]:
    """指定されたアイテム名に対応する全ストアのデータを収集."""
    store_data_list: list[ProcessedStoreData] = []
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
) -> dict[str, list[ProcessedStoreData]]:
    """アイテムを名前でグルーピング.

    Args:
        all_items: 全アイテムレコード
        target_item_keys: 監視対象アイテムキーのセット
        days: 期間（日数）
        target_config: ターゲット設定
        include_history: 履歴を含めるかどうか（軽量API用にFalseを指定）
    """
    items_by_name: dict[str, list[ProcessedStoreData]] = {}
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
                processed_keys.add(sd.store_entry.item_key)

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
                    search_keyword=keyword, search_cond="", store_name=resolved_item.store
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
) -> ProcessedStoreData | None:
    """DB に存在しないアイテムを処理してストアデータを構築."""
    # ポイント還元率と通貨単位を取得
    point_rate = _get_point_rate(target_config, item.store)
    price_unit = _get_price_unit(target_config, item.store)

    # 履歴がないアイテムとして表示
    store_entry = _build_store_entry_without_history_from_record(item, point_rate, price_unit)
    return ProcessedStoreData(store_entry=store_entry, thumb_url=item.thumb_url)


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
        target_config = price_watch.webapi.cache.get_target_config()
        target_item_keys = _get_target_item_keys(target_config)

        all_items = price_watch.webapi.cache.get_history_manager().get_all_items()

        # アイテム名でグルーピング（履歴なしで軽量化）
        items_by_name = _group_items_by_name(
            all_items, target_item_keys, days, target_config, include_history=False
        )

        # カテゴリーマッピングを構築（アイテム名 → カテゴリー名）
        category_map = _build_category_map(target_config)

        # カテゴリー表示順を構築
        categories = _build_category_order(target_config, category_map, set(items_by_name.keys()))

        # グルーピングされたアイテムを構築
        result_items = [
            _build_result_item(name, store_data_list, category=category_map.get(name, "その他"))
            for name, store_data_list in items_by_name.items()
        ]

        # 設定から監視間隔を取得
        app_config = price_watch.webapi.cache.get_app_config()
        check_interval_sec = app_config.check.interval_sec if app_config else 1800

        response = price_watch.webapi.schemas.ItemsResponse(
            items=result_items,
            store_definitions=_get_store_definitions(target_config),
            categories=categories,
            check_interval_sec=check_interval_sec,
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

        item, hist = price_watch.webapi.cache.get_history_manager().get_history(item_key, days)

        if item is None:
            error = price_watch.webapi.schemas.ErrorResponse(error="Item not found")
            return flask.jsonify(error.model_dump()), 404

        # ポイント還元率を取得（キャッシュ使用）
        target_config = price_watch.webapi.cache.get_target_config()
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
@validate()
def get_item_events(
    item_key: str, query: price_watch.webapi.schemas.ItemEventsQueryParams
) -> flask.Response | tuple[flask.Response, int]:
    """アイテム別イベント履歴を取得."""
    try:
        events = price_watch.webapi.cache.get_history_manager().get_item_events(item_key, query.limit)

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
@validate()
def get_events(
    query: price_watch.webapi.schemas.EventsQueryParams,
) -> flask.Response | tuple[flask.Response, int]:
    """最新イベント一覧を取得."""
    try:
        events = price_watch.webapi.cache.get_history_manager().get_recent_events(query.limit)

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
    target_config = price_watch.webapi.cache.get_target_config()
    all_items = price_watch.webapi.cache.get_history_manager().get_all_items()

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

    stores = [sd.store_entry for sd in store_data_list]
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
        app_config = price_watch.webapi.cache.get_app_config()
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
        app_config = price_watch.webapi.cache.get_app_config()
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
        target_config = price_watch.webapi.cache.get_target_config()

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
        app_config = price_watch.webapi.cache.get_app_config()
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
        target_config = price_watch.webapi.cache.get_target_config()

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
        app_config = price_watch.webapi.cache.get_app_config()
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
        app_config = price_watch.webapi.cache.get_app_config()
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
        app_config = price_watch.webapi.cache.get_app_config()
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
            "is_crawling": status.is_crawling,
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
@validate()
def api_metrics_sessions(
    query: price_watch.webapi.schemas.MetricsSessionsQueryParams,
) -> flask.Response:
    """セッション一覧を取得."""
    metrics_db = _get_metrics_db()
    if metrics_db is None:
        return flask.make_response(flask.jsonify({"error": "Metrics DB not available"}), 503)

    sessions = metrics_db.get_sessions(
        start_date=query.start_date, end_date=query.end_date, limit=query.limit
    )
    return flask.jsonify(
        {
            "sessions": [
                {
                    "id": s.id,
                    "started_at": s.started_at.isoformat(),
                    "ended_at": s.ended_at.isoformat() if s.ended_at else None,
                    "work_ended_at": s.work_ended_at.isoformat() if s.work_ended_at else None,
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
@validate()
def api_metrics_stores(
    query: price_watch.webapi.schemas.MetricsStoresQueryParams,
) -> flask.Response:
    """ストア統計一覧を取得."""
    metrics_db = _get_metrics_db()
    if metrics_db is None:
        return flask.make_response(flask.jsonify({"error": "Metrics DB not available"}), 503)

    stats = metrics_db.get_store_stats(
        store_name=query.store_name,
        start_date=query.start_date,
        end_date=query.end_date,
        limit=query.limit,
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
@validate()
def api_metrics_heatmap(
    query: price_watch.webapi.schemas.MetricsHeatmapQueryParams,
) -> flask.Response:
    """稼働率ヒートマップを取得."""
    metrics_db = _get_metrics_db()
    if metrics_db is None:
        return flask.make_response(flask.jsonify({"error": "Metrics DB not available"}), 503)

    # デフォルト: 過去7日間
    from datetime import timedelta

    import my_lib.time

    now = my_lib.time.now()
    end_date = query.end_date if query.end_date else now.strftime("%Y-%m-%d")
    start_date = query.start_date if query.start_date else (now - timedelta(days=6)).strftime("%Y-%m-%d")

    heatmap = metrics_db.get_uptime_heatmap(start_date, end_date)
    return flask.jsonify(
        {
            "dates": heatmap.dates,
            "hours": heatmap.hours,
            "cells": [{"date": c.date, "hour": c.hour, "uptime_rate": c.uptime_rate} for c in heatmap.cells],
        }
    )


@blueprint.route("/api/metrics/heatmap.svg")
@validate()
def api_metrics_heatmap_svg(
    query: price_watch.webapi.schemas.MetricsHeatmapSvgQueryParams,
) -> flask.Response:
    """稼働率ヒートマップ画像（SVG）を取得."""
    metrics_db = _get_metrics_db()
    if metrics_db is None:
        return flask.Response("Metrics DB not available", status=503)

    from datetime import timedelta

    import my_lib.time

    now = my_lib.time.now()
    end_date = now.strftime("%Y-%m-%d")
    start_date = (now - timedelta(days=query.days - 1)).strftime("%Y-%m-%d")

    try:
        heatmap = metrics_db.get_uptime_heatmap(start_date, end_date)
        svg_data = price_watch.webapi.metrics.generate_heatmap_svg(heatmap)
        return flask.Response(svg_data, mimetype="image/svg+xml")
    except Exception:
        logging.exception("Failed to generate heatmap SVG")
        return flask.Response("Internal server error", status=500)


@blueprint.route("/api/metrics/crawl-time/boxplot")
@validate()
def api_metrics_crawl_time_boxplot(
    query: price_watch.webapi.schemas.MetricsCrawlTimeQueryParams,
) -> flask.Response:
    """巡回時間の箱ひげ図データを取得."""
    metrics_db = _get_metrics_db()
    if metrics_db is None:
        return flask.make_response(flask.jsonify({"error": "Metrics DB not available"}), 503)

    try:
        boxplot_data = metrics_db.get_crawl_time_boxplot(query.days)

        def _stats_to_dict(stats: price_watch.metrics.BoxPlotStats) -> dict[str, object]:
            return {
                "min": stats.min,
                "q1": stats.q1,
                "median": stats.median,
                "q3": stats.q3,
                "max": stats.max,
                "count": stats.count,
                "outliers": stats.outliers,
            }

        stores = {name: _stats_to_dict(s) for name, s in boxplot_data.stores.items()}
        total = _stats_to_dict(boxplot_data.total) if boxplot_data.total else None

        return flask.jsonify({"stores": stores, "total": total})
    except Exception:
        logging.exception("Failed to get crawl time boxplot data")
        return flask.make_response(flask.jsonify({"error": "Internal server error"}), 500)


@blueprint.route("/api/metrics/crawl-time/timeseries-boxplot")
@validate()
def api_metrics_crawl_time_timeseries_boxplot(
    query: price_watch.webapi.schemas.MetricsCrawlTimeQueryParams,
) -> flask.Response:
    """巡回時間の時系列箱ひげ図データを取得（日単位）."""
    metrics_db = _get_metrics_db()
    if metrics_db is None:
        return flask.make_response(flask.jsonify({"error": "Metrics DB not available"}), 503)

    try:
        ts_data = metrics_db.get_crawl_time_timeseries_boxplot(query.days)
        return flask.jsonify(
            {
                "periods": ts_data.periods,
                "total": dict(ts_data.total),
                "stores": {store: dict(day_data) for store, day_data in ts_data.stores.items()},
            }
        )
    except Exception:
        logging.exception("Failed to get crawl time timeseries boxplot data")
        return flask.make_response(flask.jsonify({"error": "Internal server error"}), 500)


@blueprint.route("/api/metrics/failures/timeseries")
@validate()
def api_metrics_failures_timeseries(
    query: price_watch.webapi.schemas.MetricsFailuresQueryParams,
) -> flask.Response:
    """失敗数時系列データを取得."""
    metrics_db = _get_metrics_db()
    if metrics_db is None:
        return flask.make_response(flask.jsonify({"error": "Metrics DB not available"}), 503)

    try:
        ts_data = metrics_db.get_failure_timeseries(query.days)
        return flask.jsonify({"labels": ts_data.labels, "data": ts_data.data})
    except Exception:
        logging.exception("Failed to get failure timeseries data")
        return flask.make_response(flask.jsonify({"error": "Internal server error"}), 500)


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
