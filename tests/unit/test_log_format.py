#!/usr/bin/env python3
# ruff: noqa: S101
"""
log_format モジュールのユニットテスト

ログフォーマット機能を検証します。
"""

from __future__ import annotations

from dataclasses import dataclass

from price_watch.log_format import (
    ANSI_RESET,
    EMOJI_BACK_IN_STOCK,
    EMOJI_CRAWLING,
    EMOJI_IN_STOCK,
    EMOJI_NEW,
    EMOJI_OUT_OF_STOCK,
    EMOJI_PRICE_DOWN,
    HasItemInfo,
    _colorize,
    _get_attr,
    _hex_to_ansi,
    _rgb_to_256,
    format_back_in_stock,
    format_crawl_start,
    format_error,
    format_item_prefix,
    format_item_status,
    format_price_decrease,
    format_watch_start,
)


@dataclass
class MockItem:
    """テスト用のアイテムクラス"""

    name: str
    store: str
    price: int = 0
    price_unit: str = "円"
    stock: int = 0
    color: str | None = None


class TestHasItemInfoProtocol:
    """HasItemInfo プロトコルのテスト"""

    def test_dataclass_is_instance(self) -> None:
        """dataclass は HasItemInfo として認識される"""
        item = MockItem(name="Test", store="TestStore")
        assert isinstance(item, HasItemInfo)

    def test_dict_is_not_instance(self) -> None:
        """dict は HasItemInfo ではない（プロパティがない）"""
        item = {"name": "Test", "store": "TestStore"}
        assert not isinstance(item, HasItemInfo)


class TestGetAttr:
    """_get_attr 関数のテスト"""

    def test_get_from_dict(self) -> None:
        """dict から属性を取得"""
        item = {"name": "Test", "store": "TestStore"}
        assert _get_attr(item, "name") == "Test"
        assert _get_attr(item, "store") == "TestStore"

    def test_get_from_dataclass(self) -> None:
        """dataclass から属性を取得"""
        item = MockItem(name="Test", store="TestStore")
        assert _get_attr(item, "name") == "Test"
        assert _get_attr(item, "store") == "TestStore"

    def test_get_with_default(self) -> None:
        """存在しない属性はデフォルト値を返す"""
        item: dict[str, str] = {"name": "Test"}
        assert _get_attr(item, "missing", "default") == "default"

    def test_get_with_none_default(self) -> None:
        """デフォルト値が None"""
        item: dict[str, str] = {"name": "Test"}
        assert _get_attr(item, "missing") is None


class TestRgbTo256:
    """_rgb_to_256 関数のテスト"""

    def test_black(self) -> None:
        """黒 (0, 0, 0)"""
        result = _rgb_to_256(0, 0, 0)
        assert result == 16  # 16 + 36*0 + 6*0 + 0

    def test_white(self) -> None:
        """白 (255, 255, 255)"""
        result = _rgb_to_256(255, 255, 255)
        assert result == 231  # 16 + 36*5 + 6*5 + 5

    def test_red(self) -> None:
        """赤 (255, 0, 0)"""
        result = _rgb_to_256(255, 0, 0)
        assert result == 196  # 16 + 36*5 + 6*0 + 0

    def test_green(self) -> None:
        """緑 (0, 255, 0)"""
        result = _rgb_to_256(0, 255, 0)
        assert result == 46  # 16 + 36*0 + 6*5 + 0

    def test_blue(self) -> None:
        """青 (0, 0, 255)"""
        result = _rgb_to_256(0, 0, 255)
        assert result == 21  # 16 + 36*0 + 6*0 + 5

    def test_mid_gray(self) -> None:
        """中間グレー"""
        result = _rgb_to_256(128, 128, 128)
        # 128/255*5 ≈ 2.5 → round to 2 or 3
        assert 16 <= result <= 231


class TestHexToAnsi:
    """_hex_to_ansi 関数のテスト"""

    def test_with_hash(self) -> None:
        """# 付きの hex カラー"""
        result = _hex_to_ansi("#ff0000")
        assert result.startswith("\033[38;5;")
        assert result.endswith("m")

    def test_without_hash(self) -> None:
        """# なしの hex カラー"""
        result = _hex_to_ansi("ff0000")
        assert result.startswith("\033[38;5;")

    def test_returns_ansi_256_format(self) -> None:
        """256色 ANSI フォーマットを返す"""
        result = _hex_to_ansi("#ffffff")
        # 白は 231
        assert "\033[38;5;231m" == result


