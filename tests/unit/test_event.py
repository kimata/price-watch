#!/usr/bin/env python3
# ruff: noqa: S101
"""
event モジュールのユニットテスト

イベント検出・フォーマット機能のテストを行います。
"""

from unittest import mock

import pytest

from price_watch.event import (
    EventResult,
    EventType,
    check_back_in_stock,
    check_crawl_failure,
    check_data_retrieval_failure,
    check_lowest_price,
    check_price_drop,
    format_event_message,
    format_event_title,
)
from price_watch.models import EventRecord


# === EventType テスト ===
class TestEventType:
    """EventType 列挙型のテスト"""

    def test_values(self) -> None:
        """列挙値の確認"""
        assert EventType.BACK_IN_STOCK.value == "back_in_stock"
        assert EventType.CRAWL_FAILURE.value == "crawl_failure"
        assert EventType.DATA_RETRIEVAL_FAILURE.value == "data_retrieval_failure"
        assert EventType.LOWEST_PRICE.value == "lowest_price"
        assert EventType.PRICE_DROP.value == "price_drop"

    def test_is_str_subclass(self) -> None:
        """str のサブクラス"""
        assert isinstance(EventType.BACK_IN_STOCK, str)
        assert EventType.BACK_IN_STOCK == "back_in_stock"


# === EventResult テスト ===
class TestEventResult:
    """EventResult dataclass のテスト"""

    def test_create_minimal(self) -> None:
        """最小構成での作成"""
        result = EventResult(event_type=EventType.BACK_IN_STOCK, should_notify=True)
        assert result.event_type == EventType.BACK_IN_STOCK
        assert result.should_notify is True
        assert result.price is None
        assert result.old_price is None
        assert result.threshold_days is None

    def test_create_with_price(self) -> None:
        """価格情報付きで作成"""
        result = EventResult(
            event_type=EventType.LOWEST_PRICE,
            should_notify=True,
            price=800,
            old_price=1000,
        )
        assert result.price == 800
        assert result.old_price == 1000


# === format_event_message テスト ===
class TestFormatEventMessage:
    """format_event_message 関数のテスト"""

    def _create_event_record(
        self,
        event_type: str,
        item_name: str | None = None,
        price: int | None = None,
        old_price: int | None = None,
        threshold_days: int | None = None,
    ) -> EventRecord:
        """テスト用の EventRecord を作成"""
        return EventRecord(
            id=1,
            item_id=1,
            event_type=event_type,
            item_name=item_name,
            store="テストストア",
            url="https://example.com",
            thumb_url=None,
            price=price,
            old_price=old_price,
            threshold_days=threshold_days,
            notified=False,
            created_at="2024-01-15T10:00:00",
        )

    def test_back_in_stock(self) -> None:
        """在庫復活メッセージ"""
        event = self._create_event_record(event_type="back_in_stock", item_name="テスト商品")
        msg = format_event_message(event)
        assert "テスト商品" in msg
        assert "在庫が復活" in msg

    def test_crawl_failure(self) -> None:
        """クロール失敗メッセージ"""
        event = self._create_event_record(event_type="crawl_failure", item_name="テスト商品")
        msg = format_event_message(event)
        assert "テスト商品" in msg
        assert "クロール" in msg
        assert "24時間" in msg

    def test_data_retrieval_failure(self) -> None:
        """情報取得エラーメッセージ"""
        event = self._create_event_record(event_type="data_retrieval_failure", item_name="テスト商品")
        msg = format_event_message(event)
        assert "テスト商品" in msg
        assert "情報取得" in msg

    def test_lowest_price_with_prices(self) -> None:
        """過去最安値メッセージ（価格あり）"""
        event = self._create_event_record(
            event_type="lowest_price",
            item_name="テスト商品",
            price=800,
            old_price=1000,
        )
        msg = format_event_message(event)
        assert "テスト商品" in msg
        assert "過去最安値" in msg
        assert "1,000円" in msg
        assert "800円" in msg

    def test_lowest_price_without_prices(self) -> None:
        """過去最安値メッセージ（価格なし）"""
        event = self._create_event_record(event_type="lowest_price", item_name="テスト商品")
        msg = format_event_message(event)
        assert "テスト商品" in msg
        assert "過去最安値を更新しました" in msg

    def test_price_drop_with_details(self) -> None:
        """価格下落メッセージ（詳細あり）"""
        event = self._create_event_record(
            event_type="price_drop",
            item_name="テスト商品",
            price=800,
            old_price=1000,
            threshold_days=7,
        )
        msg = format_event_message(event)
        assert "テスト商品" in msg
        assert "7日間" in msg
        assert "200円" in msg  # 値下げ額

    def test_unknown_event_type(self) -> None:
        """不明なイベントタイプ"""
        event = self._create_event_record(event_type="unknown", item_name="テスト商品")
        msg = format_event_message(event)
        assert "テスト商品" in msg
        assert "イベントが発生" in msg

    def test_missing_item_name(self) -> None:
        """アイテム名がない場合"""
        event = self._create_event_record(event_type="back_in_stock", item_name=None)
        msg = format_event_message(event)
        assert "不明" in msg


