#!/usr/bin/env python3
# ruff: noqa: S101
"""
Web API integration テスト

Flask テストクライアントを使用して API エンドポイントをテストします。
Pydantic スキーマに準拠していることを検証します。
"""

import unittest.mock
from collections.abc import Iterator
from datetime import timedelta
from typing import TYPE_CHECKING

import flask.testing
import my_lib.time
import pydantic
import pytest
import time_machine

import price_watch.webapi.schemas as schemas

if TYPE_CHECKING:
    from price_watch.managers.history import HistoryManager

# 時間単位で異なる時刻を生成するためのベース時刻
_BASE_TIME = my_lib.time.now().replace(hour=10, minute=0, second=0, microsecond=0)


@pytest.fixture(autouse=True)
def mock_history_manager(
    history_manager: "HistoryManager",
) -> Iterator["HistoryManager"]:
    """webapi.page の _get_history_manager をモックしてテスト用の history_manager を返す"""
    with unittest.mock.patch(
        "price_watch.webapi.page._get_history_manager",
        return_value=history_manager,
    ):
        yield history_manager


class TestItemsEndpoint:
    """GET /price/api/items エンドポイントのテスト"""

    def test_get_items_empty(self, client: flask.testing.FlaskClient) -> None:
        """アイテムがない場合は空のリストを返す"""
        with (
            unittest.mock.patch("price_watch.webapi.page._get_target_item_keys", return_value=set()),
            unittest.mock.patch("price_watch.webapi.page._get_target_config", return_value=None),
        ):
            response = client.get("/price/api/items")

        assert response.status_code == 200

        data = response.get_json()

        # Pydantic スキーマで検証
        parsed = schemas.ItemsResponse.model_validate(data)
        assert parsed.items == []
        assert parsed.store_definitions == []

    def test_get_items_with_data(
        self,
        client: flask.testing.FlaskClient,
        history_manager: "HistoryManager",
        sample_items: list[dict],
    ) -> None:
        """アイテムがある場合はリストを返す"""
        # サンプルデータを挿入
        for item in sample_items:
            history_manager.insert(item)

        # target.yaml がない状態でテスト（全アイテム表示）
        with (
            unittest.mock.patch("price_watch.webapi.page._get_target_item_keys", return_value=set()),
            unittest.mock.patch("price_watch.webapi.page._get_target_config", return_value=None),
        ):
            response = client.get("/price/api/items")

        assert response.status_code == 200

        data = response.get_json()

        # Pydantic スキーマで検証
        parsed = schemas.ItemsResponse.model_validate(data)

        # 商品Aと商品Bの2つの結果が返る
        assert len(parsed.items) == 2

        # 各アイテムのスキーマを検証
        for item in parsed.items:
            assert isinstance(item.name, str)
            assert len(item.stores) > 0
            assert isinstance(item.best_store, str)
            assert isinstance(item.best_effective_price, int)

    def test_get_items_with_days_param(
        self,
        client: flask.testing.FlaskClient,
        history_manager: "HistoryManager",
        sample_item: dict,
    ) -> None:
        """days パラメータが正しく処理される"""
        history_manager.insert(sample_item)

        with (
            unittest.mock.patch("price_watch.webapi.page._get_target_item_keys", return_value=set()),
            unittest.mock.patch("price_watch.webapi.page._get_target_config", return_value=None),
        ):
            response = client.get("/price/api/items?days=30")

        assert response.status_code == 200

        data = response.get_json()
        parsed = schemas.ItemsResponse.model_validate(data)
        assert isinstance(parsed.items, list)

    def test_get_items_with_all_days(
        self,
        client: flask.testing.FlaskClient,
        history_manager: "HistoryManager",
        sample_item: dict,
    ) -> None:
        """days=all で全期間のデータを取得"""
        history_manager.insert(sample_item)

        with (
            unittest.mock.patch("price_watch.webapi.page._get_target_item_keys", return_value=set()),
            unittest.mock.patch("price_watch.webapi.page._get_target_config", return_value=None),
        ):
            response = client.get("/price/api/items?days=all")

        assert response.status_code == 200

        data = response.get_json()
        parsed = schemas.ItemsResponse.model_validate(data)
        assert isinstance(parsed.items, list)

    def test_get_items_response_structure(
        self,
        client: flask.testing.FlaskClient,
        history_manager: "HistoryManager",
        sample_items: list[dict],
    ) -> None:
        """レスポンス構造が正しいこと"""
        for item in sample_items:
            history_manager.insert(item)

        with (
            unittest.mock.patch("price_watch.webapi.page._get_target_item_keys", return_value=set()),
            unittest.mock.patch("price_watch.webapi.page._get_target_config", return_value=None),
        ):
            response = client.get("/price/api/items")

        data = response.get_json()

        # トップレベルのキーを検証
        assert "items" in data
        assert "store_definitions" in data

        # items の各要素の構造を検証
        for item in data["items"]:
            assert "name" in item
            assert "thumb_url" in item
            assert "stores" in item
            assert "best_store" in item
            assert "best_effective_price" in item

            # stores の各要素の構造を検証
            for store in item["stores"]:
                assert "item_key" in store
                assert "store" in store
                assert "url" in store
                assert "current_price" in store
                assert "effective_price" in store
                assert "point_rate" in store
                assert "lowest_price" in store
                assert "highest_price" in store
                assert "stock" in store
                assert "last_updated" in store
                assert "history" in store


