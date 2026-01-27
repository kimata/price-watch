#!/usr/bin/env python3
# ruff: noqa: S101, S108
"""
webapi/page.py のユニットテスト

Web API エンドポイントを検証します。
"""

from __future__ import annotations

import pathlib
from unittest.mock import MagicMock, patch

import flask
import pytest

import price_watch.managers.history
import price_watch.models
import price_watch.target
import price_watch.webapi.page


@pytest.fixture
def app() -> flask.Flask:
    """テスト用 Flask アプリケーション."""
    app = flask.Flask(__name__)
    app.register_blueprint(price_watch.webapi.page.blueprint, url_prefix="/price")
    app.config["TESTING"] = True
    return app


@pytest.fixture
def client(app: flask.Flask) -> flask.testing.FlaskClient:
    """テスト用クライアント."""
    return app.test_client()


class TestParseDays:
    """_parse_days 関数のテスト"""

    def test_parses_numeric_string(self) -> None:
        """数値文字列をパース"""
        assert price_watch.webapi.page._parse_days("30") == 30
        assert price_watch.webapi.page._parse_days("90") == 90

    def test_returns_none_for_all(self) -> None:
        """'all' の場合は None を返す"""
        assert price_watch.webapi.page._parse_days("all") is None

    def test_returns_none_for_none(self) -> None:
        """None の場合は None を返す"""
        assert price_watch.webapi.page._parse_days(None) is None

    def test_returns_default_for_invalid(self) -> None:
        """無効な文字列はデフォルト 30 を返す"""
        assert price_watch.webapi.page._parse_days("invalid") == 30


class TestCalcEffectivePrice:
    """_calc_effective_price 関数のテスト"""

    def test_calculates_effective_price(self) -> None:
        """実質価格を計算"""
        # 10% ポイント還元
        assert price_watch.webapi.page._calc_effective_price(1000, 10.0) == 900
        # 5% ポイント還元
        assert price_watch.webapi.page._calc_effective_price(1000, 5.0) == 950

    def test_returns_none_for_none_price(self) -> None:
        """価格が None の場合は None を返す"""
        assert price_watch.webapi.page._calc_effective_price(None, 10.0) is None

    def test_zero_point_rate(self) -> None:
        """ポイント還元率 0% の場合"""
        assert price_watch.webapi.page._calc_effective_price(1000, 0.0) == 1000


class TestGetPointRate:
    """_get_point_rate 関数のテスト"""

    def test_returns_store_point_rate(self) -> None:
        """ストアのポイント還元率を返す"""
        mock_store = MagicMock()
        mock_store.point_rate = 5.0
        mock_config = MagicMock()
        mock_config.get_store.return_value = mock_store

        result = price_watch.webapi.page._get_point_rate(mock_config, "TestStore")

        assert result == 5.0
        mock_config.get_store.assert_called_once_with("TestStore")

    def test_returns_zero_if_store_not_found(self) -> None:
        """ストアが見つからない場合は 0.0 を返す"""
        mock_config = MagicMock()
        mock_config.get_store.return_value = None

        result = price_watch.webapi.page._get_point_rate(mock_config, "Unknown")

        assert result == 0.0

    def test_returns_zero_if_config_is_none(self) -> None:
        """設定が None の場合は 0.0 を返す"""
        result = price_watch.webapi.page._get_point_rate(None, "TestStore")
        assert result == 0.0


class TestBuildHistoryEntries:
    """_build_history_entries 関数のテスト"""

    def test_builds_entries(self) -> None:
        """履歴エントリを構築"""
        history = [
            price_watch.models.PriceRecord(time="2024-01-15 10:00:00", price=1000, stock=1),
            price_watch.models.PriceRecord(time="2024-01-16 10:00:00", price=900, stock=1),
        ]

        result = price_watch.webapi.page._build_history_entries(history, 10.0)

        assert len(result) == 2
        assert result[0].price == 1000
        assert result[0].effective_price == 900
        assert result[1].price == 900
        assert result[1].effective_price == 810

    def test_handles_none_price(self) -> None:
        """価格が None の履歴も処理"""
        history = [
            price_watch.models.PriceRecord(time="2024-01-15 10:00:00", price=None, stock=0),
        ]

        result = price_watch.webapi.page._build_history_entries(history, 10.0)

        assert len(result) == 1
        assert result[0].price is None
        assert result[0].effective_price is None


class TestFindBestStore:
    """_find_best_store 関数のテスト"""

    def test_finds_cheapest_in_stock(self) -> None:
        """在庫ありの中で最安を返す"""
        store1 = MagicMock()
        store1.stock = 1
        store1.effective_price = 1000
        store2 = MagicMock()
        store2.stock = 1
        store2.effective_price = 800

        result = price_watch.webapi.page._find_best_store([store1, store2])

        assert result is store2

    def test_prefers_in_stock_over_out_of_stock(self) -> None:
        """在庫ありを優先"""
        store1 = MagicMock()
        store1.stock = 0
        store1.effective_price = 500
        store2 = MagicMock()
        store2.stock = 1
        store2.effective_price = 1000

        result = price_watch.webapi.page._find_best_store([store1, store2])

        assert result is store2

    def test_handles_all_out_of_stock(self) -> None:
        """全て在庫なしの場合は価格ありの最安"""
        store1 = MagicMock()
        store1.stock = 0
        store1.effective_price = 1000
        store2 = MagicMock()
        store2.stock = 0
        store2.effective_price = 800

        result = price_watch.webapi.page._find_best_store([store1, store2])

        assert result is store2

    def test_handles_all_none_prices(self) -> None:
        """全て価格なしの場合は最初を返す"""
        store1 = MagicMock()
        store1.stock = 0
        store1.effective_price = None
        store2 = MagicMock()
        store2.stock = 0
        store2.effective_price = None

        result = price_watch.webapi.page._find_best_store([store1, store2])

        assert result is store1


class TestFindFirstThumbUrl:
    """_find_first_thumb_url 関数のテスト"""

    def test_returns_first_thumb_url(self) -> None:
        """最初のサムネイル URL を返す"""
        data = [
            {"thumb_url": None},
            {"thumb_url": "http://example.com/thumb.png"},
            {"thumb_url": "http://example.com/thumb2.png"},
        ]

        result = price_watch.webapi.page._find_first_thumb_url(data)

        assert result == "http://example.com/thumb.png"

    def test_returns_none_if_no_thumb(self) -> None:
        """サムネイルがない場合は None を返す"""
        data = [
            {"thumb_url": None},
            {"thumb_url": None},
        ]

        result = price_watch.webapi.page._find_first_thumb_url(data)

        assert result is None


class TestEscapeHtml:
    """_escape_html 関数のテスト"""

    def test_escapes_special_chars(self) -> None:
        """特殊文字をエスケープ"""
        result = price_watch.webapi.page._escape_html('<script>alert("test")</script>')

        assert "&lt;" in result
        assert "&gt;" in result
        assert "&quot;" in result
        assert "&#x27;" not in result or "'" not in result


class TestEscapeJs:
    """_escape_js 関数のテスト"""

    def test_escapes_js_chars(self) -> None:
        """JavaScript 文字をエスケープ"""
        result = price_watch.webapi.page._escape_js('test"value\\n')

        assert '\\"' in result
        assert "\\\\" in result


class TestIsFacebookCrawler:
    """_is_facebook_crawler 関数のテスト"""

    def test_detects_facebook_crawler(self) -> None:
        """Facebook クローラーを検出"""
        assert price_watch.webapi.page._is_facebook_crawler(
            "facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)"
        )

    def test_returns_false_for_other_agents(self) -> None:
        """他のユーザーエージェントには False"""
        assert not price_watch.webapi.page._is_facebook_crawler("Mozilla/5.0")


