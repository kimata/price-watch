#!/usr/bin/env python3
# ruff: noqa: S101
"""
processor.py のユニットテスト

アイテム処理の共通ロジックを検証します。
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import selenium.common.exceptions

import price_watch.models
import price_watch.processor
from price_watch.target import CheckMethod, ResolvedItem


def _create_resolved_item(
    name: str = "Test",
    store: str = "test-store.com",
    url: str = "https://example.com/item",
    check_method: CheckMethod = CheckMethod.SCRAPE,
    asin: str | None = None,
    search_keyword: str | None = None,
) -> ResolvedItem:
    """テスト用の ResolvedItem を作成."""
    return ResolvedItem(
        name=name,
        store=store,
        url=url,
        check_method=check_method,
        asin=asin,
        search_keyword=search_keyword,
    )


class TestItemProcessorProperties:
    """ItemProcessor のプロパティテスト"""

    def test_config_returns_app_config(self) -> None:
        """config は app の config を返す"""
        mock_app = MagicMock()
        mock_config = MagicMock()
        mock_app.config = mock_config

        processor = price_watch.processor.ItemProcessor(app=mock_app)

        assert processor.config is mock_config


class TestProcessAll:
    """process_all メソッドのテスト"""

    def test_calls_all_processors(self) -> None:
        """全プロセッサーを呼び出す"""
        mock_app = MagicMock()
        processor = price_watch.processor.ItemProcessor(app=mock_app)

        with (
            patch.object(processor, "process_scrape_items") as mock_scrape,
            patch.object(processor, "process_amazon_items") as mock_amazon,
            patch.object(processor, "process_mercari_items") as mock_mercari,
        ):
            processor.process_all([])

        mock_scrape.assert_called_once()
        mock_amazon.assert_called_once()
        mock_mercari.assert_called_once()


class TestProcessScrapeItems:
    """process_scrape_items メソッドのテスト"""

    def test_returns_early_if_no_driver(self) -> None:
        """driver がない場合は早期リターン"""
        mock_app = MagicMock()
        mock_app.browser_manager.driver = None
        processor = price_watch.processor.ItemProcessor(app=mock_app)

        processor.process_scrape_items([])
        # No exception raised

    def test_filters_scrape_items(self) -> None:
        """スクレイピング対象をフィルタリング"""
        mock_app = MagicMock()
        mock_app.browser_manager.driver = MagicMock()
        mock_app.should_terminate = False
        mock_app.debug_mode = False
        processor = price_watch.processor.ItemProcessor(app=mock_app)

        items = [
            _create_resolved_item(name="Item1", check_method=CheckMethod.SCRAPE, store="store1"),
            _create_resolved_item(name="Item2", check_method=CheckMethod.AMAZON_PAAPI, store="amazon"),
        ]

        with (
            patch.object(processor, "_process_scrape_item", return_value=True),
            patch.object(mock_app, "wait_for_terminate", return_value=False),
        ):
            processor.process_scrape_items(items)

        # スクレイピングアイテムのみ処理される

    def test_returns_on_terminate(self) -> None:
        """終了フラグで早期リターン"""
        mock_app = MagicMock()
        mock_app.browser_manager.driver = MagicMock()
        mock_app.should_terminate = True
        mock_app.debug_mode = False
        processor = price_watch.processor.ItemProcessor(app=mock_app)

        items = [_create_resolved_item(name="Item1", check_method=CheckMethod.SCRAPE, store="store1")]

        processor.process_scrape_items(items)
        # Early return, no processing

    def test_debug_mode_selects_one_per_store(self) -> None:
        """デバッグモードではストアごとに1アイテム"""
        mock_app = MagicMock()
        mock_app.browser_manager.driver = MagicMock()
        mock_app.should_terminate = False
        mock_app.debug_mode = True
        processor = price_watch.processor.ItemProcessor(app=mock_app)

        items = [
            _create_resolved_item(name="Item1", check_method=CheckMethod.SCRAPE, store="store1"),
            _create_resolved_item(name="Item2", check_method=CheckMethod.SCRAPE, store="store1"),
            _create_resolved_item(name="Item3", check_method=CheckMethod.SCRAPE, store="store2"),
        ]

        processed_items: list[ResolvedItem] = []

        def track_process(item: ResolvedItem, store_name: str) -> bool:
            del store_name  # Unused in mock
            processed_items.append(item)
            return True

        with (
            patch.object(processor, "_process_scrape_item", side_effect=track_process),
            patch.object(mock_app, "wait_for_terminate", return_value=False),
        ):
            processor.process_scrape_items(items)

        # 2ストアから1アイテムずつ
        assert len(processed_items) == 2


class TestProcessScrapeItem:
    """_process_scrape_item メソッドのテスト"""

    def test_returns_false_if_no_driver(self) -> None:
        """driver がない場合は False"""
        mock_app = MagicMock()
        mock_app.browser_manager.driver = None
        processor = price_watch.processor.ItemProcessor(app=mock_app)

        item = _create_resolved_item()
        result = processor._process_scrape_item(item, "store")

        assert result is False

    def test_successful_scrape(self) -> None:
        """成功時の処理"""
        mock_app = MagicMock()
        mock_app.browser_manager.driver = MagicMock()
        mock_app.debug_mode = False
        mock_config = MagicMock()
        mock_app.config = mock_config
        processor = price_watch.processor.ItemProcessor(app=mock_app)

        item = _create_resolved_item(name="Test", url="https://example.com")

        mock_checked = price_watch.models.CheckedItem.from_resolved_item(item)
        mock_checked.crawl_status = price_watch.models.CrawlStatus.SUCCESS

        with (
            patch("price_watch.store.scrape.check", return_value=mock_checked),
            patch.object(processor, "_process_data"),
        ):
            result = processor._process_scrape_item(item, "store")

        assert result is True

    def test_handles_invalid_session_exception(self) -> None:
        """InvalidSessionIdException を処理"""
        mock_app = MagicMock()
        mock_app.browser_manager.driver = MagicMock()
        mock_app.browser_manager.recreate_driver.return_value = True
        mock_app.debug_mode = False
        mock_config = MagicMock()
        mock_app.config = mock_config
        processor = price_watch.processor.ItemProcessor(app=mock_app)

        item = _create_resolved_item(name="Test", url="https://example.com")

        with (
            patch(
                "price_watch.store.scrape.check",
                side_effect=selenium.common.exceptions.InvalidSessionIdException(),
            ),
            patch.object(processor, "_process_data"),
        ):
            result = processor._process_scrape_item(item, "store")

        assert result is False
        mock_app.browser_manager.recreate_driver.assert_called_once()

    def test_handles_exception(self) -> None:
        """一般的な例外を処理"""
        mock_app = MagicMock()
        mock_app.browser_manager.driver = MagicMock()
        mock_app.debug_mode = False
        mock_config = MagicMock()
        mock_app.config = mock_config
        processor = price_watch.processor.ItemProcessor(app=mock_app)

        item = _create_resolved_item(name="Test", url="https://example.com")

        with (
            patch("price_watch.store.scrape.check", side_effect=Exception("Error")),
            patch.object(processor, "_process_data"),
        ):
            result = processor._process_scrape_item(item, "store")

        assert result is False


class TestProcessAmazonItems:
    """process_amazon_items メソッドのテスト"""

    def test_returns_early_if_no_items(self) -> None:
        """アイテムがない場合は早期リターン"""
        mock_app = MagicMock()
        processor = price_watch.processor.ItemProcessor(app=mock_app)

        processor.process_amazon_items([])
        # No exception raised

    def test_processes_amazon_items(self) -> None:
        """Amazon アイテムを処理"""
        mock_app = MagicMock()
        mock_app.debug_mode = False
        mock_config = MagicMock()
        mock_config.check.drop = None
        mock_app.config = mock_config
        mock_app.history_manager.insert_checked_item.return_value = 1
        mock_app.history_manager.get_last.return_value = None
        processor = price_watch.processor.ItemProcessor(app=mock_app)

        items = [
            _create_resolved_item(
                name="Item1", check_method=CheckMethod.AMAZON_PAAPI, asin="B001", store="amazon"
            ),
            _create_resolved_item(name="Item2", check_method=CheckMethod.SCRAPE, url="https://example.com"),
        ]

        mock_checked = price_watch.models.CheckedItem(
            name="Item1",
            store="amazon",
            url="https://amazon.com/B001",
            stock=price_watch.models.StockStatus.IN_STOCK,
            crawl_status=price_watch.models.CrawlStatus.SUCCESS,
        )

        with patch(
            "price_watch.store.amazon.paapi.check_item_list",
            return_value=[mock_checked],
        ):
            processor.process_amazon_items(items)

        # 1つ以上のアイテムを処理した場合は update_liveness が呼ばれる
        mock_app.update_liveness.assert_called_once()

    def test_debug_mode_limits_to_one(self) -> None:
        """デバッグモードでは1アイテムのみ"""
        mock_app = MagicMock()
        mock_app.debug_mode = True
        mock_config = MagicMock()
        mock_app.config = mock_config
        mock_app.history_manager.insert_checked_item.return_value = 1
        mock_app.history_manager.get_last.return_value = None
        processor = price_watch.processor.ItemProcessor(app=mock_app)

        items = [
            _create_resolved_item(
                name="Item1", check_method=CheckMethod.AMAZON_PAAPI, asin="B001", store="amazon"
            ),
            _create_resolved_item(
                name="Item2", check_method=CheckMethod.AMAZON_PAAPI, asin="B002", store="amazon"
            ),
        ]

        received_items: list[ResolvedItem] = []

        def check_mock(
            *args: object,
        ) -> list[price_watch.models.CheckedItem]:
            # args[0] is config, args[1] is item_list
            item_list = args[1]
            if isinstance(item_list, list):
                received_items.extend(item_list)  # type: ignore[arg-type]
            return []

        with patch("price_watch.store.amazon.paapi.check_item_list", side_effect=check_mock):
            processor.process_amazon_items(items)

        # デバッグモードでは1アイテムのリストで呼ばれる
        assert len(received_items) == 1

    def test_handles_exception(self) -> None:
        """例外を処理"""
        mock_app = MagicMock()
        mock_app.debug_mode = False
        mock_config = MagicMock()
        mock_app.config = mock_config
        processor = price_watch.processor.ItemProcessor(app=mock_app)

        items = [
            _create_resolved_item(
                name="Item1", check_method=CheckMethod.AMAZON_PAAPI, asin="B001", store="amazon"
            )
        ]

        with patch("price_watch.store.amazon.paapi.check_item_list", side_effect=Exception("Error")):
            processor.process_amazon_items(items)
        # No exception raised


class TestProcessMercariItems:
    """process_mercari_items メソッドのテスト"""

    def test_returns_early_if_no_driver(self) -> None:
        """driver がない場合は早期リターン"""
        mock_app = MagicMock()
        mock_app.browser_manager.driver = None
        processor = price_watch.processor.ItemProcessor(app=mock_app)

        processor.process_mercari_items([])
        # No exception raised

    def test_returns_early_if_no_items(self) -> None:
        """アイテムがない場合は早期リターン"""
        mock_app = MagicMock()
        mock_app.browser_manager.driver = MagicMock()
        processor = price_watch.processor.ItemProcessor(app=mock_app)

        processor.process_mercari_items([])
        # No exception raised


class TestProcessMercariItem:
    """_process_mercari_item メソッドのテスト"""

    def test_returns_false_if_no_driver(self) -> None:
        """driver がない場合は False"""
        mock_app = MagicMock()
        mock_app.browser_manager.driver = None
        processor = price_watch.processor.ItemProcessor(app=mock_app)

        item = _create_resolved_item(check_method=CheckMethod.MERCARI_SEARCH)
        result = processor._process_mercari_item(item, "store")

        assert result is False

    def test_successful_check(self) -> None:
        """成功時の処理"""
        mock_app = MagicMock()
        mock_app.browser_manager.driver = MagicMock()
        mock_app.debug_mode = False
        mock_config = MagicMock()
        mock_app.config = mock_config
        processor = price_watch.processor.ItemProcessor(app=mock_app)

        item = _create_resolved_item(
            name="Test", search_keyword="test", check_method=CheckMethod.MERCARI_SEARCH
        )

        mock_checked = price_watch.models.CheckedItem.from_resolved_item(item)
        mock_checked.crawl_status = price_watch.models.CrawlStatus.SUCCESS

        with (
            patch("price_watch.store.mercari.generate_item_key", return_value="key123"),
            patch("price_watch.store.mercari.check", return_value=mock_checked),
            patch.object(processor, "_process_data"),
        ):
            result = processor._process_mercari_item(item, "mercari.com")

        assert result is True

    def test_handles_invalid_session_exception(self) -> None:
        """InvalidSessionIdException を処理"""
        mock_app = MagicMock()
        mock_app.browser_manager.driver = MagicMock()
        mock_app.browser_manager.recreate_driver.return_value = True
        mock_app.debug_mode = False
        mock_config = MagicMock()
        mock_app.config = mock_config
        processor = price_watch.processor.ItemProcessor(app=mock_app)

        item = _create_resolved_item(
            name="Test", search_keyword="test", check_method=CheckMethod.MERCARI_SEARCH
        )

        with (
            patch("price_watch.store.mercari.generate_item_key", return_value="key123"),
            patch(
                "price_watch.store.mercari.check",
                side_effect=selenium.common.exceptions.InvalidSessionIdException(),
            ),
            patch.object(processor, "_process_data"),
        ):
            result = processor._process_mercari_item(item, "mercari.com")

        assert result is False
        mock_app.browser_manager.recreate_driver.assert_called_once()


class TestProcessData:
    """_process_data メソッドのテスト"""

    def test_inserts_history(self) -> None:
        """履歴を挿入"""
        mock_app = MagicMock()
        mock_config = MagicMock()
        mock_config.check.drop = None
        mock_app.config = mock_config
        mock_app.history_manager.insert_checked_item.return_value = 1
        mock_app.history_manager.get_last.return_value = None
        processor = price_watch.processor.ItemProcessor(app=mock_app)

        item = price_watch.models.CheckedItem(
            name="Test",
            store="store",
            url="https://example.com",
            crawl_status=price_watch.models.CrawlStatus.SUCCESS,
        )

        result = processor._process_data(item)

        assert result is True

    def test_handles_existing_item(self) -> None:
        """既存アイテムの更新"""
        mock_app = MagicMock()
        mock_config = MagicMock()
        mock_config.check.drop = None
        mock_app.config = mock_config
        mock_app.history_manager.insert_checked_item.return_value = 1
        # PriceHistoryRecord を返すようにする
        mock_last = MagicMock()
        mock_last.price = 900
        mock_last.stock = 1
        mock_app.history_manager.get_last.return_value = mock_last
        processor = price_watch.processor.ItemProcessor(app=mock_app)

        item = price_watch.models.CheckedItem(
            name="Test",
            store="store",
            url="https://example.com",
            price=1000,
            crawl_status=price_watch.models.CrawlStatus.SUCCESS,
        )

        result = processor._process_data(item)

        assert result is True
        assert item.old_price == 900


class TestCheckAndNotifyEvents:
    """_check_and_notify_events メソッドのテスト"""

    def test_checks_back_in_stock(self) -> None:
        """在庫復活を判定"""
        mock_app = MagicMock()
        mock_config = MagicMock()
        mock_config.check.drop = MagicMock()
        mock_config.check.drop.ignore.hour = 24
        mock_config.check.drop.windows = []
        mock_config.check.lowest = None
        mock_config.check.currency = []
        mock_app.config = mock_config
        processor = price_watch.processor.ItemProcessor(app=mock_app)

        item = price_watch.models.CheckedItem(
            name="Test",
            store="store",
            url="https://example.com",
            price=1000,
            stock=price_watch.models.StockStatus.IN_STOCK,
            crawl_status=price_watch.models.CrawlStatus.SUCCESS,
        )
        # PriceHistoryRecord のモック
        mock_last = MagicMock()
        mock_last.stock = 0

        mock_result = MagicMock()
        mock_result.should_notify = True
        mock_result.price = None

        with (
            patch("price_watch.event.check_back_in_stock", return_value=mock_result),
            patch("price_watch.event.check_lowest_price", return_value=None),
            patch.object(processor, "_notify_and_record_event"),
        ):
            processor._check_and_notify_events(item, mock_last, 1, crawl_status=1)


class TestNotifyAndRecordEvent:
    """_notify_and_record_event メソッドのテスト"""

    def test_notifies_and_records(self) -> None:
        """通知して記録"""
        mock_app = MagicMock()
        mock_config = MagicMock()
        mock_app.config = mock_config
        processor = price_watch.processor.ItemProcessor(app=mock_app)

        mock_result = MagicMock()
        mock_result.event_type.value = "PRICE_DROP"

        item = price_watch.models.CheckedItem(
            name="Test",
            store="store",
            url="https://example.com",
            crawl_status=price_watch.models.CrawlStatus.SUCCESS,
        )

        with (
            patch("price_watch.notify.event", return_value="message_id"),
            patch("price_watch.event.record_event"),
        ):
            processor._notify_and_record_event(mock_result, item, 1)


class TestHandleCrawlFailure:
    """_handle_crawl_failure メソッドのテスト"""

    def test_increments_error_count(self) -> None:
        """エラーカウントをインクリメント"""
        mock_app = MagicMock()
        mock_app.debug_mode = False
        processor = price_watch.processor.ItemProcessor(app=mock_app)

        item = price_watch.models.CheckedItem(
            name="Test",
            store="store",
            url="https://example.com",
            crawl_status=price_watch.models.CrawlStatus.FAILURE,
        )

        processor._handle_crawl_failure(item, "store")

        assert processor.error_count["https://example.com"] == 1


class TestHandleException:
    """_handle_exception メソッドのテスト"""

    def test_increments_error_count(self) -> None:
        """エラーカウントをインクリメント"""
        mock_app = MagicMock()
        mock_app.debug_mode = False
        processor = price_watch.processor.ItemProcessor(app=mock_app)

        item = _create_resolved_item(name="Test", url="https://example.com")

        with patch.object(processor, "_process_data"):
            processor._handle_exception(item, "store")

        assert processor.error_count["https://example.com"] == 1


class TestMarkDebugFailure:
    """_mark_debug_failure メソッドのテスト"""

    def test_records_failure_in_debug_mode(self) -> None:
        """デバッグモードで失敗を記録"""
        mock_app = MagicMock()
        mock_app.debug_mode = True
        processor = price_watch.processor.ItemProcessor(app=mock_app)

        processor._mark_debug_failure("store", "test reason")

        assert processor.debug_check_results["store"] is False

    def test_does_nothing_in_normal_mode(self) -> None:
        """通常モードでは何もしない"""
        mock_app = MagicMock()
        mock_app.debug_mode = False
        processor = price_watch.processor.ItemProcessor(app=mock_app)

        processor._mark_debug_failure("store", "test reason")

        assert "store" not in processor.debug_check_results


class TestGroupByStore:
    """_group_by_store メソッドのテスト"""

    def test_groups_items(self) -> None:
        """アイテムをグループ化"""
        mock_app = MagicMock()
        processor = price_watch.processor.ItemProcessor(app=mock_app)

        items = [
            _create_resolved_item(name="Item1", store="store1"),
            _create_resolved_item(name="Item2", store="store2"),
            _create_resolved_item(name="Item3", store="store1"),
        ]

        result = processor._group_by_store(items)

        assert len(result["store1"]) == 2
        assert len(result["store2"]) == 1


class TestSelectOneItemPerStore:
    """_select_one_item_per_store メソッドのテスト"""

    def test_selects_one_per_store(self) -> None:
        """ストアごとに1アイテム選択"""
        mock_app = MagicMock()
        processor = price_watch.processor.ItemProcessor(app=mock_app)

        items = [
            _create_resolved_item(name="Item1", store="store1"),
            _create_resolved_item(name="Item2", store="store1"),
            _create_resolved_item(name="Item3", store="store2"),
        ]

        result = processor._select_one_item_per_store(items)

        assert len(result) == 2
        stores = {item.store for item in result}
        assert stores == {"store1", "store2"}


class TestCheckDebugResults:
    """check_debug_results メソッドのテスト"""

    def test_returns_false_if_no_results(self) -> None:
        """結果がない場合は False"""
        mock_app = MagicMock()
        processor = price_watch.processor.ItemProcessor(app=mock_app)

        result = processor.check_debug_results()

        assert result is False

    def test_returns_true_if_all_success(self) -> None:
        """全成功時は True"""
        mock_app = MagicMock()
        processor = price_watch.processor.ItemProcessor(app=mock_app)
        processor.debug_check_results = {"store1": True, "store2": True}

        result = processor.check_debug_results()

        assert result is True

    def test_returns_false_if_any_failure(self) -> None:
        """失敗があれば False"""
        mock_app = MagicMock()
        processor = price_watch.processor.ItemProcessor(app=mock_app)
        processor.debug_check_results = {"store1": True, "store2": False}

        result = processor.check_debug_results()

        assert result is False


class TestProcessYahooItems:
    """process_yahoo_items メソッドのテスト"""

    def test_returns_early_if_no_items(self) -> None:
        """アイテムがない場合は早期リターン"""
        mock_app = MagicMock()
        processor = price_watch.processor.ItemProcessor(app=mock_app)

        processor.process_yahoo_items([])
        # No exception raised

    def test_processes_yahoo_items(self) -> None:
        """Yahoo アイテムを処理"""
        mock_app = MagicMock()
        mock_app.debug_mode = False
        mock_app.should_terminate = False
        mock_config = MagicMock()
        mock_config.check.drop = None
        mock_app.config = mock_config
        mock_app.history_manager.insert_checked_item.return_value = 1
        mock_app.history_manager.get_last.return_value = None
        mock_app.wait_for_terminate.return_value = False
        processor = price_watch.processor.ItemProcessor(app=mock_app)

        items = [
            _create_resolved_item(name="Item1", check_method=CheckMethod.YAHOO_SEARCH, store="Yahoo"),
            _create_resolved_item(name="Item2", check_method=CheckMethod.SCRAPE, url="https://example.com"),
        ]

        mock_checked = price_watch.models.CheckedItem(
            name="Item1",
            store="Yahoo",
            url="https://store.yahoo.co.jp/item",
            stock=price_watch.models.StockStatus.IN_STOCK,
            crawl_status=price_watch.models.CrawlStatus.SUCCESS,
            search_keyword="Item1",
        )

        with (
            patch("price_watch.store.yahoo.check", return_value=mock_checked),
            patch("price_watch.store.yahoo.generate_item_key", return_value="yahoo_key"),
        ):
            processor.process_yahoo_items(items)

        # 成功した場合は update_liveness が呼ばれる
        mock_app.update_liveness.assert_called_once()

    def test_debug_mode_limits_to_one(self) -> None:
        """デバッグモードでは1アイテムのみ"""
        mock_app = MagicMock()
        mock_app.debug_mode = True
        mock_app.should_terminate = False
        mock_config = MagicMock()
        mock_app.config = mock_config
        mock_app.history_manager.insert_checked_item.return_value = 1
        mock_app.history_manager.get_last.return_value = None
        mock_app.wait_for_terminate.return_value = False
        processor = price_watch.processor.ItemProcessor(app=mock_app)

        items = [
            _create_resolved_item(name="Item1", check_method=CheckMethod.YAHOO_SEARCH, store="Yahoo"),
            _create_resolved_item(name="Item2", check_method=CheckMethod.YAHOO_SEARCH, store="Yahoo"),
        ]

        check_count = 0

        def check_mock(*_args: object) -> price_watch.models.CheckedItem:
            nonlocal check_count
            check_count += 1
            return price_watch.models.CheckedItem(
                name="Item1",
                store="Yahoo",
                url="https://store.yahoo.co.jp/item",
                stock=price_watch.models.StockStatus.IN_STOCK,
                crawl_status=price_watch.models.CrawlStatus.SUCCESS,
            )

        with (
            patch("price_watch.store.yahoo.check", side_effect=check_mock),
            patch("price_watch.store.yahoo.generate_item_key", return_value="yahoo_key"),
        ):
            processor.process_yahoo_items(items)

        # デバッグモードでは1アイテムのみ
        assert check_count == 1

    def test_handles_exception(self) -> None:
        """例外を処理"""
        mock_app = MagicMock()
        mock_app.debug_mode = False
        mock_app.should_terminate = False
        mock_config = MagicMock()
        mock_config.check.drop = None
        mock_app.config = mock_config
        mock_app.wait_for_terminate.return_value = False
        # history_manager のモックを適切に設定
        mock_app.history_manager.insert.return_value = 1
        mock_app.history_manager.get_no_data_duration_hours.return_value = None
        processor = price_watch.processor.ItemProcessor(app=mock_app)

        items = [_create_resolved_item(name="Item1", check_method=CheckMethod.YAHOO_SEARCH, store="Yahoo")]

        with (
            patch("price_watch.store.yahoo.check", side_effect=Exception("Error")),
            patch("price_watch.store.yahoo.generate_item_key", return_value="yahoo_key"),
        ):
            processor.process_yahoo_items(items)
        # No exception raised

    def test_returns_on_terminate(self) -> None:
        """終了フラグで早期リターン"""
        mock_app = MagicMock()
        mock_app.debug_mode = False
        mock_app.should_terminate = True
        processor = price_watch.processor.ItemProcessor(app=mock_app)

        items = [_create_resolved_item(name="Item1", check_method=CheckMethod.YAHOO_SEARCH, store="Yahoo")]

        processor.process_yahoo_items(items)
        # Early return


class TestProcessYahooItem:
    """_process_yahoo_item メソッドのテスト"""

    def test_successful_check(self) -> None:
        """成功時の処理"""
        mock_app = MagicMock()
        mock_app.debug_mode = False
        mock_config = MagicMock()
        mock_config.check.drop = None
        mock_app.config = mock_config
        mock_app.history_manager.insert_checked_item.return_value = 1
        mock_app.history_manager.get_last.return_value = None
        processor = price_watch.processor.ItemProcessor(app=mock_app)

        item = _create_resolved_item(
            name="Test", search_keyword="test", check_method=CheckMethod.YAHOO_SEARCH, store="Yahoo"
        )

        mock_checked = price_watch.models.CheckedItem.from_resolved_item(item)
        mock_checked.crawl_status = price_watch.models.CrawlStatus.SUCCESS

        with (
            patch("price_watch.store.yahoo.generate_item_key", return_value="key123"),
            patch("price_watch.store.yahoo.check", return_value=mock_checked),
        ):
            result = processor._process_yahoo_item(item, "Yahoo")

        assert result is True

    def test_handles_crawl_failure(self) -> None:
        """クロール失敗時の処理"""
        mock_app = MagicMock()
        mock_app.debug_mode = False
        mock_config = MagicMock()
        mock_config.check.drop = None
        mock_app.config = mock_config
        mock_app.history_manager.insert_checked_item.return_value = 1
        mock_app.history_manager.get_last.return_value = None
        processor = price_watch.processor.ItemProcessor(app=mock_app)

        item = _create_resolved_item(
            name="Test", search_keyword="test", check_method=CheckMethod.YAHOO_SEARCH, store="Yahoo"
        )

        mock_checked = price_watch.models.CheckedItem.from_resolved_item(item)
        mock_checked.crawl_status = price_watch.models.CrawlStatus.FAILURE

        with (
            patch("price_watch.store.yahoo.generate_item_key", return_value="key123"),
            patch("price_watch.store.yahoo.check", return_value=mock_checked),
        ):
            result = processor._process_yahoo_item(item, "Yahoo")

        assert result is False


class TestProcessAllWithYahoo:
    """process_all メソッドのYahoo対応テスト"""

    def test_calls_all_processors_including_yahoo(self) -> None:
        """Yahooを含む全プロセッサーを呼び出す"""
        mock_app = MagicMock()
        processor = price_watch.processor.ItemProcessor(app=mock_app)

        with (
            patch.object(processor, "process_scrape_items") as mock_scrape,
            patch.object(processor, "process_amazon_items") as mock_amazon,
            patch.object(processor, "process_mercari_items") as mock_mercari,
            patch.object(processor, "process_yahoo_items") as mock_yahoo,
        ):
            processor.process_all([])

        mock_scrape.assert_called_once()
        mock_amazon.assert_called_once()
        mock_mercari.assert_called_once()
        mock_yahoo.assert_called_once()


class TestExceptionHandling:
    """例外処理パスのテスト"""

    def test_scrape_webdriver_exception(self) -> None:
        """WebDriverException を処理"""
        mock_app = MagicMock()
        mock_app.browser_manager.driver = MagicMock()
        mock_app.debug_mode = False
        mock_config = MagicMock()
        mock_config.check.drop = None
        mock_app.config = mock_config
        processor = price_watch.processor.ItemProcessor(app=mock_app)

        item = _create_resolved_item(name="Test", url="https://example.com")

        with (
            patch(
                "price_watch.store.scrape.check", side_effect=selenium.common.exceptions.WebDriverException()
            ),
            patch.object(processor, "_process_data"),
        ):
            result = processor._process_scrape_item(item, "store")

        assert result is False
        # エラーカウントがインクリメントされる
        assert processor.error_count["https://example.com"] == 1

    def test_mercari_general_exception(self) -> None:
        """メルカリの一般的な例外を処理"""
        mock_app = MagicMock()
        mock_app.browser_manager.driver = MagicMock()
        mock_app.debug_mode = False
        mock_config = MagicMock()
        mock_config.check.drop = None
        mock_app.config = mock_config
        processor = price_watch.processor.ItemProcessor(app=mock_app)

        item = _create_resolved_item(
            name="Test", search_keyword="test", check_method=CheckMethod.MERCARI_SEARCH
        )

        with (
            patch("price_watch.store.mercari.generate_item_key", return_value="key123"),
            patch("price_watch.store.mercari.check", side_effect=Exception("Network Error")),
            patch.object(processor, "_process_data"),
        ):
            result = processor._process_mercari_item(item, "mercari.com")

        assert result is False
        assert processor.error_count["key123"] == 1

    def test_yahoo_general_exception(self) -> None:
        """Yahooの一般的な例外を処理"""
        mock_app = MagicMock()
        mock_app.debug_mode = False
        mock_config = MagicMock()
        mock_config.check.drop = None
        mock_app.config = mock_config
        processor = price_watch.processor.ItemProcessor(app=mock_app)

        item = _create_resolved_item(
            name="Test", search_keyword="test", check_method=CheckMethod.YAHOO_SEARCH, store="Yahoo"
        )

        with (
            patch("price_watch.store.yahoo.generate_item_key", return_value="yahoo_key"),
            patch("price_watch.store.yahoo.check", side_effect=Exception("API Error")),
            patch.object(processor, "_process_data"),
        ):
            result = processor._process_yahoo_item(item, "Yahoo")

        assert result is False
        assert processor.error_count["yahoo_key"] == 1

    def test_driver_recreate_failure(self) -> None:
        """ドライバー再作成失敗"""
        mock_app = MagicMock()
        mock_app.browser_manager.driver = MagicMock()
        mock_app.browser_manager.recreate_driver.return_value = False  # 再作成失敗
        mock_app.debug_mode = False
        mock_config = MagicMock()
        mock_app.config = mock_config
        processor = price_watch.processor.ItemProcessor(app=mock_app)

        item = _create_resolved_item(name="Test", url="https://example.com")

        with patch(
            "price_watch.store.scrape.check",
            side_effect=selenium.common.exceptions.InvalidSessionIdException(),
        ):
            result = processor._process_scrape_item(item, "store")

        assert result is False
        mock_app.browser_manager.recreate_driver.assert_called_once()
