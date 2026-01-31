#!/usr/bin/env python3
"""target.yaml エディタ API エンドポイント.

target.yaml の読み込み、保存、バリデーションを行う API を提供します。
"""

import io
import logging
import pathlib
import shutil
from typing import Any

import flask
import my_lib.time
from flask_pydantic import validate
from ruamel.yaml import YAML

import price_watch.webapi.cache
import price_watch.webapi.git_sync
import price_watch.webapi.schemas

blueprint = flask.Blueprint("target_editor", __name__)

# ruamel.yaml の設定
_yaml = YAML()
_yaml.preserve_quotes = True
_yaml.indent(mapping=4, sequence=4, offset=2)
_yaml.default_flow_style = False


def _get_target_file_path() -> pathlib.Path:
    """target.yaml のファイルパスを取得."""
    return price_watch.webapi.cache.get_target_config_cache().file_path


def _load_raw_target() -> dict[str, Any]:
    """target.yaml を生のデータとして読み込む."""
    target_path = _get_target_file_path()
    if not target_path.exists():
        return {"category_list": [], "store_list": [], "item_list": []}

    with target_path.open("r", encoding="utf-8") as f:
        data = _yaml.load(f)
        return dict(data) if data else {"category_list": [], "store_list": [], "item_list": []}


def _save_raw_target(data: dict[str, Any], *, create_backup: bool = True) -> None:
    """target.yaml を保存（アトミック書き込み）.

    Args:
        data: 保存するデータ
        create_backup: バックアップを作成するか
    """
    target_path = _get_target_file_path()

    # バックアップ作成
    if create_backup and target_path.exists():
        timestamp = my_lib.time.now().strftime("%Y%m%d_%H%M%S")
        backup_path = target_path.with_suffix(f".yaml.bak.{timestamp}")
        shutil.copy2(target_path, backup_path)
        logging.info("Created backup: %s", backup_path)

    # 一時ファイルに書き込み
    tmp_path = target_path.with_suffix(".yaml.tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        _yaml.dump(data, f)

    # アトミックに置換
    tmp_path.replace(target_path)
    logging.info("Saved target.yaml")


def _convert_schema_to_raw(config: price_watch.webapi.schemas.TargetConfigSchema) -> dict[str, Any]:
    """Pydantic スキーマから生データに変換."""
    result: dict[str, Any] = {}

    # category_list
    if config.category_list:
        result["category_list"] = list(config.category_list)

    # store_list
    if config.store_list:
        store_list = []
        for store in config.store_list:
            store_data: dict[str, Any] = {"name": store.name}

            # check_method (scrape 以外のみ出力)
            if store.check_method != "scrape":
                store_data["check_method"] = store.check_method

            # XPath 関連
            if store.price_xpath:
                store_data["price_xpath"] = store.price_xpath
            if store.thumb_img_xpath:
                store_data["thumb_img_xpath"] = store.thumb_img_xpath
            if store.unavailable_xpath:
                store_data["unavailable_xpath"] = store.unavailable_xpath

            # 通貨・ポイント
            if store.price_unit != "円":
                store_data["price_unit"] = store.price_unit
            if store.point_rate > 0:
                store_data["point_rate"] = store.point_rate

            # 色
            if store.color:
                store_data["color"] = store.color

            # アクション
            if store.action:
                store_data["action"] = [
                    {k: v for k, v in {"type": a.type, "xpath": a.xpath, "value": a.value}.items() if v}
                    for a in store.action
                ]

            store_list.append(store_data)

        result["store_list"] = store_list

    # item_list
    if config.item_list:
        item_list = []
        for item in config.item_list:
            item_data: dict[str, Any] = {"name": item.name}

            # カテゴリー
            if item.category:
                item_data["category"] = item.category

            # アイテムレベルの共通設定
            if item.price:
                item_data["price"] = list(item.price)
            if item.cond:
                item_data["cond"] = item.cond

            # ストアリスト
            store_entries = []
            for store_entry in item.store:
                entry_data: dict[str, Any] = {"name": store_entry.name}

                if store_entry.url:
                    entry_data["url"] = store_entry.url
                if store_entry.asin:
                    entry_data["asin"] = store_entry.asin
                if store_entry.price_xpath:
                    entry_data["price_xpath"] = store_entry.price_xpath
                if store_entry.thumb_img_xpath:
                    entry_data["thumb_img_xpath"] = store_entry.thumb_img_xpath
                if store_entry.unavailable_xpath:
                    entry_data["unavailable_xpath"] = store_entry.unavailable_xpath
                if store_entry.price_unit:
                    entry_data["price_unit"] = store_entry.price_unit
                if store_entry.preload:
                    entry_data["preload"] = {
                        "url": store_entry.preload.url,
                        "every": store_entry.preload.every,
                    }
                if store_entry.search_keyword:
                    entry_data["search_keyword"] = store_entry.search_keyword
                if store_entry.exclude_keyword:
                    entry_data["exclude_keyword"] = store_entry.exclude_keyword
                if store_entry.price:
                    entry_data["price"] = list(store_entry.price)
                if store_entry.cond:
                    entry_data["cond"] = store_entry.cond
                if store_entry.jan_code:
                    entry_data["jan_code"] = store_entry.jan_code

                store_entries.append(entry_data)

            item_data["store"] = store_entries
            item_list.append(item_data)

        result["item_list"] = item_list

    return result


def _convert_raw_to_schema(data: dict[str, Any]) -> price_watch.webapi.schemas.TargetConfigSchema:
    """生データから Pydantic スキーマに変換."""
    # category_list
    category_list = data.get("category_list", [])

    # store_list
    store_list = []
    for store_data in data.get("store_list", []):
        actions = [
            price_watch.webapi.schemas.ActionStepSchema(
                type=action.get("type", "click"),
                xpath=action.get("xpath"),
                value=action.get("value"),
            )
            for action in store_data.get("action", [])
        ]

        # point_rate は assumption.point_rate またはトップレベルから取得
        assumption = store_data.get("assumption", {})
        point_rate = float(assumption.get("point_rate", store_data.get("point_rate", 0.0)))

        store_list.append(
            price_watch.webapi.schemas.StoreDefinitionSchema(
                name=store_data["name"],
                check_method=store_data.get("check_method", "scrape"),
                price_xpath=store_data.get("price_xpath"),
                thumb_img_xpath=store_data.get("thumb_img_xpath"),
                unavailable_xpath=store_data.get("unavailable_xpath"),
                price_unit=store_data.get("price_unit", "円"),
                point_rate=point_rate,
                color=store_data.get("color"),
                action=actions,
            )
        )

    # item_list
    item_list = []
    for item_data in data.get("item_list", []):
        store_entries = []
        store_field = item_data.get("store", [])

        # 新書式: store がリスト
        if isinstance(store_field, list):
            for store_entry in store_field:
                preload = None
                if "preload" in store_entry:
                    preload = price_watch.webapi.schemas.PreloadConfigSchema(
                        url=store_entry["preload"]["url"],
                        every=store_entry["preload"].get("every", 1),
                    )

                # price フィールドの処理
                price = None
                if "price" in store_entry:
                    price_data = store_entry["price"]
                    if isinstance(price_data, list):
                        price = [int(p) for p in price_data]
                    elif isinstance(price_data, int):
                        price = [price_data]

                store_entries.append(
                    price_watch.webapi.schemas.StoreEntrySchema(
                        name=store_entry["name"],
                        url=store_entry.get("url"),
                        asin=store_entry.get("asin"),
                        price_xpath=store_entry.get("price_xpath"),
                        thumb_img_xpath=store_entry.get("thumb_img_xpath"),
                        unavailable_xpath=store_entry.get("unavailable_xpath"),
                        price_unit=store_entry.get("price_unit"),
                        preload=preload,
                        search_keyword=store_entry.get("search_keyword"),
                        exclude_keyword=store_entry.get("exclude_keyword"),
                        price=price,
                        cond=store_entry.get("cond"),
                        jan_code=store_entry.get("jan_code"),
                    )
                )
        # 旧書式: store が文字列（単一ストア）
        elif isinstance(store_field, str):
            preload = None
            if "preload" in item_data:
                preload = price_watch.webapi.schemas.PreloadConfigSchema(
                    url=item_data["preload"]["url"],
                    every=item_data["preload"].get("every", 1),
                )

            price = None
            if "price" in item_data:
                price_data = item_data["price"]
                if isinstance(price_data, list):
                    price = [int(p) for p in price_data]
                elif isinstance(price_data, int):
                    price = [price_data]

            store_entries.append(
                price_watch.webapi.schemas.StoreEntrySchema(
                    name=store_field,
                    url=item_data.get("url"),
                    asin=item_data.get("asin"),
                    price_xpath=item_data.get("price_xpath"),
                    thumb_img_xpath=item_data.get("thumb_img_xpath"),
                    unavailable_xpath=item_data.get("unavailable_xpath"),
                    price_unit=item_data.get("price_unit"),
                    preload=preload,
                    search_keyword=item_data.get("search_keyword"),
                    exclude_keyword=item_data.get("exclude_keyword"),
                    price=price,
                    cond=item_data.get("cond"),
                    jan_code=item_data.get("jan_code"),
                )
            )

        # アイテムレベルの price と cond
        item_price = None
        if "price" in item_data and isinstance(item_data.get("store"), list):
            price_data = item_data["price"]
            if isinstance(price_data, list):
                item_price = [int(p) for p in price_data]
            elif isinstance(price_data, int):
                item_price = [price_data]

        item_list.append(
            price_watch.webapi.schemas.ItemDefinitionSchema(
                name=item_data["name"],
                category=item_data.get("category"),
                price=item_price,
                cond=item_data.get("cond") if isinstance(item_data.get("store"), list) else None,
                store=store_entries,
            )
        )

    return price_watch.webapi.schemas.TargetConfigSchema(
        category_list=category_list,
        store_list=store_list,
        item_list=item_list,
    )


def _validate_config(
    config: price_watch.webapi.schemas.TargetConfigSchema,
) -> list[price_watch.webapi.schemas.ValidationError]:
    """設定のバリデーション."""
    errors: list[price_watch.webapi.schemas.ValidationError] = []

    # ストア名の重複チェック
    store_names = [s.name for s in config.store_list]
    seen: set[str] = set()
    for i, name in enumerate(store_names):
        if name in seen:
            errors.append(
                price_watch.webapi.schemas.ValidationError(
                    path=f"store_list[{i}].name",
                    message=f"ストア名 '{name}' が重複しています",
                )
            )
        seen.add(name)

    # アイテムのストア参照チェック
    valid_stores = set(store_names)
    for i, item in enumerate(config.item_list):
        for j, store_entry in enumerate(item.store):
            if store_entry.name not in valid_stores:
                errors.append(
                    price_watch.webapi.schemas.ValidationError(
                        path=f"item_list[{i}].store[{j}].name",
                        message=f"ストア '{store_entry.name}' は store_list に定義されていません",
                    )
                )

            # スクレイピングストアの場合、URL が必要
            store_def = next((s for s in config.store_list if s.name == store_entry.name), None)
            if (
                store_def
                and store_def.check_method == "scrape"
                and not store_entry.url
                and not store_entry.asin
            ):
                errors.append(
                    price_watch.webapi.schemas.ValidationError(
                        path=f"item_list[{i}].store[{j}]",
                        message=f"ストア '{store_entry.name}' には url または asin が必要です",
                    )
                )

    return errors


@blueprint.route("/api/target", methods=["GET"])
def get_target() -> flask.Response | tuple[flask.Response, int]:
    """target.yaml の現在の設定を取得."""
    try:
        raw_data = _load_raw_target()
        config = _convert_raw_to_schema(raw_data)

        # パスワード認証が必要かどうかを判定
        app_config = price_watch.webapi.cache.get_app_config()
        require_password = False
        if app_config and app_config.edit and app_config.edit.password:
            require_password = True

        response = price_watch.webapi.schemas.TargetConfigResponse(
            config=config,
            check_methods=price_watch.webapi.schemas.CHECK_METHODS,
            action_types=price_watch.webapi.schemas.ACTION_TYPES,
            require_password=require_password,
        )

        return flask.jsonify(response.model_dump())

    except Exception:
        logging.exception("Error getting target config")
        error = price_watch.webapi.schemas.ErrorResponse(error="設定の読み込みに失敗しました")
        return flask.jsonify(error.model_dump()), 500


@blueprint.route("/api/target", methods=["PUT"])
@validate()
def update_target(
    body: price_watch.webapi.schemas.TargetUpdateRequest,
) -> flask.Response | tuple[flask.Response, int]:
    """target.yaml を更新."""
    try:
        # アプリ設定を取得
        app_config = price_watch.webapi.cache.get_app_config()
        edit_config = app_config.edit if app_config else None

        # パスワード認証
        if edit_config and edit_config.password and body.password != edit_config.password:
            error = price_watch.webapi.schemas.ErrorResponse(error="パスワードが正しくありません")
            return flask.jsonify(error.model_dump()), 401

        # バリデーション
        errors = _validate_config(body.config)
        if errors:
            response = price_watch.webapi.schemas.ValidateResponse(valid=False, errors=errors)
            return flask.jsonify(response.model_dump()), 400

        # 保存
        raw_data = _convert_schema_to_raw(body.config)
        _save_raw_target(raw_data, create_backup=body.create_backup)

        # Git push（設定されている場合）
        git_pushed = False
        git_commit_url: str | None = None
        if edit_config and edit_config.git:
            # YAML 文字列を生成
            yaml_output = io.StringIO()
            _yaml.dump(raw_data, yaml_output)
            content = yaml_output.getvalue()

            # コミットメッセージを生成（ファイル名を含める）
            target_file_name = _get_target_file_path().name
            commit_message = f"fix: {target_file_name} via price-watch Web UI"

            result = price_watch.webapi.git_sync.sync_to_remote(
                config=edit_config.git,
                content=content,
                commit_message=commit_message,
            )
            if result.success:
                git_pushed = True
                git_commit_url = result.commit_url
            else:
                # Git push 失敗時はエラーを返す（ローカルは保存済み）
                error_msg = f"ローカル保存は成功しましたが、Git push に失敗しました: {result.error}"
                error = price_watch.webapi.schemas.ErrorResponse(error=error_msg)
                return flask.jsonify(error.model_dump()), 500

        update_response = price_watch.webapi.schemas.TargetUpdateResponse(
            success=True,
            git_pushed=git_pushed,
            git_commit_url=git_commit_url,
        )
        return flask.jsonify(update_response.model_dump())

    except Exception:
        logging.exception("Error updating target config")
        error = price_watch.webapi.schemas.ErrorResponse(error="設定の保存に失敗しました")
        return flask.jsonify(error.model_dump()), 500


@blueprint.route("/api/target/validate", methods=["POST"])
@validate()
def validate_target(
    body: price_watch.webapi.schemas.TargetConfigSchema,
) -> flask.Response:
    """設定の事前バリデーション（保存せずに検証）."""
    errors = _validate_config(body)
    response = price_watch.webapi.schemas.ValidateResponse(valid=len(errors) == 0, errors=errors)
    return flask.jsonify(response.model_dump())
