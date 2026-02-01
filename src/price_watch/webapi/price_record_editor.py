#!/usr/bin/env python3
"""価格記録編集 API エンドポイント.

価格記録の一覧表示、削除プレビュー、削除を行う API を提供します。
"""

import logging
from typing import Any

import flask
from flask_pydantic import validate
from my_lib.pydantic.base import BaseSchema
from pydantic import Field

import price_watch.notify
import price_watch.webapi.auth_rate_limiter
import price_watch.webapi.cache
import price_watch.webapi.password

blueprint = flask.Blueprint("price_record_editor", __name__)


def _get_client_ip() -> str:
    """クライアントIPアドレスを取得（プロキシ対応）."""
    forwarded_for = flask.request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return flask.request.remote_addr or "unknown"


# === Pydantic スキーマ ===


class PriceRecordSchema(BaseSchema):
    """価格記録."""

    id: int = Field(..., description="レコード ID")
    price: int | None = Field(None, description="価格")
    stock: int | None = Field(None, description="在庫状態")
    time: str = Field(..., description="記録時刻")
    crawl_status: int = Field(..., description="クロールステータス")


class ItemInfoSchema(BaseSchema):
    """アイテム情報."""

    id: int = Field(..., description="アイテム ID")
    item_key: str = Field(..., description="アイテムキー")
    name: str = Field(..., description="アイテム名")
    store: str = Field(..., description="ストア名")
    price_unit: str = Field(default="円", description="価格単位")


class PriceRecordsResponse(BaseSchema):
    """価格記録一覧レスポンス."""

    item: ItemInfoSchema = Field(..., description="アイテム情報")
    records: list[PriceRecordSchema] = Field(..., description="価格記録リスト")
    require_password: bool = Field(..., description="パスワード認証が必要か")


class DeletePreviewRequest(BaseSchema):
    """削除プレビューリクエスト."""

    record_ids: list[int] = Field(..., min_length=1, description="削除対象レコード ID リスト")


class DeletePreviewResponse(BaseSchema):
    """削除プレビューレスポンス."""

    record_count: int = Field(..., description="削除対象レコード数")
    event_count: int = Field(..., description="削除される関連イベント数")
    prices: list[int] = Field(..., description="削除対象の価格リスト")


class DeleteRecordsRequest(BaseSchema):
    """削除リクエスト."""

    record_ids: list[int] = Field(..., min_length=1, description="削除対象レコード ID リスト")
    password: str | None = Field(None, description="パスワード")


class DeleteRecordsResponse(BaseSchema):
    """削除レスポンス."""

    deleted_records: int = Field(..., description="削除したレコード数")
    deleted_events: int = Field(..., description="削除した関連イベント数")
    new_lowest_price: int | None = Field(None, description="削除後の最安値")


class ErrorResponse(BaseSchema):
    """エラーレスポンス."""

    error: str = Field(..., description="エラーメッセージ")


def _get_history_manager() -> Any:
    """HistoryManager を取得."""
    return price_watch.webapi.cache.get_history_manager()


@blueprint.route("/api/items/<item_key>/price-records", methods=["GET"])
def get_price_records(item_key: str) -> flask.Response | tuple[flask.Response, int]:
    """価格記録一覧を取得."""
    try:
        history_manager = _get_history_manager()
        if history_manager is None:
            error = ErrorResponse(error="データベースに接続できません")
            return flask.jsonify(error.model_dump()), 500

        item, records = history_manager.get_records_for_edit(item_key)
        if item is None:
            error = ErrorResponse(error="アイテムが見つかりません")
            return flask.jsonify(error.model_dump()), 404

        # パスワード認証が必要かどうかを判定
        app_config = price_watch.webapi.cache.get_app_config()
        require_password = app_config is not None

        response = PriceRecordsResponse(
            item=ItemInfoSchema(
                id=item.id,
                item_key=item.item_key,
                name=item.name,
                store=item.store,
                price_unit=item.price_unit,
            ),
            records=[
                PriceRecordSchema(
                    id=r["id"],
                    price=r["price"],
                    stock=r["stock"],
                    time=r["time"],
                    crawl_status=r["crawl_status"],
                )
                for r in records
            ],
            require_password=require_password,
        )

        return flask.jsonify(response.model_dump())

    except Exception:
        logging.exception("Error getting price records")
        error = ErrorResponse(error="価格記録の取得に失敗しました")
        return flask.jsonify(error.model_dump()), 500