# === format_event_title テスト ===
class TestFormatEventTitle:
    """format_event_title 関数のテスト"""

    def test_back_in_stock(self) -> None:
        """在庫復活タイトル"""
        assert format_event_title("back_in_stock") == "在庫復活"

    def test_crawl_failure(self) -> None:
        """クロール失敗タイトル"""
        assert format_event_title("crawl_failure") == "クロール失敗"

    def test_data_retrieval_failure(self) -> None:
        """情報取得エラータイトル"""
        assert format_event_title("data_retrieval_failure") == "情報取得エラー"

    def test_lowest_price(self) -> None:
        """過去最安値タイトル"""
        assert format_event_title("lowest_price") == "過去最安値"

    def test_price_drop(self) -> None:
        """価格下落タイトル"""
        assert format_event_title("price_drop") == "価格下落"

    def test_unknown(self) -> None:
        """不明なタイプ"""
        assert format_event_title("unknown") == "イベント"


# === check_back_in_stock テスト ===
class TestCheckBackInStock:
    """check_back_in_stock 関数のテスト"""

    @pytest.fixture
    def mock_history(self) -> mock.MagicMock:
        """HistoryManager のモック"""
        return mock.MagicMock()

    def test_returns_none_when_current_stock_is_none(self, mock_history: mock.MagicMock) -> None:
        """現在の在庫状態が不明の場合は None"""
        result = check_back_in_stock(
            mock_history, item_id=1, current_stock=None, last_stock=0, ignore_hours=24
        )
        assert result is None

    def test_returns_none_when_last_stock_is_none(self, mock_history: mock.MagicMock) -> None:
        """前回の在庫状態が不明の場合は None"""
        result = check_back_in_stock(
            mock_history, item_id=1, current_stock=1, last_stock=None, ignore_hours=24
        )
        assert result is None

    def test_returns_none_when_no_stock_change(self, mock_history: mock.MagicMock) -> None:
        """在庫変化がない場合は None"""
        result = check_back_in_stock(mock_history, item_id=1, current_stock=1, last_stock=1, ignore_hours=24)
        assert result is None

    def test_returns_none_when_out_of_stock_duration_short(self, mock_history: mock.MagicMock) -> None:
        """在庫なし継続時間が短い場合は None"""
        mock_history.get_out_of_stock_duration_hours.return_value = 1.0  # 1時間（3時間未満）

        result = check_back_in_stock(
            mock_history,
            item_id=1,
            current_stock=1,
            last_stock=0,
            ignore_hours=24,
            min_out_of_stock_hours=3.0,
        )
        assert result is None

    def test_returns_event_with_should_notify_false_when_recent_event(
        self, mock_history: mock.MagicMock
    ) -> None:
        """最近イベントがある場合は should_notify=False"""
        mock_history.get_out_of_stock_duration_hours.return_value = 5.0
        mock_history.has_event_in_hours.return_value = True

        result = check_back_in_stock(mock_history, item_id=1, current_stock=1, last_stock=0, ignore_hours=24)

        assert result is not None
        assert result.event_type == EventType.BACK_IN_STOCK
        assert result.should_notify is False

    def test_returns_event_with_should_notify_true(self, mock_history: mock.MagicMock) -> None:
        """条件を満たす場合は should_notify=True"""
        mock_history.get_out_of_stock_duration_hours.return_value = 5.0
        mock_history.has_event_in_hours.return_value = False

        result = check_back_in_stock(mock_history, item_id=1, current_stock=1, last_stock=0, ignore_hours=24)

        assert result is not None
        assert result.event_type == EventType.BACK_IN_STOCK
        assert result.should_notify is True