class TestGetTargetItemKeys:
    """_get_target_item_keys 関数のテスト"""

    def test_returns_empty_set_for_none(self) -> None:
        """None の場合は空セット"""
        result = price_watch.webapi.page._get_target_item_keys(None)
        assert result == set()

    def test_generates_keys_from_resolved_items(self) -> None:
        """解決済みアイテムからキーを生成"""
        mock_item = MagicMock()
        mock_item.check_method = price_watch.target.CheckMethod.SCRAPE
        mock_item.url = "http://example.com/item"

        mock_config = MagicMock()
        mock_config.resolve_items.return_value = [mock_item]

        with patch("price_watch.managers.history.url_hash", return_value="hash123"):
            result = price_watch.webapi.page._get_target_item_keys(mock_config)

        assert "hash123" in result

    def test_handles_mercari_search(self) -> None:
        """メルカリ検索のキー生成"""
        mock_item = MagicMock()
        mock_item.check_method = price_watch.target.CheckMethod.MERCARI_SEARCH
        mock_item.search_keyword = "keyword"
        mock_item.name = "Item Name"

        mock_config = MagicMock()
        mock_config.resolve_items.return_value = [mock_item]

        with patch("price_watch.managers.history.generate_item_key", return_value="mercari_key"):
            result = price_watch.webapi.page._get_target_item_keys(mock_config)

        assert "mercari_key" in result

    def test_returns_empty_set_on_exception(self) -> None:
        """resolve_items が例外を投げた場合は空セット"""
        mock_config = MagicMock()
        mock_config.resolve_items.side_effect = Exception("Error")

        result = price_watch.webapi.page._get_target_item_keys(mock_config)

        assert result == set()


class TestGetTargetConfig:
    """_get_target_config 関数のテスト"""

    def test_returns_none_on_exception(self) -> None:
        """例外時は None を返す"""
        with patch.object(
            price_watch.webapi.page._target_config_cache,
            "get",
            side_effect=Exception("File not found"),
        ):
            result = price_watch.webapi.page._get_target_config()

        assert result is None


class TestGetStoreDefinitions:
    """_get_store_definitions 関数のテスト"""

    def test_returns_store_definitions(self) -> None:
        """ストア定義を返す"""
        mock_store = MagicMock()
        mock_store.name = "Store1"
        mock_store.point_rate = 5.0
        mock_store.color = "#ff0000"

        mock_config = MagicMock()
        mock_config.stores = [mock_store]

        result = price_watch.webapi.page._get_store_definitions(mock_config)

        assert len(result) == 1
        assert result[0].name == "Store1"
        assert result[0].point_rate == 5.0
        assert result[0].color == "#ff0000"

    def test_returns_empty_for_none(self) -> None:
        """None の場合は空リスト"""
        result = price_watch.webapi.page._get_store_definitions(None)
        assert result == []


class TestServeThumb:
    """serve_thumb エンドポイントのテスト"""

    def test_returns_thumb_image(self, client: flask.testing.FlaskClient, tmp_path: pathlib.Path) -> None:
        """サムネイル画像を返す"""
        thumb_file = tmp_path / "test.png"
        thumb_file.write_bytes(b"\x89PNG\r\n\x1a\n")

        with patch("price_watch.thumbnail.get_thumb_dir", return_value=tmp_path):
            response = client.get("/price/thumb/test.png")

        assert response.status_code == 200
        assert response.content_type == "image/png"

    def test_returns_404_for_missing_file(
        self, client: flask.testing.FlaskClient, tmp_path: pathlib.Path
    ) -> None:
        """ファイルがない場合は 404"""
        with patch("price_watch.thumbnail.get_thumb_dir", return_value=tmp_path):
            response = client.get("/price/thumb/missing.png")

        assert response.status_code == 404

    def test_rejects_invalid_filename(self, client: flask.testing.FlaskClient) -> None:
        """無効なファイル名を拒否"""
        response = client.get("/price/thumb/test.jpg")
        assert response.status_code == 404

        response = client.get("/price/thumb/../etc/passwd")
        assert response.status_code == 404


class TestGetItems:
    """get_items エンドポイントのテスト"""

    def test_returns_items(self, client: flask.testing.FlaskClient) -> None:
        """アイテム一覧を返す"""
        mock_items = [
            price_watch.models.ItemRecord(
                id=1,
                name="Item1",
                store="Store1",
                item_key="key1",
                url="http://example.com",
                thumb_url="http://example.com/thumb.png",
                search_keyword=None,
            )
        ]

        mock_history_manager = MagicMock()
        mock_history_manager.get_all_items.return_value = mock_items
        mock_history_manager.get_latest.return_value = None

        with (
            patch.object(price_watch.webapi.page._target_config_cache, "get", return_value=None),
            patch.object(price_watch.webapi.page, "_get_history_manager", return_value=mock_history_manager),
        ):
            response = client.get("/price/api/items")

        assert response.status_code == 200

    def test_handles_exception(self, client: flask.testing.FlaskClient) -> None:
        """例外時は 500 を返す"""
        mock_history_manager = MagicMock()
        mock_history_manager.get_all_items.side_effect = Exception("DB error")

        with (
            patch.object(price_watch.webapi.page._target_config_cache, "get", return_value=None),
            patch.object(price_watch.webapi.page, "_get_history_manager", return_value=mock_history_manager),
        ):
            response = client.get("/price/api/items")

        assert response.status_code == 500


class TestGetItemHistory:
    """get_item_history エンドポイントのテスト"""

    def test_returns_history(self, client: flask.testing.FlaskClient) -> None:
        """履歴を返す"""
        mock_item = price_watch.models.ItemRecord(
            id=1,
            item_key="key1",
            name="Item1",
            store="Store1",
            url="http://example.com",
            thumb_url=None,
            search_keyword=None,
        )
        mock_history = [price_watch.models.PriceRecord(time="2024-01-15 10:00:00", price=1000, stock=1)]

        mock_history_manager = MagicMock()
        mock_history_manager.get_history.return_value = (mock_item, mock_history)

        with (
            patch.object(price_watch.webapi.page._target_config_cache, "get", return_value=None),
            patch.object(price_watch.webapi.page, "_get_history_manager", return_value=mock_history_manager),
        ):
            response = client.get("/price/api/items/key1/history")

        assert response.status_code == 200
        data = response.get_json()
        assert "history" in data

    def test_returns_404_for_missing_item(self, client: flask.testing.FlaskClient) -> None:
        """アイテムがない場合は 404"""
        mock_history_manager = MagicMock()
        mock_history_manager.get_history.return_value = (None, [])

        with patch.object(price_watch.webapi.page, "_get_history_manager", return_value=mock_history_manager):
            response = client.get("/price/api/items/missing/history")

        assert response.status_code == 404


class TestGetItemEvents:
    """get_item_events エンドポイントのテスト"""

    def test_returns_events(self, client: flask.testing.FlaskClient) -> None:
        """イベントを返す"""
        mock_events = [
            price_watch.models.EventRecord(
                id=1,
                item_id=1,
                item_name="Item1",
                store="Store1",
                url="http://example.com",
                thumb_url=None,
                event_type="price_drop",
                price=900,
                old_price=1000,
                threshold_days=30,
                notified=True,
                created_at="2024-01-15 10:00:00",
            )
        ]

        mock_history_manager = MagicMock()
        mock_history_manager.get_item_events.return_value = mock_events

        # グローバル変数を直接設定
        original = price_watch.webapi.page._history_manager
        price_watch.webapi.page._history_manager = mock_history_manager
        try:
            with (
                patch("price_watch.event.format_event_message", return_value="Message"),
                patch("price_watch.event.format_event_title", return_value="Title"),
            ):
                response = client.get("/price/api/items/key1/events")
        finally:
            price_watch.webapi.page._history_manager = original

        assert response.status_code == 200
        data = response.get_json()
        assert "events" in data

    def test_returns_empty_for_no_events(self, client: flask.testing.FlaskClient) -> None:
        """イベントがない場合は空リスト"""
        mock_history_manager = MagicMock()
        mock_history_manager.get_item_events.return_value = []

        # グローバル変数を直接設定
        original = price_watch.webapi.page._history_manager
        price_watch.webapi.page._history_manager = mock_history_manager
        try:
            response = client.get("/price/api/items/key1/events")
        finally:
            price_watch.webapi.page._history_manager = original

        assert response.status_code == 200
        data = response.get_json()
        assert data["events"] == []

    def test_respects_limit(self, client: flask.testing.FlaskClient) -> None:
        """limit パラメータを尊重"""
        mock_history_manager = MagicMock()
        mock_history_manager.get_item_events.return_value = []

        # グローバル変数を直接設定
        original = price_watch.webapi.page._history_manager
        price_watch.webapi.page._history_manager = mock_history_manager
        try:
            client.get("/price/api/items/key1/events?limit=25")
        finally:
            price_watch.webapi.page._history_manager = original

        mock_history_manager.get_item_events.assert_called_once_with("key1", 25)


