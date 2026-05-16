#!/usr/bin/env python3
# ruff: noqa: S101
"""chart_image モジュールのユニットテスト."""

import pathlib
import tempfile

import pytest
from PIL import Image

import price_watch.chart_image


@pytest.fixture
def sample_chart_data() -> price_watch.chart_image.ChartData:
    """サンプルのチャートデータを生成."""
    history1 = [
        price_watch.chart_image.PricePoint(
            time="2024-01-01T10:00:00",
            price=1000,
            effective_price=1000,
            stock=1,
        ),
        price_watch.chart_image.PricePoint(
            time="2024-01-02T10:00:00",
            price=950,
            effective_price=950,
            stock=1,
        ),
        price_watch.chart_image.PricePoint(
            time="2024-01-03T10:00:00",
            price=980,
            effective_price=980,
            stock=1,
        ),
    ]

    history2 = [
        price_watch.chart_image.PricePoint(
            time="2024-01-01T10:00:00",
            price=1100,
            effective_price=1100,
            stock=1,
        ),
        price_watch.chart_image.PricePoint(
            time="2024-01-02T10:00:00",
            price=1050,
            effective_price=1050,
            stock=0,  # 在庫なし
        ),
        price_watch.chart_image.PricePoint(
            time="2024-01-03T10:00:00",
            price=1020,
            effective_price=1020,
            stock=1,
        ),
    ]

    stores = [
        price_watch.chart_image.StoreChartData(
            store_name="ストアA",
            color="#3b82f6",
            currency_rate=1.0,
            history=history1,
        ),
        price_watch.chart_image.StoreChartData(
            store_name="ストアB",
            color="#ef4444",
            currency_rate=1.0,
            history=history2,
        ),
    ]

    return price_watch.chart_image.ChartData(
        item_name="テスト商品",
        item_key="test_item_key",
        stores=stores,
    )


@pytest.fixture
def empty_chart_data() -> price_watch.chart_image.ChartData:
    """空のチャートデータを生成."""
    return price_watch.chart_image.ChartData(
        item_name="空の商品",
        item_key="empty_item_key",
        stores=[],
    )


class TestChartDataSerialization:
    """ChartData のシリアライズテスト."""

    def test_price_point_fields(self) -> None:
        """PricePoint のフィールドが正しく設定される."""
        point = price_watch.chart_image.PricePoint(
            time="2024-01-01T10:00:00",
            price=1000,
            effective_price=950,
            stock=1,
        )
        assert point.time == "2024-01-01T10:00:00"
        assert point.price == 1000
        assert point.effective_price == 950
        assert point.stock == 1

    def test_store_chart_data_to_dict(self) -> None:
        """StoreChartData.to_dict() が正しい辞書を返す."""
        history = [
            price_watch.chart_image.PricePoint(
                time="2024-01-01T10:00:00",
                price=1000,
                effective_price=1000,
                stock=1,
            ),
        ]
        store = price_watch.chart_image.StoreChartData(
            store_name="テストストア",
            color="#ff0000",
            currency_rate=1.5,
            history=history,
        )
        result = store.to_dict()

        assert result["store"] == "テストストア"
        assert result["color"] == "#ff0000"
        assert result["currency_rate"] == 1.5
        assert len(result["history"]) == 1
        assert result["history"][0]["time"] == "2024-01-01T10:00:00"
        assert result["history"][0]["price"] == 1000

    def test_chart_data_to_dict(self, sample_chart_data: price_watch.chart_image.ChartData) -> None:
        """ChartData.to_dict() が正しい辞書を返す."""
        result = sample_chart_data.to_dict()

        assert result["item_name"] == "テスト商品"
        assert result["item_key"] == "test_item_key"
        assert len(result["stores"]) == 2

    def test_store_definition_to_dict(self) -> None:
        """StoreDefinition.to_dict() が正しい辞書を返す."""
        store_def = price_watch.chart_image.StoreDefinition(
            name="Amazon",
            color="#ff9900",
        )
        result = store_def.to_dict()

        assert result["name"] == "Amazon"
        assert result["color"] == "#ff9900"


class TestRenderChartHtml:
    """_render_chart_html 関数のテスト."""

    def test_render_html_contains_chart_js(
        self, sample_chart_data: price_watch.chart_image.ChartData
    ) -> None:
        """生成された HTML に Chart.js が含まれる."""
        html = price_watch.chart_image._render_chart_html(sample_chart_data, css_width=351, css_height=160)

        assert "chart.js" in html.lower()
        assert "canvas" in html.lower()
        assert "priceChart" in html

    def test_render_html_contains_data(self, sample_chart_data: price_watch.chart_image.ChartData) -> None:
        """生成された HTML にデータが含まれる."""
        html = price_watch.chart_image._render_chart_html(sample_chart_data, css_width=351, css_height=160)

        assert "テスト商品" in html or "test_item_key" in html
        assert "ストアA" in html
        assert "ストアB" in html

    def test_render_html_custom_size(self, sample_chart_data: price_watch.chart_image.ChartData) -> None:
        """カスタムサイズで HTML がレンダリングされる."""
        html = price_watch.chart_image._render_chart_html(sample_chart_data, css_width=300, css_height=200)

        assert "300px" in html
        assert "200px" in html