# === check_crawl_failure テスト ===
class TestCheckCrawlFailure:
    """check_crawl_failure 関数のテスト"""

    @pytest.fixture
    def mock_history(self) -> mock.MagicMock:
        """HistoryManager のモック"""
        return mock.MagicMock()

    def test_returns_none_when_recent_success(self, mock_history: mock.MagicMock) -> None:
        """最近成功したクロールがある場合は None"""
        mock_history.has_successful_crawl_in_hours.return_value = True

        result = check_crawl_failure(mock_history, item_id=1)
        assert result is None

    def test_returns_event_with_should_notify_false_when_recent_event(
        self, mock_history: mock.MagicMock
    ) -> None:
        """最近イベントがある場合は should_notify=False"""
        mock_history.has_successful_crawl_in_hours.return_value = False
        mock_history.has_event_in_hours.return_value = True

        result = check_crawl_failure(mock_history, item_id=1)

        assert result is not None
        assert result.event_type == EventType.CRAWL_FAILURE
        assert result.should_notify is False

    def test_returns_event_with_should_notify_true(self, mock_history: mock.MagicMock) -> None:
        """条件を満たす場合は should_notify=True"""
        mock_history.has_successful_crawl_in_hours.return_value = False
        mock_history.has_event_in_hours.return_value = False

        result = check_crawl_failure(mock_history, item_id=1)

        assert result is not None
        assert result.event_type == EventType.CRAWL_FAILURE
        assert result.should_notify is True


# === check_data_retrieval_failure テスト ===
class TestCheckDataRetrievalFailure:
    """check_data_retrieval_failure 関数のテスト"""

    @pytest.fixture
    def mock_history(self) -> mock.MagicMock:
        """HistoryManager のモック"""
        return mock.MagicMock()

    def test_returns_none_when_duration_short(self, mock_history: mock.MagicMock) -> None:
        """失敗継続時間が短い場合は None"""
        mock_history.get_no_data_duration_hours.return_value = 2.0  # 2時間（6時間未満）

        result = check_data_retrieval_failure(mock_history, item_id=1)
        assert result is None

    def test_returns_event_with_should_notify_true(self, mock_history: mock.MagicMock) -> None:
        """条件を満たす場合は should_notify=True"""
        mock_history.get_no_data_duration_hours.return_value = 8.0
        mock_history.has_event_in_hours.return_value = False

        result = check_data_retrieval_failure(mock_history, item_id=1)

        assert result is not None
        assert result.event_type == EventType.DATA_RETRIEVAL_FAILURE
        assert result.should_notify is True