class TestGetEvents:
    """get_events エンドポイントのテスト"""

    def test_returns_events(self, client: flask.testing.FlaskClient) -> None:
        """イベント一覧を返す"""
        mock_events = [
            price_watch.models.EventRecord(
                id=1,
                item_id=1,
                item_name="Item1",
                store="Store1",
                url="http://example.com",
                thumb_url=None,
                event_type="price_drop",
                price=900,
                old_price=1000,
                threshold_days=30,
                notified=True,
                created_at="2024-01-15 10:00:00",
            )
        ]

        mock_history_manager = MagicMock()
        mock_history_manager.get_recent_events.return_value = mock_events

        # グローバル変数を直接設定
        original = price_watch.webapi.page._history_manager
        price_watch.webapi.page._history_manager = mock_history_manager
        try:
            with (
                patch("price_watch.event.format_event_message", return_value="Message"),
                patch("price_watch.event.format_event_title", return_value="Title"),
            ):
                response = client.get("/price/api/events")
        finally:
            price_watch.webapi.page._history_manager = original

        assert response.status_code == 200
        data = response.get_json()
        assert "events" in data


class TestTopPage:
    """top_page エンドポイントのテスト"""

    def test_returns_html(self, client: flask.testing.FlaskClient) -> None:
        """HTML を返す"""
        with patch.object(price_watch.webapi.page._config_cache, "get", return_value=None):
            response = client.get("/price/")

        assert response.status_code == 200
        assert response.content_type == "text/html; charset=utf-8"


class TestMetricsPage:
    """metrics_page エンドポイントのテスト"""

    def test_returns_html(self, client: flask.testing.FlaskClient) -> None:
        """HTML を返す"""
        with patch.object(price_watch.webapi.page._config_cache, "get", return_value=None):
            response = client.get("/price/metrics")

        assert response.status_code == 200
        assert response.content_type == "text/html; charset=utf-8"


class TestApiMetricsStatus:
    """api_metrics_status エンドポイントのテスト"""

    def test_returns_status(self, client: flask.testing.FlaskClient) -> None:
        """ステータスを返す"""
        mock_status = MagicMock()
        mock_status.is_running = True
        mock_status.session_id = 1
        mock_status.started_at = None
        mock_status.last_heartbeat_at = None
        mock_status.uptime_sec = 100
        mock_status.total_items = 10
        mock_status.success_items = 8
        mock_status.failed_items = 2

        mock_db = MagicMock()
        mock_db.get_current_session_status.return_value = mock_status

        with patch("price_watch.webapi.page._get_metrics_db", return_value=mock_db):
            response = client.get("/price/api/metrics/status")

        assert response.status_code == 200
        data = response.get_json()
        assert data["is_running"] is True

    def test_returns_503_without_db(self, client: flask.testing.FlaskClient) -> None:
        """DB がない場合は 503"""
        with patch("price_watch.webapi.page._get_metrics_db", return_value=None):
            response = client.get("/price/api/metrics/status")

        assert response.status_code == 503


class TestApiMetricsSessions:
    """api_metrics_sessions エンドポイントのテスト"""

    def test_returns_sessions(self, client: flask.testing.FlaskClient) -> None:
        """セッション一覧を返す"""
        mock_session = MagicMock()
        mock_session.id = 1
        mock_session.started_at.isoformat.return_value = "2024-01-15T10:00:00"
        mock_session.ended_at = None
        mock_session.duration_sec = 100
        mock_session.total_items = 10
        mock_session.success_items = 8
        mock_session.failed_items = 2
        mock_session.exit_reason = "normal"

        mock_db = MagicMock()
        mock_db.get_sessions.return_value = [mock_session]

        with patch("price_watch.webapi.page._get_metrics_db", return_value=mock_db):
            response = client.get("/price/api/metrics/sessions")

        assert response.status_code == 200
        data = response.get_json()
        assert "sessions" in data


class TestApiMetricsStores:
    """api_metrics_stores エンドポイントのテスト"""

    def test_returns_store_stats(self, client: flask.testing.FlaskClient) -> None:
        """ストア統計を返す"""
        mock_stat = MagicMock()
        mock_stat.id = 1
        mock_stat.session_id = 1
        mock_stat.store_name = "Store1"
        mock_stat.started_at.isoformat.return_value = "2024-01-15T10:00:00"
        mock_stat.ended_at = None
        mock_stat.duration_sec = 50
        mock_stat.item_count = 5
        mock_stat.success_count = 4
        mock_stat.failed_count = 1

        mock_db = MagicMock()
        mock_db.get_store_stats.return_value = [mock_stat]

        with patch("price_watch.webapi.page._get_metrics_db", return_value=mock_db):
            response = client.get("/price/api/metrics/stores")

        assert response.status_code == 200
        data = response.get_json()
        assert "store_stats" in data


class TestApiMetricsHeatmap:
    """api_metrics_heatmap エンドポイントのテスト"""

    def test_returns_heatmap(self, client: flask.testing.FlaskClient) -> None:
        """ヒートマップデータを返す"""
        mock_cell = MagicMock()
        mock_cell.date = "2024-01-15"
        mock_cell.hour = 10
        mock_cell.uptime_rate = 0.8

        mock_heatmap = MagicMock()
        mock_heatmap.dates = ["2024-01-15"]
        mock_heatmap.hours = [10]
        mock_heatmap.cells = [mock_cell]

        mock_db = MagicMock()
        mock_db.get_uptime_heatmap.return_value = mock_heatmap

        with patch("price_watch.webapi.page._get_metrics_db", return_value=mock_db):
            response = client.get("/price/api/metrics/heatmap")

        assert response.status_code == 200
        data = response.get_json()
        assert "cells" in data


class TestApiMetricsHeatmapSvg:
    """api_metrics_heatmap_svg エンドポイントのテスト"""

    def test_returns_svg(self, client: flask.testing.FlaskClient) -> None:
        """SVG を返す"""
        mock_cell = MagicMock()
        mock_cell.date = "2024-01-15"
        mock_cell.hour = 10
        mock_cell.uptime_rate = 0.8

        mock_heatmap = MagicMock()
        mock_heatmap.dates = ["2024-01-15"]
        mock_heatmap.hours = list(range(24))
        mock_heatmap.cells = [mock_cell]

        mock_db = MagicMock()
        mock_db.get_uptime_heatmap.return_value = mock_heatmap

        with patch("price_watch.webapi.page._get_metrics_db", return_value=mock_db):
            response = client.get("/price/api/metrics/heatmap.svg")

        assert response.status_code == 200
        assert response.content_type == "image/svg+xml; charset=utf-8"


class TestApiSysinfo:
    """api_sysinfo エンドポイントのテスト"""

    def test_returns_sysinfo(self, client: flask.testing.FlaskClient) -> None:
        """システム情報を返す"""
        response = client.get("/price/api/sysinfo")

        assert response.status_code == 200
        data = response.get_json()
        assert "date" in data
        assert "timezone" in data