class TestColorize:
    """_colorize 関数のテスト"""

    def test_with_color(self) -> None:
        """カラーを適用"""
        result = _colorize("text", "#ff0000")
        assert result.startswith("\033[38;5;")
        assert "text" in result
        assert result.endswith(ANSI_RESET)

    def test_with_none(self) -> None:
        """カラーが None の場合はそのまま返す"""
        result = _colorize("text", None)
        assert result == "text"


class TestFormatItemPrefix:
    """format_item_prefix 関数のテスト"""

    def test_with_dict(self) -> None:
        """dict 形式のアイテム"""
        item = {"name": "商品名", "store": "ストア"}
        result = format_item_prefix(item)
        assert "[ストア] 商品名" in result

    def test_with_dataclass(self) -> None:
        """dataclass 形式のアイテム"""
        item = MockItem(name="商品名", store="ストア")
        result = format_item_prefix(item)
        assert "[ストア] 商品名" in result

    def test_with_color(self) -> None:
        """カラー付きのストア"""
        item = {"name": "商品名", "store": "ストア", "color": "#ff9900"}
        result = format_item_prefix(item)
        assert "\033[38;5;" in result  # ANSI カラー
        assert "商品名" in result

    def test_with_missing_fields(self) -> None:
        """フィールドがない場合はデフォルト値"""
        item: dict[str, str] = {}
        result = format_item_prefix(item)
        assert "[unknown] unknown" in result


class TestFormatCrawlStart:
    """format_crawl_start 関数のテスト"""

    def test_format(self) -> None:
        """クロール開始メッセージ"""
        item = {"name": "商品名", "store": "ストア"}
        result = format_crawl_start(item)
        assert EMOJI_CRAWLING in result
        assert "クロール開始" in result
        assert "ストア" in result
        assert "商品名" in result


class TestFormatWatchStart:
    """format_watch_start 関数のテスト"""

    def test_in_stock(self) -> None:
        """在庫ありの場合"""
        item = {"name": "商品名", "store": "ストア", "price": 1000, "stock": 1}
        result = format_watch_start(item)
        assert EMOJI_NEW in result
        assert "監視開始" in result
        assert "1000円" in result
        assert "在庫あり" in result

    def test_out_of_stock(self) -> None:
        """在庫なしの場合"""
        item = {"name": "商品名", "store": "ストア", "stock": 0}
        result = format_watch_start(item)
        assert EMOJI_NEW in result
        assert "監視開始" in result
        assert "在庫なし" in result

    def test_custom_price_unit(self) -> None:
        """カスタム通貨単位"""
        item = {"name": "商品名", "store": "ストア", "price": 100, "stock": 1, "price_unit": "ドル"}
        result = format_watch_start(item)
        assert "100ドル" in result


class TestFormatPriceDecrease:
    """format_price_decrease 関数のテスト"""

    def test_format(self) -> None:
        """価格下落メッセージ"""
        item = {"name": "商品名", "store": "ストア", "price": 800}
        result = format_price_decrease(item, old_price=1000)
        assert EMOJI_PRICE_DOWN in result
        assert "価格下落" in result
        assert "1000円" in result
        assert "800円" in result
        assert "→" in result


class TestFormatBackInStock:
    """format_back_in_stock 関数のテスト"""

    def test_format(self) -> None:
        """在庫復活メッセージ"""
        item = {"name": "商品名", "store": "ストア", "price": 1500}
        result = format_back_in_stock(item)
        assert EMOJI_BACK_IN_STOCK in result
        assert "在庫復活" in result
        assert "1500円" in result


class TestFormatItemStatus:
    """format_item_status 関数のテスト"""

    def test_in_stock(self) -> None:
        """在庫ありの状態"""
        item = {"name": "商品名", "store": "ストア", "price": 2000, "stock": 1}
        result = format_item_status(item)
        assert EMOJI_IN_STOCK in result
        assert "2000円" in result

    def test_out_of_stock(self) -> None:
        """在庫なしの状態"""
        item = {"name": "商品名", "store": "ストア", "stock": 0}
        result = format_item_status(item)
        assert EMOJI_OUT_OF_STOCK in result
        assert "在庫なし" in result


class TestFormatError:
    """format_error 関数のテスト"""

    def test_format(self) -> None:
        """エラーメッセージ"""
        item = {"name": "商品名", "store": "ストア"}
        result = format_error(item, error_count=3)
        assert "⚠️" in result
        assert "エラー発生" in result
        assert "連続3回目" in result

    def test_different_error_counts(self) -> None:
        """異なるエラー回数"""
        item = {"name": "商品名", "store": "ストア"}

        result1 = format_error(item, error_count=1)
        assert "連続1回目" in result1

        result5 = format_error(item, error_count=5)
        assert "連続5回目" in result5