class TestItemHistoryEndpoint:
    """GET /price/api/items/<item_key>/history エンドポイントのテスト"""

    def test_get_history_not_found(self, client: flask.testing.FlaskClient) -> None:
        """存在しないアイテムの場合は 404 を返す"""
        response = client.get("/price/api/items/nonexistent123/history")

        assert response.status_code == 404

        data = response.get_json()

        # エラーレスポンスの検証
        parsed = schemas.ErrorResponse.model_validate(data)
        assert parsed.error == "Item not found"

    def test_get_history_success(
        self,
        client: flask.testing.FlaskClient,
        history_manager: "HistoryManager",
        sample_item: dict,
    ) -> None:
        """アイテムの履歴を取得"""
        # データを挿入
        history_manager.insert(sample_item)

        # item_key を取得
        all_items = history_manager.get_all_items()
        item_key = all_items[0].item_key

        response = client.get(f"/price/api/items/{item_key}/history")

        assert response.status_code == 200

        data = response.get_json()

        # Pydantic スキーマで検証
        parsed = schemas.HistoryResponse.model_validate(data)
        assert len(parsed.history) == 1

        # 履歴エントリの内容を検証
        entry = parsed.history[0]
        assert entry.price == sample_item["price"]
        assert entry.stock == sample_item["stock"]
        assert entry.effective_price == sample_item["price"]  # point_rate=0 の場合

    def test_get_history_with_multiple_entries(
        self,
        client: flask.testing.FlaskClient,
        history_manager: "HistoryManager",
        sample_item: dict,
    ) -> None:
        """複数の履歴エントリがある場合

        Note: insert は1時間単位で重複排除するため、異なる時間帯で挿入する必要がある
        """
        # 1回目: 10:00
        with time_machine.travel(_BASE_TIME, tick=False):
            history_manager.insert(sample_item)

        # 2回目: 11:00
        with time_machine.travel(_BASE_TIME + timedelta(hours=1), tick=False):
            modified_item = sample_item.copy()
            modified_item["price"] = 900
            history_manager.insert(modified_item)

        # 3回目: 12:00
        with time_machine.travel(_BASE_TIME + timedelta(hours=2), tick=False):
            modified_item = sample_item.copy()
            modified_item["price"] = 800
            history_manager.insert(modified_item)

        # item_key を取得
        all_items = history_manager.get_all_items()
        item_key = all_items[0].item_key

        # days=all で全期間を指定（デフォルトは30日）
        response = client.get(f"/price/api/items/{item_key}/history?days=all")

        assert response.status_code == 200

        data = response.get_json()
        parsed = schemas.HistoryResponse.model_validate(data)

        assert len(parsed.history) == 3

    def test_get_history_with_days_param(
        self,
        client: flask.testing.FlaskClient,
        history_manager: "HistoryManager",
        sample_item: dict,
    ) -> None:
        """days パラメータが正しく処理される"""
        history_manager.insert(sample_item)

        all_items = history_manager.get_all_items()
        item_key = all_items[0].item_key

        response = client.get(f"/price/api/items/{item_key}/history?days=30")

        assert response.status_code == 200

        data = response.get_json()
        parsed = schemas.HistoryResponse.model_validate(data)
        assert isinstance(parsed.history, list)


class TestPydanticValidation:
    """Pydantic スキーマの検証テスト"""

    def test_items_response_invalid_data(self) -> None:
        """無効なデータで ItemsResponse がエラーになる"""
        with pytest.raises(pydantic.ValidationError):
            schemas.ItemsResponse.model_validate({"items": "invalid"})

    def test_store_entry_required_fields(self) -> None:
        """StoreEntry の必須フィールドが欠けるとエラー"""
        with pytest.raises(pydantic.ValidationError):
            schemas.StoreEntry.model_validate({"store": "test"})  # 他の必須フィールドが欠けている

    def test_price_history_point_validation(self) -> None:
        """PriceHistoryPoint の検証"""
        entry = schemas.PriceHistoryPoint.model_validate(
            {
                "time": "2024-01-01 12:00:00",
                "price": 1000,
                "effective_price": 900,
                "stock": 5,
            }
        )
        assert entry.time == "2024-01-01 12:00:00"
        assert entry.price == 1000
        assert entry.effective_price == 900
        assert entry.stock == 5

    def test_result_item_validation(self) -> None:
        """ResultItem の検証"""
        store = schemas.StoreEntry.model_validate(
            {
                "item_key": "abc123",
                "store": "test-store.com",
                "url": "https://test-store.com/item/1",
                "current_price": 1000,
                "effective_price": 900,
                "point_rate": 10.0,
                "lowest_price": 800,
                "highest_price": 1200,
                "stock": 5,
                "last_updated": "2024-01-01 12:00:00",
                "history": [],
            }
        )

        item = schemas.ResultItem.model_validate(
            {
                "name": "テスト商品",
                "thumb_url": None,
                "stores": [store.model_dump()],
                "best_store": "test-store.com",
                "best_effective_price": 900,
            }
        )

        assert item.name == "テスト商品"
        assert len(item.stores) == 1
        assert item.best_store == "test-store.com"


class TestErrorHandling:
    """エラーハンドリングのテスト"""

    def test_internal_error_returns_500(
        self,
        client: flask.testing.FlaskClient,
    ) -> None:
        """内部エラーが発生した場合は 500 を返す"""
        # _get_history_manager をモックしてエラーを発生させる
        mock_manager = unittest.mock.MagicMock()
        mock_manager.get_all_items.side_effect = Exception("Database error")

        with unittest.mock.patch(
            "price_watch.webapi.page._get_history_manager",
            return_value=mock_manager,
        ):
            response = client.get("/price/api/items")

        assert response.status_code == 500

        data = response.get_json()
        parsed = schemas.ErrorResponse.model_validate(data)
        # エラーメッセージにはデバッグ用の詳細情報が含まれる場合がある
        assert parsed.error.startswith("Internal server error")