class TestItemDetailPage:
    """item_detail_page エンドポイントのテスト"""

    def test_returns_html(self, client: flask.testing.FlaskClient) -> None:
        """HTML を返す"""
        mock_items = [
            price_watch.models.ItemRecord(
                id=1,
                name="Item1",
                store="Store1",
                item_key="key1",
                url="http://example.com",
                thumb_url=None,
                search_keyword=None,
            )
        ]

        mock_latest = price_watch.models.LatestPriceRecord(
            price=1000, stock=1, crawl_status=1, time="2024-01-15 10:00:00"
        )
        mock_stats = price_watch.models.ItemStats(lowest_price=900, highest_price=1100, data_count=10)

        mock_history_manager = MagicMock()
        mock_history_manager.get_all_items.return_value = mock_items
        mock_history_manager.get_latest.return_value = mock_latest
        mock_history_manager.get_stats.return_value = mock_stats
        mock_history_manager.get_history.return_value = (mock_items[0], [])

        with (
            patch.object(price_watch.webapi.page._target_config_cache, "get", return_value=None),
            patch.object(price_watch.webapi.page._config_cache, "get", return_value=None),
            patch.object(price_watch.webapi.page, "_get_history_manager", return_value=mock_history_manager),
        ):
            response = client.get("/price/items/key1")

        assert response.status_code == 200
        assert response.content_type == "text/html; charset=utf-8"

    def test_returns_404_for_missing_item(self, client: flask.testing.FlaskClient) -> None:
        """アイテムがない場合は 404"""
        mock_history_manager = MagicMock()
        mock_history_manager.get_all_items.return_value = []

        with (
            patch.object(price_watch.webapi.page._target_config_cache, "get", return_value=None),
            patch.object(price_watch.webapi.page, "_get_history_manager", return_value=mock_history_manager),
        ):
            response = client.get("/price/items/missing")

        assert response.status_code == 404


class TestOgpImage:
    """ogp_image エンドポイントのテスト"""

    def test_returns_404_for_missing_item(self, client: flask.testing.FlaskClient) -> None:
        """アイテムがない場合は 404"""
        mock_config = MagicMock()
        mock_config.data.cache = pathlib.Path("/tmp/cache")
        mock_config.data.thumb = pathlib.Path("/tmp/thumb")

        mock_history_manager = MagicMock()
        mock_history_manager.get_all_items.return_value = []

        with (
            patch.object(price_watch.webapi.page._config_cache, "get", return_value=mock_config),
            patch.object(price_watch.webapi.page._target_config_cache, "get", return_value=None),
            patch.object(price_watch.webapi.page, "_get_history_manager", return_value=mock_history_manager),
        ):
            response = client.get("/price/ogp/missing.png")

        assert response.status_code == 404

    def test_returns_500_without_config(self, client: flask.testing.FlaskClient) -> None:
        """設定がない場合は 500"""
        with patch.object(price_watch.webapi.page._config_cache, "get", return_value=None):
            response = client.get("/price/ogp/key1.png")

        assert response.status_code == 500


class TestGenerateHeatmapSvg:
    """_generate_heatmap_svg 関数のテスト"""

    def test_generates_svg(self) -> None:
        """SVG を生成"""
        mock_cell = MagicMock()
        mock_cell.date = "2024-01-15"
        mock_cell.hour = 10
        mock_cell.uptime_rate = 0.8

        mock_heatmap = MagicMock()
        mock_heatmap.dates = ["2024-01-15"]
        mock_heatmap.hours = list(range(24))
        mock_heatmap.cells = [mock_cell]

        result = price_watch.webapi.page._generate_heatmap_svg(mock_heatmap)

        assert b"<svg" in result
        assert b"</svg>" in result

    def test_handles_empty_data(self) -> None:
        """空データを処理"""
        mock_heatmap = MagicMock()
        mock_heatmap.dates = []
        mock_heatmap.hours = []
        mock_heatmap.cells = []

        result = price_watch.webapi.page._generate_heatmap_svg(mock_heatmap)

        assert b"No data" in result


class TestRenderTopPageHtml:
    """_render_top_page_html 関数のテスト"""

    def test_returns_fallback_html(self) -> None:
        """フォールバック HTML を返す"""
        result = price_watch.webapi.page._render_top_page_html(None)

        assert "<!DOCTYPE html>" in result
        assert "Price Watch" in result

    def test_uses_index_html(self, tmp_path: pathlib.Path) -> None:
        """index.html を使用"""
        index_file = tmp_path / "index.html"
        index_file.write_text("<!DOCTYPE html><html><head></head><body></body></html>")

        result = price_watch.webapi.page._render_top_page_html(tmp_path)

        assert "og:title" in result


class TestRenderOgpHtml:
    """_render_ogp_html 関数のテスト"""

    def test_generates_html_with_ogp_tags(self) -> None:
        """OGP タグ付き HTML を生成"""
        mock_store = MagicMock()
        mock_store.effective_price = 1000
        mock_store.store = "Store1"

        result = price_watch.webapi.page._render_ogp_html(
            item_key="key1",
            item_name="Test Item",
            best_store=mock_store,
            ogp_image_url="http://example.com/ogp.png",
            ogp_image_square_url="http://example.com/ogp_square.png",
            page_url="http://example.com/items/key1",
            static_dir=None,
            is_facebook=False,
        )

        assert "og:title" in result
        assert "Test Item" in result
        assert "Price Watch" in result


class TestBuildStoreEntry:
    """_build_store_entry 関数のテスト"""

    def test_builds_entry(self) -> None:
        """ストアエントリを構築"""
        item = price_watch.models.ItemRecord(
            id=1,
            item_key="key1",
            store="Store1",
            url="http://example.com",
            name="Item1",
            thumb_url=None,
            search_keyword=None,
        )
        latest = price_watch.models.LatestPriceRecord(
            price=1000, stock=1, crawl_status=1, time="2024-01-15 10:00:00"
        )
        stats = price_watch.models.ItemStats(lowest_price=900, highest_price=1100, data_count=10)
        history = [price_watch.models.PriceRecord(time="2024-01-15 10:00:00", price=1000, stock=1)]

        result = price_watch.webapi.page._build_store_entry(item, latest, stats, history, 10.0)

        assert result.item_key == "key1"
        assert result.store == "Store1"
        assert result.current_price == 1000
        assert result.effective_price == 900


class TestBuildStoreEntryWithoutHistory:
    """_build_store_entry_without_history_from_record 関数のテスト"""

    def test_builds_entry(self) -> None:
        """履歴なしストアエントリを構築"""
        item = price_watch.models.ItemRecord(
            id=1,
            item_key="key1",
            store="Store1",
            url="http://example.com",
            name="Item1",
            thumb_url=None,
            search_keyword=None,
        )

        result = price_watch.webapi.page._build_store_entry_without_history_from_record(item, 10.0)

        assert result.item_key == "key1"
        assert result.store == "Store1"
        assert result.current_price is None
        assert result.history == []


class TestProcessItem:
    """_process_item 関数のテスト"""

    def test_processes_item_with_history(self) -> None:
        """履歴ありアイテムを処理"""
        item = price_watch.models.ItemRecord(
            id=1,
            item_key="key1",
            store="Store1",
            url="http://example.com",
            name="Item1",
            thumb_url="http://example.com/thumb.png",
            search_keyword=None,
        )

        mock_latest = price_watch.models.LatestPriceRecord(
            price=1000, stock=1, crawl_status=1, time="2024-01-15"
        )
        mock_stats = price_watch.models.ItemStats(lowest_price=900, highest_price=1100, data_count=10)

        mock_history_manager = MagicMock()
        mock_history_manager.get_latest.return_value = mock_latest
        mock_history_manager.get_stats.return_value = mock_stats
        mock_history_manager.get_history.return_value = (item, [])

        with patch.object(price_watch.webapi.page, "_get_history_manager", return_value=mock_history_manager):
            result = price_watch.webapi.page._process_item(item, 30, None)

        assert result is not None
        assert result["store_entry"].store == "Store1"

    def test_handles_item_without_latest(self) -> None:
        """latest がないアイテムを処理"""
        item = price_watch.models.ItemRecord(
            id=1,
            item_key="key1",
            store="Store1",
            url="http://example.com",
            name="Item1",
            thumb_url=None,
            search_keyword=None,
        )

        mock_history_manager = MagicMock()
        mock_history_manager.get_latest.return_value = None

        with patch.object(price_watch.webapi.page, "_get_history_manager", return_value=mock_history_manager):
            result = price_watch.webapi.page._process_item(item, 30, None)

        assert result is not None
        assert result["store_entry"].current_price is None