# === check_lowest_price テスト ===
class TestCheckLowestPrice:
    """check_lowest_price 関数のテスト"""

    @pytest.fixture
    def mock_history(self) -> mock.MagicMock:
        """HistoryManager のモック"""
        return mock.MagicMock()

    def test_returns_none_when_no_history(self, mock_history: mock.MagicMock) -> None:
        """履歴がない場合は None"""
        mock_history.get_lowest_in_period.return_value = None

        result = check_lowest_price(mock_history, item_id=1, current_price=800, ignore_hours=24)
        assert result is None

    def test_returns_none_when_price_not_lower(self, mock_history: mock.MagicMock) -> None:
        """現在価格が最安値以上の場合は None"""
        mock_history.get_lowest_in_period.return_value = 800

        result = check_lowest_price(mock_history, item_id=1, current_price=900, ignore_hours=24)
        assert result is None

    def test_returns_event_with_prices(self, mock_history: mock.MagicMock) -> None:
        """最安値更新時にイベントを返す"""
        mock_history.get_lowest_in_period.return_value = 1000
        mock_history.has_event_in_hours.return_value = False

        result = check_lowest_price(mock_history, item_id=1, current_price=800, ignore_hours=24)

        assert result is not None
        assert result.event_type == EventType.LOWEST_PRICE
        assert result.should_notify is True
        assert result.price == 800
        assert result.old_price == 1000

    def test_with_lowest_config_rate_met(self, mock_history: mock.MagicMock) -> None:
        """LowestConfig の rate 閾値を満たす場合にイベントを返す"""
        from price_watch.config import LowestConfig

        mock_history.get_lowest_in_period.return_value = 1000
        mock_history.get_last_event.return_value = None  # 前回イベントなし → baseline = lowest_price
        mock_history.has_event_in_hours.return_value = False

        lowest_config = LowestConfig(rate=5.0, value=None)
        # drop_amount = 1000 - 800 = 200, rate = 200/1000*100 = 20% >= 5%
        result = check_lowest_price(
            mock_history, item_id=1, current_price=800, ignore_hours=24, lowest_config=lowest_config
        )

        assert result is not None
        assert result.should_notify is True

    def test_with_lowest_config_rate_not_met(self, mock_history: mock.MagicMock) -> None:
        """LowestConfig の rate 閾値を満たさない場合は None"""
        from price_watch.config import LowestConfig

        mock_history.get_lowest_in_period.return_value = 1000
        mock_history.get_last_event.return_value = None
        mock_history.has_event_in_hours.return_value = False

        lowest_config = LowestConfig(rate=50.0, value=None)
        # drop_amount = 1000 - 800 = 200, rate = 20% < 50%
        result = check_lowest_price(
            mock_history, item_id=1, current_price=800, ignore_hours=24, lowest_config=lowest_config
        )

        assert result is None

    def test_with_lowest_config_value_with_currency(self, mock_history: mock.MagicMock) -> None:
        """LowestConfig の value 閾値を通貨換算で判定"""
        from price_watch.config import LowestConfig

        mock_history.get_lowest_in_period.return_value = 100  # $100
        mock_history.get_last_event.return_value = None
        mock_history.has_event_in_hours.return_value = False

        lowest_config = LowestConfig(rate=None, value=1000)
        # drop_amount = 100 - 90 = 10, effective_drop = 10 * 150 = 1500 >= 1000
        result = check_lowest_price(
            mock_history,
            item_id=1,
            current_price=90,
            ignore_hours=24,
            lowest_config=lowest_config,
            currency_rate=150.0,
        )

        assert result is not None
        assert result.should_notify is True

    def test_with_lowest_config_value_not_met_without_currency(self, mock_history: mock.MagicMock) -> None:
        """通貨換算なしでは value 閾値を満たさない"""
        from price_watch.config import LowestConfig

        mock_history.get_lowest_in_period.return_value = 100
        mock_history.get_last_event.return_value = None

        lowest_config = LowestConfig(rate=None, value=1000)
        # drop_amount = 100 - 90 = 10, effective_drop = 10 * 1.0 = 10 < 1000
        result = check_lowest_price(
            mock_history,
            item_id=1,
            current_price=90,
            ignore_hours=24,
            lowest_config=lowest_config,
            currency_rate=1.0,
        )

        assert result is None

    def test_with_lowest_config_uses_last_event_as_baseline(self, mock_history: mock.MagicMock) -> None:
        """直近の LOWEST_PRICE イベントをベースラインに使用"""
        from price_watch.config import LowestConfig

        mock_history.get_lowest_in_period.return_value = 1000

        # 前回イベントの price をベースラインとする
        mock_last_event = mock.MagicMock()
        mock_last_event.price = 900  # baseline = 900
        mock_history.get_last_event.return_value = mock_last_event
        mock_history.has_event_in_hours.return_value = False

        lowest_config = LowestConfig(rate=5.0, value=None)
        # drop_amount = 900 - 800 = 100, rate = 100/900*100 = 11.1% >= 5%
        result = check_lowest_price(
            mock_history, item_id=1, current_price=800, ignore_hours=24, lowest_config=lowest_config
        )

        assert result is not None
        assert result.should_notify is True

    def test_without_lowest_config_fires_immediately(self, mock_history: mock.MagicMock) -> None:
        """LowestConfig なしの場合は従来通り即発火"""
        mock_history.get_lowest_in_period.return_value = 1000
        mock_history.has_event_in_hours.return_value = False

        result = check_lowest_price(
            mock_history, item_id=1, current_price=999, ignore_hours=24, lowest_config=None
        )

        assert result is not None
        assert result.should_notify is True