@pytest.mark.selenium
@pytest.mark.xdist_group(name="chrome")
class TestGenerateChartImage:
    """generate_chart_image 関数のテスト（Selenium 必要）."""

    def test_basic_chart_generation(
        self, sample_chart_data: price_watch.chart_image.ChartData, tmp_path: pathlib.Path
    ) -> None:
        """基本的なチャート生成."""
        data_path = tmp_path / "chrome_data"
        img = price_watch.chart_image.generate_chart_image(sample_chart_data, data_path=data_path)

        assert isinstance(img, Image.Image)
        # Selenium スクリーンショットのサイズはブラウザウィンドウに依存
        assert img.size[0] > 0
        assert img.size[1] > 0
        assert img.mode in ("RGB", "RGBA")

    def test_empty_data_chart(
        self, empty_chart_data: price_watch.chart_image.ChartData, tmp_path: pathlib.Path
    ) -> None:
        """空データでもエラーにならない."""
        data_path = tmp_path / "chrome_data"
        img = price_watch.chart_image.generate_chart_image(empty_chart_data, data_path=data_path)

        assert isinstance(img, Image.Image)

    def test_custom_size(
        self, sample_chart_data: price_watch.chart_image.ChartData, tmp_path: pathlib.Path
    ) -> None:
        """カスタムサイズでの生成."""
        data_path = tmp_path / "chrome_data"
        width = 400
        height = 200
        img = price_watch.chart_image.generate_chart_image(
            sample_chart_data,
            width=width,
            height=height,
            data_path=data_path,
        )

        assert isinstance(img, Image.Image)
        assert img.size[0] > 0
        assert img.size[1] > 0


@pytest.mark.xdist_group(name="chrome")
class TestCacheOperations:
    """キャッシュ操作のテスト."""

    def test_get_cache_path(self) -> None:
        """キャッシュパスの取得."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = pathlib.Path(tmpdir)
            item_key = "test_item"

            cache_path = price_watch.chart_image.get_cache_path(item_key, cache_dir)

            assert cache_path.parent.name == "chart"
            assert cache_path.suffix == ".png"
            assert item_key in str(cache_path.name)

    def test_is_cache_valid_nonexistent(self) -> None:
        """存在しないキャッシュは無効."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = pathlib.Path(tmpdir) / "nonexistent.png"

            assert not price_watch.chart_image.is_cache_valid(cache_path)

    def test_is_cache_valid_fresh(self) -> None:
        """新しいキャッシュは有効."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = pathlib.Path(tmpdir) / "test.png"
            # ダミーファイルを作成
            cache_path.write_bytes(b"dummy")

            # TTL を長く設定して有効性を確認
            assert price_watch.chart_image.is_cache_valid(cache_path, ttl_sec=3600)

    def test_sanitize_filename(self) -> None:
        """ファイル名のサニタイズ."""
        # 通常の文字
        assert price_watch.chart_image._sanitize_filename("test_item") == "test_item"
        # 特殊文字を含む
        result = price_watch.chart_image._sanitize_filename("test/item:name")
        assert "/" not in result
        assert ":" not in result

    @pytest.mark.selenium
    def test_save_and_load_chart_image(
        self, sample_chart_data: price_watch.chart_image.ChartData, tmp_path: pathlib.Path
    ) -> None:
        """画像の保存と読み込み."""
        # 並列テストでの Chrome プロファイル競合を避けるため、一意の data_path を使用
        data_path = tmp_path / "chrome_data"

        # 画像を生成して保存
        img = price_watch.chart_image.generate_chart_image(sample_chart_data, data_path=data_path)
        output_path = tmp_path / "test.png"
        price_watch.chart_image.save_chart_image(img, output_path)

        # ファイルが存在することを確認
        assert output_path.exists()

        # 読み込んで検証
        loaded_img = Image.open(output_path)
        assert loaded_img.size == img.size

    @pytest.mark.selenium
    def test_get_or_generate_chart_image(
        self, sample_chart_data: price_watch.chart_image.ChartData, tmp_path: pathlib.Path
    ) -> None:
        """キャッシュ有無による画像生成."""
        # 並列テストでの Chrome プロファイル競合を避けるため、一意の data_path を使用
        data_path = tmp_path / "chrome_data"

        # 初回: 画像生成
        path1 = price_watch.chart_image.get_or_generate_chart_image(
            sample_chart_data,
            tmp_path,
            data_path=data_path,
        )
        assert path1.exists()
        mtime1 = path1.stat().st_mtime

        # 2回目: キャッシュから取得（ファイル更新なし）
        path2 = price_watch.chart_image.get_or_generate_chart_image(
            sample_chart_data,
            tmp_path,
            data_path=data_path,
        )
        assert path2 == path1
        assert path2.stat().st_mtime == mtime1


class TestFontPaths:
    """FontPaths のテスト."""

    def test_from_config_none(self) -> None:
        """None からの生成."""
        font_paths = price_watch.chart_image.FontPaths.from_config(None)

        assert font_paths.jp_regular is None
        assert font_paths.jp_medium is None
        assert font_paths.jp_bold is None
        assert font_paths.en_medium is None
        assert font_paths.en_bold is None

    def test_default_values(self) -> None:
        """デフォルト値の確認."""
        font_paths = price_watch.chart_image.FontPaths()

        assert font_paths.jp_regular is None
        assert font_paths.jp_medium is None
        assert font_paths.jp_bold is None
        assert font_paths.en_medium is None
        assert font_paths.en_bold is None