class TestBuildResultItem:
    """_build_result_item 関数のテスト"""

    def test_builds_item(self) -> None:
        """結果アイテムを構築"""
        mock_store = MagicMock(spec=[])
        mock_store.item_key = "key1"
        mock_store.store = "Store1"
        mock_store.url = "http://example.com"
        mock_store.current_price = 1000
        mock_store.effective_price = 900
        mock_store.point_rate = 10.0
        mock_store.lowest_price = 800
        mock_store.highest_price = 1200
        mock_store.stock = 1
        mock_store.last_updated = "2024-01-15 10:00:00"
        mock_store.history = []
        mock_store.product_url = None
        mock_store.search_keyword = None

        store_data_list = [{"store_entry": mock_store, "thumb_url": "http://example.com/thumb.png"}]

        result = price_watch.webapi.page._build_result_item("Test Item", store_data_list)

        assert result.name == "Test Item"
        assert result.best_store == "Store1"
        assert result.thumb_url == "http://example.com/thumb.png"


class TestRenderOgpHtmlWithHistory:
    """_render_ogp_html 関数の履歴データ関連テスト"""

    def test_render_ogp_html_with_history_and_index(self, tmp_path: pathlib.Path) -> None:
        """履歴データと index.html がある場合"""
        # index.html を作成
        index_file = tmp_path / "index.html"
        index_file.write_text(
            """<!DOCTYPE html>
<html>
<head>
<title>Price Watch</title>
</head>
<body>
<div id="root"></div>
</body>
</html>"""
        )

        mock_store = MagicMock()
        mock_store.effective_price = 1500
        mock_store.store = "Store1"

        result = price_watch.webapi.page._render_ogp_html(
            item_key="test_key",
            item_name="テスト商品",
            best_store=mock_store,
            ogp_image_url="http://example.com/ogp.png",
            ogp_image_square_url="http://example.com/ogp_square.png",
            page_url="http://example.com/items/test_key",
            static_dir=tmp_path,
            is_facebook=False,
        )

        # OGP タグが挿入されている
        assert "og:title" in result
        assert "テスト商品" in result
        # 価格情報が含まれる
        assert "¥1,500" in result
        # item_key スクリプトが挿入されている
        assert "window.__ITEM_KEY__" in result
        assert "test_key" in result

    def test_render_ogp_html_facebook_crawler(self, tmp_path: pathlib.Path) -> None:
        """Facebook クローラーの場合は横長画像を使用"""
        index_file = tmp_path / "index.html"
        html_content = (
            "<!DOCTYPE html><html><head><title>Price Watch</title></head>"
            '<body><div id="root"></div></body></html>'
        )
        index_file.write_text(html_content)

        mock_store = MagicMock()
        mock_store.effective_price = 2000
        mock_store.store = "Store1"

        result = price_watch.webapi.page._render_ogp_html(
            item_key="key1",
            item_name="Item",
            best_store=mock_store,
            ogp_image_url="http://example.com/ogp.png",
            ogp_image_square_url="http://example.com/ogp_square.png",
            page_url="http://example.com/items/key1",
            static_dir=tmp_path,
            is_facebook=True,
        )

        # Facebook用に横長画像が og:image に設定される
        assert 'og:image" content="http://example.com/ogp.png"' in result

    def test_render_ogp_html_without_price(self) -> None:
        """価格がない場合"""
        mock_store = MagicMock()
        mock_store.effective_price = None
        mock_store.store = "Store1"

        result = price_watch.webapi.page._render_ogp_html(
            item_key="key1",
            item_name="Item",
            best_store=mock_store,
            ogp_image_url="http://example.com/ogp.png",
            ogp_image_square_url="http://example.com/ogp_square.png",
            page_url="http://example.com/items/key1",
            static_dir=None,
            is_facebook=False,
        )

        assert "価格未取得" in result


class TestRenderOgpHtmlFallback:
    """_render_ogp_html 関数のフォールバックテスト"""

    def test_render_ogp_html_index_read_failure(self, tmp_path: pathlib.Path) -> None:
        """index.html の読み込み失敗時はフォールバック HTML"""
        # 存在するが読み込み不可なディレクトリを設定
        mock_store = MagicMock()
        mock_store.effective_price = 1000
        mock_store.store = "Store1"

        with patch.object(pathlib.Path, "read_text", side_effect=PermissionError("Permission denied")):
            result = price_watch.webapi.page._render_ogp_html(
                item_key="key1",
                item_name="Item",
                best_store=mock_store,
                ogp_image_url="http://example.com/ogp.png",
                ogp_image_square_url="http://example.com/ogp_square.png",
                page_url="http://example.com/items/key1",
                static_dir=tmp_path,
                is_facebook=False,
            )

        # フォールバック HTML が生成される
        assert "<!DOCTYPE html>" in result
        assert "フロントエンド未ビルド" in result


class TestGenerateHeatmapSvgAdvanced:
    """_generate_heatmap_svg 関数の詳細テスト"""

    def test_generate_heatmap_svg_label_alignment(self) -> None:
        """ラベルの配置が正しいことを確認"""
        # 複数日のデータを作成
        mock_cells = []
        dates = ["2024-01-15", "2024-01-16", "2024-01-17"]
        for date in dates:
            for hour in range(24):
                cell = MagicMock()
                cell.date = date
                cell.hour = hour
                cell.uptime_rate = 0.9
                mock_cells.append(cell)

        mock_heatmap = MagicMock()
        mock_heatmap.dates = dates
        mock_heatmap.hours = list(range(24))
        mock_heatmap.cells = mock_cells

        result = price_watch.webapi.page._generate_heatmap_svg(mock_heatmap)

        # SVG 構造を確認
        assert b"<svg" in result
        assert b"</svg>" in result
        # 時間ラベル（0, 6, 12, 18, 24）が含まれる
        assert b">0<" in result
        assert b">6<" in result
        assert b">12<" in result
        assert b">18<" in result
        assert b">24<" in result
        # 日付ラベルが含まれる
        assert "月".encode() in result  # "1月15日(月)" のような形式

    def test_generate_heatmap_svg_color_mapping(self) -> None:
        """稼働率に応じた色分けを確認"""
        dates = ["2024-01-15"]
        hours = list(range(24))

        # 異なる稼働率のセルを作成
        mock_cells = []
        rates = [0.1, 0.3, 0.5, 0.7, 0.95]  # 各色に対応
        for i, rate in enumerate(rates):
            cell = MagicMock()
            cell.date = "2024-01-15"
            cell.hour = i
            cell.uptime_rate = rate
            mock_cells.append(cell)

        mock_heatmap = MagicMock()
        mock_heatmap.dates = dates
        mock_heatmap.hours = hours
        mock_heatmap.cells = mock_cells

        result = price_watch.webapi.page._generate_heatmap_svg(mock_heatmap)

        # 各色が SVG に含まれる
        assert b"#e0e0e0" in result  # 低稼働率
        assert b"#4caf50" in result  # 高稼働率

    def test_generate_heatmap_svg_weekend_colors(self) -> None:
        """土日のラベルに異なる色が適用されることを確認"""
        # 土曜と日曜を含むデータ
        dates = ["2024-01-20", "2024-01-21"]  # 土曜、日曜

        mock_cells = []
        for date in dates:
            cell = MagicMock()
            cell.date = date
            cell.hour = 0
            cell.uptime_rate = 0.8
            mock_cells.append(cell)

        mock_heatmap = MagicMock()
        mock_heatmap.dates = dates
        mock_heatmap.hours = [0]
        mock_heatmap.cells = mock_cells

        result = price_watch.webapi.page._generate_heatmap_svg(mock_heatmap)

        # 土曜・日曜用の CSS クラスが含まれる
        assert b"label-sat" in result
        assert b"label-sun" in result

    def test_generate_heatmap_svg_none_ratio(self) -> None:
        """稼働率が None のセルを処理"""
        cell = MagicMock()
        cell.date = "2024-01-15"
        cell.hour = 10
        cell.uptime_rate = None  # データなし

        mock_heatmap = MagicMock()
        mock_heatmap.dates = ["2024-01-15"]
        mock_heatmap.hours = [10]
        mock_heatmap.cells = [cell]

        result = price_watch.webapi.page._generate_heatmap_svg(mock_heatmap)

        # データなしの色が適用される
        assert b"#ebedf0" in result
        assert "データなし".encode() in result