@blueprint.route("/api/items/<item_key>/price-records/preview-delete", methods=["POST"])
@validate()
def preview_delete(item_key: str, body: DeletePreviewRequest) -> flask.Response | tuple[flask.Response, int]:
    """削除プレビュー（影響範囲確認）."""
    try:
        history_manager = _get_history_manager()
        if history_manager is None:
            error = ErrorResponse(error="データベースに接続できません")
            return flask.jsonify(error.model_dump()), 500

        # アイテム情報を取得
        item_id = history_manager.get_item_id(item_key=item_key)
        if item_id is None:
            error = ErrorResponse(error="アイテムが見つかりません")
            return flask.jsonify(error.model_dump()), 404

        # 削除対象の価格を取得
        prices = history_manager.get_prices_by_record_ids(body.record_ids)

        # 関連イベント数を取得
        event_count = history_manager.count_events_by_price(item_id, prices)

        response = DeletePreviewResponse(
            record_count=len(body.record_ids),
            event_count=event_count,
            prices=prices,
        )

        return flask.jsonify(response.model_dump())

    except Exception:
        logging.exception("Error previewing delete")
        error = ErrorResponse(error="プレビューの取得に失敗しました")
        return flask.jsonify(error.model_dump()), 500


@blueprint.route("/api/items/<item_key>/price-records", methods=["DELETE"])
@validate()
def delete_records(item_key: str, body: DeleteRecordsRequest) -> flask.Response | tuple[flask.Response, int]:
    """選択した記録と関連イベントを削除."""
    try:
        # アプリ設定を取得（必須）
        app_config = price_watch.webapi.cache.get_app_config()
        if app_config is None:
            logging.error("config.yaml の読み込みに失敗したため、削除を拒否しました")
            error = ErrorResponse(error="サーバー設定の読み込みに失敗しました。管理者に連絡してください。")
            return flask.jsonify(error.model_dump()), 500

        # レート制限チェック
        client_ip = _get_client_ip()
        if price_watch.webapi.auth_rate_limiter.is_locked_out(client_ip):
            remaining = price_watch.webapi.auth_rate_limiter.get_lockout_remaining_sec(client_ip)
            remaining_min = remaining // 60
            logging.warning("認証ロックアウト中: IP=%s, 残り%d分", client_ip, remaining_min)
            error = ErrorResponse(
                error=f"認証試行回数の上限を超えました。{remaining_min}分後に再試行してください。"
            )
            return flask.jsonify(error.model_dump()), 429

        # パスワード認証
        if not body.password or not price_watch.webapi.password.verify_password(
            body.password, app_config.edit.password_hash
        ):
            locked_out = price_watch.webapi.auth_rate_limiter.record_failure(client_ip)

            # 1時間ウィンドウで5回ごとにSlack通知
            notify_count = price_watch.webapi.auth_rate_limiter.record_failure_for_notify(client_ip)
            if notify_count is not None:
                logging.warning("認証失敗通知閾値到達: IP=%s, 回数=%d", client_ip, notify_count)
                price_watch.notify.auth_failure(app_config.slack, client_ip, notify_count)

            if locked_out:
                logging.warning("認証失敗上限到達、ロックアウト開始: IP=%s", client_ip)
                error = ErrorResponse(error="認証試行回数の上限を超えました。3時間後に再試行してください。")
                return flask.jsonify(error.model_dump()), 429
            logging.warning("認証失敗: IP=%s", client_ip)
            error = ErrorResponse(error="パスワードが正しくありません")
            return flask.jsonify(error.model_dump()), 401

        history_manager = _get_history_manager()
        if history_manager is None:
            error = ErrorResponse(error="データベースに接続できません")
            return flask.jsonify(error.model_dump()), 500

        # アイテム情報を取得
        item_id = history_manager.get_item_id(item_key=item_key)
        if item_id is None:
            error = ErrorResponse(error="アイテムが見つかりません")
            return flask.jsonify(error.model_dump()), 404

        # 削除対象の価格を取得（イベント削除用）
        prices = history_manager.get_prices_by_record_ids(body.record_ids)

        # 価格記録を削除
        deleted_records = history_manager.delete_price_records(body.record_ids)

        # 関連イベントを削除
        deleted_events = history_manager.delete_events_by_price(item_id, prices)

        # 削除後の最安値を取得
        new_lowest_price = history_manager.get_lowest_in_period(item_id)

        logging.info(
            "価格記録を削除: item_key=%s, records=%d, events=%d",
            item_key,
            deleted_records,
            deleted_events,
        )

        response = DeleteRecordsResponse(
            deleted_records=deleted_records,
            deleted_events=deleted_events,
            new_lowest_price=new_lowest_price,
        )

        return flask.jsonify(response.model_dump())

    except Exception:
        logging.exception("Error deleting records")
        error = ErrorResponse(error="価格記録の削除に失敗しました")
        return flask.jsonify(error.model_dump()), 500