# === check_price_drop テスト ===
class TestCheckPriceDrop:
    """check_price_drop 関数のテスト"""

    @pytest.fixture
    def mock_history(self) -> mock.MagicMock:
        """HistoryManager のモック"""
        return mock.MagicMock()

    @pytest.fixture
    def mock_window(self) -> mock.MagicMock:
        """PriceDropWindow のモック"""
        window = mock.MagicMock()
        window.days = 7
        window.rate = 10.0
        window.value = None
        return window

    def test_returns_none_when_no_history(
        self, mock_history: mock.MagicMock, mock_window: mock.MagicMock
    ) -> None:
        """履歴がない場合は None"""
        mock_history.get_lowest_in_period.return_value = None

        result = check_price_drop(mock_history, item_id=1, current_price=800, windows=[mock_window])
        assert result is None

    def test_returns_none_when_no_drop(
        self, mock_history: mock.MagicMock, mock_window: mock.MagicMock
    ) -> None:
        """価格が下がっていない場合は None"""
        mock_history.get_lowest_in_period.return_value = 700  # 現在価格より安い

        result = check_price_drop(mock_history, item_id=1, current_price=800, windows=[mock_window])
        assert result is None

    def test_returns_event_when_rate_threshold_met(
        self, mock_history: mock.MagicMock, mock_window: mock.MagicMock
    ) -> None:
        """パーセンテージ閾値を満たす場合にイベントを返す"""
        mock_history.get_lowest_in_period.return_value = 1000  # 10% 以上の下落

        result = check_price_drop(mock_history, item_id=1, current_price=800, windows=[mock_window])

        assert result is not None
        assert result.event_type == EventType.PRICE_DROP
        assert result.should_notify is True
        assert result.price == 800
        assert result.old_price == 1000
        assert result.threshold_days == 7

    def test_returns_event_when_value_threshold_met(self, mock_history: mock.MagicMock) -> None:
        """絶対値閾値を満たす場合にイベントを返す"""
        window = mock.MagicMock()
        window.days = 7
        window.rate = None
        window.value = 100  # 100円以上の下落

        mock_history.get_lowest_in_period.return_value = 1000  # 200円の下落

        result = check_price_drop(mock_history, item_id=1, current_price=800, windows=[window])

        assert result is not None
        assert result.should_notify is True

    def test_value_threshold_with_currency_rate(self, mock_history: mock.MagicMock) -> None:
        """通貨換算後の値で value 閾値を判定"""
        window = mock.MagicMock()
        window.days = 7
        window.rate = None
        window.value = 1000  # 1000円以上の下落

        # drop_amount = 100 - 90 = 10, effective_drop = 10 * 150 = 1500 >= 1000
        mock_history.get_lowest_in_period.return_value = 100

        result = check_price_drop(
            mock_history, item_id=1, current_price=90, windows=[window], currency_rate=150.0
        )

        assert result is not None
        assert result.should_notify is True

    def test_value_threshold_not_met_without_currency(self, mock_history: mock.MagicMock) -> None:
        """通貨換算なしでは value 閾値を満たさない"""
        window = mock.MagicMock()
        window.days = 7
        window.rate = None
        window.value = 1000

        # drop_amount = 100 - 90 = 10, effective_drop = 10 * 1.0 = 10 < 1000
        mock_history.get_lowest_in_period.return_value = 100

        result = check_price_drop(
            mock_history, item_id=1, current_price=90, windows=[window], currency_rate=1.0
        )

        assert result is None