class TestGetHistoryManager:
    """_get_history_manager 関数のテスト"""

    def test_get_history_manager_without_config(self) -> None:
        """設定がない場合は RuntimeError"""
        # グローバル変数をリセット
        original = price_watch.webapi.page._history_manager
        price_watch.webapi.page._history_manager = None
        try:
            with (
                patch.object(price_watch.webapi.page._config_cache, "get", return_value=None),
                pytest.raises(RuntimeError, match="App config not available"),
            ):
                price_watch.webapi.page._get_history_manager()
        finally:
            price_watch.webapi.page._history_manager = original

    def test_get_history_manager_cached(self) -> None:
        """キャッシュされた HistoryManager を返す"""
        mock_manager = MagicMock()
        original = price_watch.webapi.page._history_manager
        price_watch.webapi.page._history_manager = mock_manager
        try:
            result = price_watch.webapi.page._get_history_manager()
            assert result is mock_manager
        finally:
            price_watch.webapi.page._history_manager = original


class TestGroupItemsByName:
    """_group_items_by_name 関数のテスト"""

    def test_group_items_skips_non_target_items(self) -> None:
        """target.yaml にないアイテムはスキップ"""
        items = [
            price_watch.models.ItemRecord(
                id=1,
                item_key="key1",
                name="Item1",
                store="Store1",
                url="http://example.com",
                thumb_url=None,
                search_keyword=None,
            )
        ]

        mock_history_manager = MagicMock()
        mock_history_manager.get_latest.return_value = None

        # target_item_keys に key1 が含まれない
        target_keys = {"key2", "key3"}

        with patch.object(price_watch.webapi.page, "_get_history_manager", return_value=mock_history_manager):
            result = price_watch.webapi.page._group_items_by_name(
                items, target_keys, days=30, target_config=None
            )

        # key1 は含まれない
        assert "Item1" not in result

    def test_group_items_handles_resolve_exception(self) -> None:
        """resolve_items の例外を処理"""
        items: list[price_watch.models.ItemRecord] = []

        mock_config = MagicMock()
        mock_config.resolve_items.side_effect = Exception("Resolve error")

        mock_history_manager = MagicMock()

        with patch.object(price_watch.webapi.page, "_get_history_manager", return_value=mock_history_manager):
            result = price_watch.webapi.page._group_items_by_name(
                items, set(), days=30, target_config=mock_config
            )

        # 例外が発生してもクラッシュしない
        assert result == {}


class TestBuildOgpData:
    """_build_ogp_data 関数のテスト"""

    def test_build_ogp_data_with_thumb(self, tmp_path: pathlib.Path) -> None:
        """サムネイルがある場合"""
        # サムネイルファイルを作成
        thumb_filename = price_watch.thumbnail.get_thumb_filename("Test Item")
        thumb_file = tmp_path / thumb_filename
        thumb_file.write_bytes(b"\x89PNG")

        mock_store = MagicMock()
        mock_store.store = "Store1"
        mock_store.effective_price = 1000
        mock_store.lowest_price = 900
        mock_store.history = []
        mock_store.stock = 1  # 在庫あり

        stores = [mock_store]

        result = price_watch.webapi.page._build_ogp_data("Test Item", stores, None, tmp_path)

        assert result.item_name == "Test Item"
        assert result.thumb_path == thumb_file

    def test_build_ogp_data_without_thumb(self, tmp_path: pathlib.Path) -> None:
        """サムネイルがない場合"""
        mock_store = MagicMock()
        mock_store.store = "Store1"
        mock_store.effective_price = 1000
        mock_store.lowest_price = 900
        mock_store.history = []
        mock_store.stock = 1  # 在庫あり

        stores = [mock_store]

        result = price_watch.webapi.page._build_ogp_data("Test Item", stores, None, tmp_path)

        assert result.thumb_path is None

    def test_build_ogp_data_with_store_color(self, tmp_path: pathlib.Path) -> None:
        """ストアに色が設定されている場合"""
        mock_store = MagicMock()
        mock_store.store = "Store1"
        mock_store.effective_price = 1000
        mock_store.lowest_price = 900
        mock_store.history = []
        mock_store.stock = 1  # 在庫あり

        mock_store_def = MagicMock()
        mock_store_def.color = "#ff0000"

        mock_config = MagicMock()
        mock_config.get_store.return_value = mock_store_def

        stores = [mock_store]

        result = price_watch.webapi.page._build_ogp_data("Test Item", stores, mock_config, tmp_path)

        assert result.store_histories[0].color == "#ff0000"


class TestOgpImageSquare:
    """ogp_image_square エンドポイントのテスト"""

    def test_returns_404_for_missing_item(self, client: flask.testing.FlaskClient) -> None:
        """アイテムがない場合は 404"""
        mock_config = MagicMock()
        mock_config.data.cache = pathlib.Path("/tmp/cache")
        mock_config.data.thumb = pathlib.Path("/tmp/thumb")

        mock_history_manager = MagicMock()
        mock_history_manager.get_all_items.return_value = []

        with (
            patch.object(price_watch.webapi.page._config_cache, "get", return_value=mock_config),
            patch.object(price_watch.webapi.page._target_config_cache, "get", return_value=None),
            patch.object(price_watch.webapi.page, "_get_history_manager", return_value=mock_history_manager),
        ):
            response = client.get("/price/ogp/missing_square.png")

        assert response.status_code == 404

    def test_returns_500_without_config(self, client: flask.testing.FlaskClient) -> None:
        """設定がない場合は 500"""
        with patch.object(price_watch.webapi.page._config_cache, "get", return_value=None):
            response = client.get("/price/ogp/key1_square.png")

        assert response.status_code == 500


