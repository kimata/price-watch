#!/usr/bin/env python3
# ruff: noqa: S101
"""
notify モジュールのユニットテスト

Slack 通知処理を検証します。
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import my_lib.notify.slack

import price_watch.event
import price_watch.models
import price_watch.notify


def _create_checked_item(
    name: str = "Test",
    store: str = "TestStore",
    url: str | None = "https://example.com",
    price: int | None = 1000,
    old_price: int | None = 1200,
    price_unit: str = "円",
    stock: price_watch.models.StockStatus = price_watch.models.StockStatus.IN_STOCK,
    thumb_url: str | None = "https://example.com/thumb.jpg",
    color: str | None = None,
) -> price_watch.models.CheckedItem:
    """テスト用 CheckedItem を作成."""
    item = price_watch.models.CheckedItem(
        name=name,
        store=store,
        url=url,
        price=price,
        old_price=old_price,
        price_unit=price_unit,
        stock=stock,
        thumb_url=thumb_url,
        color=color,
    )
    return item


class TestInfo:
    """info 関数のテスト"""

    def test_returns_none_for_empty_config(self) -> None:
        """SlackEmptyConfig の場合は None"""
        config = my_lib.notify.slack.SlackEmptyConfig()
        item = _create_checked_item()
        result = price_watch.notify.info(config, item)
        assert result is None

    def test_sends_notification(self) -> None:
        """通知を送信"""
        mock_config = MagicMock()
        mock_config.info.channel.name = "#test"

        item = _create_checked_item()

        with patch("my_lib.notify.slack.send", return_value="ts123") as mock_send:
            result = price_watch.notify.info(mock_config, item)

            assert result == "ts123"
            mock_send.assert_called_once()

    def test_with_record_flag(self) -> None:
        """最安値フラグ付き"""
        mock_config = MagicMock()
        mock_config.info.channel.name = "#test"

        item = _create_checked_item()

        with patch("my_lib.notify.slack.send", return_value="ts123") as mock_send:
            price_watch.notify.info(mock_config, item, is_record=True)

            # :fire: が含まれることを確認
            call_args = mock_send.call_args
            formatted_msg = call_args[0][2]  # 第3引数が FormattedMessage
            assert ":fire:" in formatted_msg.text or "Test" in formatted_msg.text


class TestError:
    """error 関数のテスト"""

    def test_returns_none_for_empty_config(self) -> None:
        """SlackEmptyConfig の場合は None"""
        config = my_lib.notify.slack.SlackEmptyConfig()
        item = _create_checked_item()
        result = price_watch.notify.error(config, item, "Error message")
        assert result is None

    def test_sends_error_notification(self) -> None:
        """エラー通知を送信"""
        mock_config = MagicMock()
        mock_config.error.channel.name = "#error"

        item = _create_checked_item()

        with patch("my_lib.notify.slack.send", return_value="ts456") as mock_send:
            result = price_watch.notify.error(mock_config, item, "Something went wrong")

            assert result == "ts456"
            mock_send.assert_called_once()

    def test_handles_send_exception(self) -> None:
        """送信例外をハンドル"""
        mock_config = MagicMock()
        mock_config.error.channel.name = "#error"

        item = _create_checked_item()

        with patch("my_lib.notify.slack.send", side_effect=Exception("Network error")):
            result = price_watch.notify.error(mock_config, item, "Error")
            assert result is None


class TestErrorWithPage:
    """error_with_page 関数のテスト"""

    def test_returns_none_for_empty_config(self) -> None:
        """SlackEmptyConfig の場合は None"""
        config = my_lib.notify.slack.SlackEmptyConfig()
        item = _create_checked_item()
        result = price_watch.notify.error_with_page(config, item, Exception("Test"))
        assert result is None

    def test_sends_error_with_page(self) -> None:
        """ページ付きエラー通知"""
        mock_config = MagicMock()

        item = _create_checked_item()

        with patch("my_lib.notify.slack.notify_error_with_page", return_value="ts789") as mock_notify:
            result = price_watch.notify.error_with_page(
                mock_config, item, Exception("Test error"), screenshot=None, page_source="<html>"
            )

            assert result == "ts789"
            mock_notify.assert_called_once()

    def test_handles_exception(self) -> None:
        """例外をハンドル"""
        mock_config = MagicMock()

        item = _create_checked_item()

        with patch("my_lib.notify.slack.notify_error_with_page", side_effect=Exception("Failed")):
            result = price_watch.notify.error_with_page(mock_config, item, Exception("Test error"))
            assert result is None


class TestEvent:
    """event 関数のテスト"""

    def test_returns_none_for_empty_config(self) -> None:
        """SlackEmptyConfig の場合は None"""
        config = my_lib.notify.slack.SlackEmptyConfig()
        event_result = price_watch.event.EventResult(
            event_type=price_watch.event.EventType.PRICE_DROP,
            should_notify=True,
            price=800,
            old_price=1000,
            threshold_days=7,
        )
        item = _create_checked_item()
        result = price_watch.notify.event(config, event_result, item)
        assert result is None

    def test_sends_price_drop_event(self) -> None:
        """値下げイベント通知"""
        mock_config = MagicMock()
        mock_config.info.channel.name = "#info"

        event_result = price_watch.event.EventResult(
            event_type=price_watch.event.EventType.PRICE_DROP,
            should_notify=True,
            price=800,
            old_price=1000,
            threshold_days=7,
        )
        item = _create_checked_item()

        with patch("my_lib.notify.slack.send", return_value="ts001") as mock_send:
            result = price_watch.notify.event(mock_config, event_result, item)

            assert result == "ts001"
            mock_send.assert_called_once()

    def test_sends_back_in_stock_event(self) -> None:
        """在庫復活イベント通知"""
        mock_config = MagicMock()
        mock_config.info.channel.name = "#info"

        event_result = price_watch.event.EventResult(
            event_type=price_watch.event.EventType.BACK_IN_STOCK,
            should_notify=True,
            price=1000,
        )
        item = _create_checked_item()

        with patch("my_lib.notify.slack.send", return_value="ts002"):
            result = price_watch.notify.event(mock_config, event_result, item)
            assert result == "ts002"

    def test_sends_lowest_price_event(self) -> None:
        """最安値イベント通知"""
        mock_config = MagicMock()
        mock_config.info.channel.name = "#info"

        event_result = price_watch.event.EventResult(
            event_type=price_watch.event.EventType.LOWEST_PRICE,
            should_notify=True,
            price=500,
            old_price=800,
        )
        item = _create_checked_item()

        with patch("my_lib.notify.slack.send", return_value="ts003"):
            result = price_watch.notify.event(mock_config, event_result, item)
            assert result == "ts003"

    def test_sends_crawl_failure_event(self) -> None:
        """クロール失敗イベント通知"""
        mock_config = MagicMock()
        mock_config.info.channel.name = "#info"

        event_result = price_watch.event.EventResult(
            event_type=price_watch.event.EventType.CRAWL_FAILURE,
            should_notify=True,
        )
        item = _create_checked_item()

        with patch("my_lib.notify.slack.send", return_value="ts004"):
            result = price_watch.notify.event(mock_config, event_result, item)
            assert result == "ts004"

    def test_sends_data_retrieval_failure_to_error_channel(self) -> None:
        """情報取得失敗はエラーチャンネルに送信"""
        mock_config = MagicMock()
        mock_config.error.channel.name = "#error"

        event_result = price_watch.event.EventResult(
            event_type=price_watch.event.EventType.DATA_RETRIEVAL_FAILURE,
            should_notify=True,
        )
        item = _create_checked_item()

        with patch("my_lib.notify.slack.send", return_value="ts005") as mock_send:
            result = price_watch.notify.event(mock_config, event_result, item)

            assert result == "ts005"
            # error チャンネルに送信されることを確認
            call_args = mock_send.call_args
            assert call_args[0][1] == "#error"

    def test_with_no_thumb_url(self) -> None:
        """サムネイルなしの場合"""
        mock_config = MagicMock()
        mock_config.info.channel.name = "#info"

        event_result = price_watch.event.EventResult(
            event_type=price_watch.event.EventType.PRICE_DROP,
            should_notify=True,
            price=800,
            old_price=1000,
            threshold_days=7,
        )
        item = _create_checked_item(thumb_url=None)

        with patch("my_lib.notify.slack.send", return_value="ts006"):
            result = price_watch.notify.event(mock_config, event_result, item)
            assert result == "ts006"

    def test_handles_send_exception(self) -> None:
        """送信例外をハンドル"""
        mock_config = MagicMock()
        mock_config.info.channel.name = "#info"

        event_result = price_watch.event.EventResult(
            event_type=price_watch.event.EventType.PRICE_DROP,
            should_notify=True,
            price=800,
        )
        item = _create_checked_item()

        with patch("my_lib.notify.slack.send", side_effect=Exception("Network error")):
            result = price_watch.notify.event(mock_config, event_result, item)
            assert result is None


class TestGetEventIcon:
    """_get_event_icon 関数のテスト"""

    def test_back_in_stock_icon(self) -> None:
        """在庫復活アイコン"""
        result = price_watch.notify._get_event_icon(price_watch.event.EventType.BACK_IN_STOCK)
        assert result == ":package:"

    def test_crawl_failure_icon(self) -> None:
        """クロール失敗アイコン"""
        result = price_watch.notify._get_event_icon(price_watch.event.EventType.CRAWL_FAILURE)
        assert result == ":warning:"

    def test_data_retrieval_failure_icon(self) -> None:
        """情報取得失敗アイコン"""
        result = price_watch.notify._get_event_icon(price_watch.event.EventType.DATA_RETRIEVAL_FAILURE)
        assert result == ":x:"

    def test_lowest_price_icon(self) -> None:
        """最安値アイコン"""
        result = price_watch.notify._get_event_icon(price_watch.event.EventType.LOWEST_PRICE)
        assert result == ":fire:"

    def test_price_drop_icon(self) -> None:
        """値下げアイコン"""
        result = price_watch.notify._get_event_icon(price_watch.event.EventType.PRICE_DROP)
        assert result == ":chart_with_downwards_trend:"


class TestBuildEventMessage:
    """_build_event_message 関数のテスト"""

    def test_back_in_stock_message(self) -> None:
        """在庫復活メッセージ"""
        event_result = price_watch.event.EventResult(
            event_type=price_watch.event.EventType.BACK_IN_STOCK,
            should_notify=True,
            price=1000,
        )
        item = _create_checked_item()
        result = price_watch.notify._build_event_message(event_result, item)
        assert "在庫が復活" in result
        assert "1,000円" in result

    def test_back_in_stock_without_price(self) -> None:
        """在庫復活メッセージ（価格なし）"""
        event_result = price_watch.event.EventResult(
            event_type=price_watch.event.EventType.BACK_IN_STOCK,
            should_notify=True,
        )
        item = _create_checked_item()
        result = price_watch.notify._build_event_message(event_result, item)
        assert "在庫が復活" in result

    def test_crawl_failure_message(self) -> None:
        """クロール失敗メッセージ"""
        event_result = price_watch.event.EventResult(
            event_type=price_watch.event.EventType.CRAWL_FAILURE,
            should_notify=True,
        )
        item = _create_checked_item()
        result = price_watch.notify._build_event_message(event_result, item)
        assert "24時間以上" in result
        assert "クロールに失敗" in result

    def test_data_retrieval_failure_message(self) -> None:
        """情報取得失敗メッセージ"""
        event_result = price_watch.event.EventResult(
            event_type=price_watch.event.EventType.DATA_RETRIEVAL_FAILURE,
            should_notify=True,
        )
        item = _create_checked_item()
        result = price_watch.notify._build_event_message(event_result, item)
        assert "6時間以上" in result
        assert "取得できていません" in result

    def test_lowest_price_message(self) -> None:
        """最安値メッセージ"""
        event_result = price_watch.event.EventResult(
            event_type=price_watch.event.EventType.LOWEST_PRICE,
            should_notify=True,
            price=500,
            old_price=800,
        )
        item = _create_checked_item()
        result = price_watch.notify._build_event_message(event_result, item)
        assert "過去最安値を更新" in result
        assert "800" in result
        assert "500" in result

    def test_lowest_price_without_prices(self) -> None:
        """最安値メッセージ（価格なし）"""
        event_result = price_watch.event.EventResult(
            event_type=price_watch.event.EventType.LOWEST_PRICE,
            should_notify=True,
        )
        item = _create_checked_item()
        result = price_watch.notify._build_event_message(event_result, item)
        assert "過去最安値を更新しました" in result

    def test_price_drop_message(self) -> None:
        """値下げメッセージ"""
        event_result = price_watch.event.EventResult(
            event_type=price_watch.event.EventType.PRICE_DROP,
            should_notify=True,
            price=800,
            old_price=1000,
            threshold_days=7,
        )
        item = _create_checked_item()
        result = price_watch.notify._build_event_message(event_result, item)
        assert "7日間の最安値から値下げ" in result
        assert "1,000" in result
        assert "800" in result

    def test_price_drop_without_details(self) -> None:
        """値下げメッセージ（詳細なし）"""
        event_result = price_watch.event.EventResult(
            event_type=price_watch.event.EventType.PRICE_DROP,
            should_notify=True,
        )
        item = _create_checked_item()
        result = price_watch.notify._build_event_message(event_result, item)
        assert "価格が下がりました" in result

    def test_message_includes_link(self) -> None:
        """メッセージにリンクが含まれる"""
        event_result = price_watch.event.EventResult(
            event_type=price_watch.event.EventType.PRICE_DROP,
            should_notify=True,
        )
        item = _create_checked_item()
        result = price_watch.notify._build_event_message(event_result, item)
        assert "詳細を見る" in result
        assert "https://example.com" in result