class TestGetItemDataForOgp:
    """_get_item_data_for_ogp 関数のテスト"""

    def test_returns_none_for_missing_item(self) -> None:
        """アイテムが見つからない場合は (None, []) を返す"""
        mock_history_manager = MagicMock()
        mock_history_manager.get_all_items.return_value = []

        with (
            patch.object(price_watch.webapi.page._target_config_cache, "get", return_value=None),
            patch.object(price_watch.webapi.page, "_get_history_manager", return_value=mock_history_manager),
        ):
            name, stores = price_watch.webapi.page._get_item_data_for_ogp("nonexistent")

        assert name is None
        assert stores == []

    def test_returns_item_data(self) -> None:
        """アイテムデータを返す"""
        mock_item = price_watch.models.ItemRecord(
            id=1,
            item_key="key1",
            name="Test Item",
            store="Store1",
            url="http://example.com",
            thumb_url=None,
            search_keyword=None,
        )

        mock_latest = price_watch.models.LatestPriceRecord(
            price=1000, stock=1, crawl_status=1, time="2024-01-15"
        )
        mock_stats = price_watch.models.ItemStats(lowest_price=900, highest_price=1100, data_count=10)

        mock_history_manager = MagicMock()
        mock_history_manager.get_all_items.return_value = [mock_item]
        mock_history_manager.get_latest.return_value = mock_latest
        mock_history_manager.get_stats.return_value = mock_stats
        mock_history_manager.get_history.return_value = (mock_item, [])

        with (
            patch.object(price_watch.webapi.page._target_config_cache, "get", return_value=None),
            patch.object(price_watch.webapi.page, "_get_history_manager", return_value=mock_history_manager),
        ):
            name, stores = price_watch.webapi.page._get_item_data_for_ogp("key1")

        assert name == "Test Item"
        assert len(stores) == 1
        assert stores[0].store == "Store1"


class TestOgpImageSuccess:
    """OGP 画像生成の成功パスのテスト"""

    def test_returns_png_image(self, client: flask.testing.FlaskClient, tmp_path: pathlib.Path) -> None:
        """OGP 画像を正常に返す"""
        # キャッシュディレクトリを作成
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        thumb_dir = tmp_path / "thumb"
        thumb_dir.mkdir()

        # OGP 画像ファイルを作成
        image_path = cache_dir / "test_key_ogp.png"
        image_path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

        mock_config = MagicMock()
        mock_config.data.cache = cache_dir
        mock_config.data.thumb = thumb_dir
        mock_config.font = None

        mock_item = price_watch.models.ItemRecord(
            id=1,
            item_key="test_key",
            name="Test Item",
            store="Store1",
            url="http://example.com",
            thumb_url=None,
            search_keyword=None,
        )

        mock_latest = price_watch.models.LatestPriceRecord(
            price=1000, stock=1, crawl_status=1, time="2024-01-15"
        )
        mock_stats = price_watch.models.ItemStats(lowest_price=900, highest_price=1100, data_count=10)

        mock_history_manager = MagicMock()
        mock_history_manager.get_all_items.return_value = [mock_item]
        mock_history_manager.get_latest.return_value = mock_latest
        mock_history_manager.get_stats.return_value = mock_stats
        mock_history_manager.get_history.return_value = (mock_item, [])

        with (
            patch.object(price_watch.webapi.page._config_cache, "get", return_value=mock_config),
            patch.object(price_watch.webapi.page._target_config_cache, "get", return_value=None),
            patch.object(price_watch.webapi.page, "_get_history_manager", return_value=mock_history_manager),
            patch("price_watch.webapi.ogp.get_or_generate_ogp_image", return_value=image_path),
        ):
            response = client.get("/price/ogp/test_key.png")

        assert response.status_code == 200
        assert response.content_type == "image/png"

    def test_returns_square_png_image(
        self, client: flask.testing.FlaskClient, tmp_path: pathlib.Path
    ) -> None:
        """正方形 OGP 画像を正常に返す"""
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        thumb_dir = tmp_path / "thumb"
        thumb_dir.mkdir()

        image_path = cache_dir / "test_key_ogp_square.png"
        image_path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

        mock_config = MagicMock()
        mock_config.data.cache = cache_dir
        mock_config.data.thumb = thumb_dir
        mock_config.font = None

        mock_item = price_watch.models.ItemRecord(
            id=1,
            item_key="test_key",
            name="Test Item",
            store="Store1",
            url="http://example.com",
            thumb_url=None,
            search_keyword=None,
        )

        mock_latest = price_watch.models.LatestPriceRecord(
            price=1000, stock=1, crawl_status=1, time="2024-01-15"
        )
        mock_stats = price_watch.models.ItemStats(lowest_price=900, highest_price=1100, data_count=10)

        mock_history_manager = MagicMock()
        mock_history_manager.get_all_items.return_value = [mock_item]
        mock_history_manager.get_latest.return_value = mock_latest
        mock_history_manager.get_stats.return_value = mock_stats
        mock_history_manager.get_history.return_value = (mock_item, [])

        with (
            patch.object(price_watch.webapi.page._config_cache, "get", return_value=mock_config),
            patch.object(price_watch.webapi.page._target_config_cache, "get", return_value=None),
            patch.object(price_watch.webapi.page, "_get_history_manager", return_value=mock_history_manager),
            patch("price_watch.webapi.ogp.get_or_generate_ogp_image_square", return_value=image_path),
        ):
            response = client.get("/price/ogp/test_key_square.png")

        assert response.status_code == 200
        assert response.content_type == "image/png"


class TestOgpImageException:
    """OGP 画像生成の例外処理テスト"""

    def test_returns_500_on_exception(
        self, client: flask.testing.FlaskClient, tmp_path: pathlib.Path
    ) -> None:
        """例外発生時は 500 を返す"""
        mock_config = MagicMock()
        mock_config.data.cache = tmp_path
        mock_config.data.thumb = tmp_path
        mock_config.font = None

        mock_item = price_watch.models.ItemRecord(
            id=1,
            item_key="key1",
            name="Item",
            store="Store",
            url="http://example.com",
            thumb_url=None,
            search_keyword=None,
        )
        mock_latest = price_watch.models.LatestPriceRecord(
            price=1000, stock=1, crawl_status=1, time="2024-01-15"
        )
        mock_stats = price_watch.models.ItemStats(lowest_price=900, highest_price=1100, data_count=10)

        mock_history_manager = MagicMock()
        mock_history_manager.get_all_items.return_value = [mock_item]
        mock_history_manager.get_latest.return_value = mock_latest
        mock_history_manager.get_stats.return_value = mock_stats
        mock_history_manager.get_history.return_value = (mock_item, [])

        with (
            patch.object(price_watch.webapi.page._config_cache, "get", return_value=mock_config),
            patch.object(price_watch.webapi.page._target_config_cache, "get", return_value=None),
            patch.object(price_watch.webapi.page, "_get_history_manager", return_value=mock_history_manager),
            patch("price_watch.webapi.ogp.get_or_generate_ogp_image", side_effect=Exception("OGP error")),
        ):
            response = client.get("/price/ogp/key1.png")

        assert response.status_code == 500

    def test_square_returns_500_on_exception(
        self, client: flask.testing.FlaskClient, tmp_path: pathlib.Path
    ) -> None:
        """正方形画像の例外発生時は 500 を返す"""
        mock_config = MagicMock()
        mock_config.data.cache = tmp_path
        mock_config.data.thumb = tmp_path
        mock_config.font = None

        mock_item = price_watch.models.ItemRecord(
            id=1,
            item_key="key1",
            name="Item",
            store="Store",
            url="http://example.com",
            thumb_url=None,
            search_keyword=None,
        )
        mock_latest = price_watch.models.LatestPriceRecord(
            price=1000, stock=1, crawl_status=1, time="2024-01-15"
        )
        mock_stats = price_watch.models.ItemStats(lowest_price=900, highest_price=1100, data_count=10)

        mock_history_manager = MagicMock()
        mock_history_manager.get_all_items.return_value = [mock_item]
        mock_history_manager.get_latest.return_value = mock_latest
        mock_history_manager.get_stats.return_value = mock_stats
        mock_history_manager.get_history.return_value = (mock_item, [])

        with (
            patch.object(price_watch.webapi.page._config_cache, "get", return_value=mock_config),
            patch.object(price_watch.webapi.page._target_config_cache, "get", return_value=None),
            patch.object(price_watch.webapi.page, "_get_history_manager", return_value=mock_history_manager),
            patch("price_watch.webapi.ogp.get_or_generate_ogp_image_square", side_effect=Exception("Error")),
        ):
            response = client.get("/price/ogp/key1_square.png")

        assert response.status_code == 500


class TestGetMetricsDb:
    """_get_metrics_db 関数のテスト"""

    def test_returns_none_without_config(self) -> None:
        """設定がない場合は None を返す"""
        with patch.object(price_watch.webapi.page._config_cache, "get", return_value=None):
            result = price_watch.webapi.page._get_metrics_db()
        assert result is None

    def test_returns_none_if_db_not_exists(self, tmp_path: pathlib.Path) -> None:
        """DB ファイルが存在しない場合は None を返す"""
        mock_config = MagicMock()
        mock_config.data.metrics = tmp_path  # metrics.db は存在しない

        with patch.object(price_watch.webapi.page._config_cache, "get", return_value=mock_config):
            result = price_watch.webapi.page._get_metrics_db()

        assert result is None

    def test_returns_none_on_exception(self) -> None:
        """例外発生時は None を返す"""
        with patch.object(
            price_watch.webapi.page._config_cache, "get", side_effect=Exception("Config error")
        ):
            result = price_watch.webapi.page._get_metrics_db()

        assert result is None


class TestPageExceptionHandling:
    """ページの例外処理テスト"""

    def test_top_page_exception_returns_500(self, client: flask.testing.FlaskClient) -> None:
        """トップページの例外発生時は 500"""
        with patch.object(
            price_watch.webapi.page, "_render_top_page_html", side_effect=Exception("Render error")
        ):
            response = client.get("/price/")

        assert response.status_code == 500

    def test_metrics_page_exception_returns_500(self, client: flask.testing.FlaskClient) -> None:
        """メトリクスページの例外発生時は 500"""
        with patch.object(
            price_watch.webapi.page, "_render_top_page_html", side_effect=Exception("Render error")
        ):
            response = client.get("/price/metrics")

        assert response.status_code == 500


class TestHeatmapSvgException:
    """ヒートマップ SVG の例外処理テスト"""

    def test_returns_503_without_db(self, client: flask.testing.FlaskClient) -> None:
        """DB がない場合は 503"""
        with patch.object(price_watch.webapi.page, "_get_metrics_db", return_value=None):
            response = client.get("/price/api/metrics/heatmap.svg")

        assert response.status_code == 503

    def test_returns_500_on_exception(self, client: flask.testing.FlaskClient) -> None:
        """例外発生時は 500"""
        mock_db = MagicMock()
        mock_db.get_uptime_heatmap.side_effect = Exception("DB error")

        with patch.object(price_watch.webapi.page, "_get_metrics_db", return_value=mock_db):
            response = client.get("/price/api/metrics/heatmap.svg")

        assert response.status_code == 500


class TestProcessItemWithoutDb:
    """_process_item_without_db 関数のテスト"""

    def test_builds_store_data(self) -> None:
        """DB にないアイテムのストアデータを構築"""
        item = price_watch.models.ItemRecord(
            id=0,
            item_key="key1",
            name="Item1",
            store="Store1",
            url="http://example.com",
            thumb_url="http://example.com/thumb.png",
            search_keyword=None,
        )

        result = price_watch.webapi.page._process_item_without_db(item, None)

        assert result is not None
        assert result["store_entry"].item_key == "key1"
        assert result["store_entry"].store == "Store1"
        assert result["thumb_url"] == "http://example.com/thumb.png"


class TestGroupItemsWithMercariSearch:
    """Mercari 検索アイテムを含むグループ化テスト"""

    def test_processes_mercari_search_items(self) -> None:
        """target.yaml の Mercari 検索アイテムを処理"""
        # DB から取得したアイテム（空）
        items: list[price_watch.models.ItemRecord] = []

        # target.yaml の Mercari 検索アイテム
        mock_mercari_item = MagicMock()
        mock_mercari_item.name = "Mercari Item"
        mock_mercari_item.store = "メルカリ"
        mock_mercari_item.url = None
        mock_mercari_item.search_keyword = "keyword"
        mock_mercari_item.check_method = price_watch.target.CheckMethod.MERCARI_SEARCH

        mock_config = MagicMock()
        mock_config.resolve_items.return_value = [mock_mercari_item]

        mock_history_manager = MagicMock()

        with (
            patch.object(price_watch.webapi.page, "_get_history_manager", return_value=mock_history_manager),
            patch.object(price_watch.managers.history, "generate_item_key", return_value="mercari_key"),
        ):
            result = price_watch.webapi.page._group_items_by_name(
                items, set(), days=30, target_config=mock_config
            )

        # Mercari アイテムが追加される
        assert "Mercari Item" in result


class TestHeatmapSvgLabelAlignment:
    """ヒートマップ SVG のラベル配置テスト"""

    def test_first_label_left_aligned_when_cutoff(self) -> None:
        """最初のラベルが見切れる場合は左寄せ"""
        # 1日だけのデータで最初のラベルが見切れやすい状況を作る
        dates = ["2024-01-15"]
        hours = list(range(24))

        mock_cells = []
        for hour in hours:
            cell = MagicMock()
            cell.date = "2024-01-15"
            cell.hour = hour
            cell.uptime_rate = 0.8
            mock_cells.append(cell)

        mock_heatmap = MagicMock()
        mock_heatmap.dates = dates
        mock_heatmap.hours = hours
        mock_heatmap.cells = mock_cells

        result = price_watch.webapi.page._generate_heatmap_svg(mock_heatmap)

        # SVG が正常に生成される
        assert b"<svg" in result
        assert b"</svg>" in result

    def test_last_label_right_aligned_when_cutoff(self) -> None:
        """最後のラベルが見切れる場合は右寄せ（多数の日付で確認）"""
        # 多数の日付でラベルが端に来る状況
        dates = [f"2024-01-{i:02d}" for i in range(15, 22)]  # 7日間
        hours = list(range(24))

        mock_cells = []
        for date in dates:
            for hour in hours:
                cell = MagicMock()
                cell.date = date
                cell.hour = hour
                cell.uptime_rate = 0.8
                mock_cells.append(cell)

        mock_heatmap = MagicMock()
        mock_heatmap.dates = dates
        mock_heatmap.hours = hours
        mock_heatmap.cells = mock_cells

        result = price_watch.webapi.page._generate_heatmap_svg(mock_heatmap)

        # SVG が正常に生成される
        assert b"<svg" in result
        # text-anchor 属性が使用されている
        assert b'text-anchor="' in result


class TestRenderTopPageHtmlException:
    """_render_top_page_html の例外処理テスト"""

    def test_handles_index_read_exception(self, tmp_path: pathlib.Path) -> None:
        """index.html の読み込み失敗時はフォールバック"""
        # ディレクトリは存在するがファイルを読めない状況をシミュレート
        static_dir = tmp_path / "static"
        static_dir.mkdir()
        index_file = static_dir / "index.html"
        index_file.write_text("valid html")

        with patch.object(pathlib.Path, "read_text", side_effect=PermissionError("Permission denied")):
            result = price_watch.webapi.page._render_top_page_html(static_dir)

        # フォールバック HTML が返される
        assert "フロントエンド未ビルド" in result


class TestGetHistoryManagerCreate:
    """_get_history_manager の HistoryManager 作成テスト"""

    def test_creates_history_manager(self, tmp_path: pathlib.Path) -> None:
        """設定から HistoryManager を作成"""
        mock_config = MagicMock()
        mock_config.data.price = tmp_path

        # グローバル変数をリセット
        original = price_watch.webapi.page._history_manager
        price_watch.webapi.page._history_manager = None

        mock_manager = MagicMock()
        mock_manager_class = MagicMock(return_value=mock_manager)

        try:
            with (
                patch.object(price_watch.webapi.page._config_cache, "get", return_value=mock_config),
                patch.object(price_watch.managers.history.HistoryManager, "create", mock_manager_class),
            ):
                result = price_watch.webapi.page._get_history_manager()

            assert result is mock_manager
            mock_manager.initialize.assert_called_once()
        finally:
            price_watch.webapi.page._history_manager = original
