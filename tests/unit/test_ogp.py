#!/usr/bin/env python3
# ruff: noqa: S101
"""
ogp.py のユニットテスト
"""

import pathlib
import tempfile

from PIL import Image

from price_watch.webapi.ogp import (
    CACHE_TTL_SEC,
    DEFAULT_COLORS,
    GRAPH_HEIGHT,
    GRAPH_WIDTH,
    OGP_HEIGHT,
    OGP_SQUARE_SIZE,
    OGP_WIDTH,
    FontPaths,
    OgpData,
    StoreHistory,
    generate_ogp_image,
    generate_ogp_image_square,
    get_cache_path,
    get_or_generate_ogp_image,
    get_or_generate_ogp_image_square,
    is_cache_valid,
    save_ogp_image,
)


class TestOgpConstants:
    """OGP 定数のテスト"""

    def test_ogp_dimensions(self):
        """OGP 画像の推奨サイズであること"""
        assert OGP_WIDTH == 1200
        assert OGP_HEIGHT == 630

    def test_ogp_square_dimensions(self):
        """正方形 OGP 画像のサイズ"""
        assert OGP_SQUARE_SIZE == 1200

    def test_graph_dimensions(self):
        """グラフ領域のサイズ（OGP全面に表示）"""
        # グラフは OGP 全面に表示
        assert GRAPH_WIDTH == OGP_WIDTH
        assert GRAPH_HEIGHT == OGP_HEIGHT

    def test_cache_ttl(self):
        """キャッシュ有効期間が1時間であること"""
        assert CACHE_TTL_SEC == 3600

    def test_default_colors(self):
        """デフォルトカラーが6色あること"""
        assert len(DEFAULT_COLORS) == 6
        # すべて HEX 形式であること
        for color in DEFAULT_COLORS:
            assert color.startswith("#")
            assert len(color) == 7


class TestStoreHistory:
    """StoreHistory データクラスのテスト"""

    def test_create(self):
        """インスタンス生成"""
        history = StoreHistory(
            store_name="TestStore",
            color="#3b82f6",
            history=[{"time": "2026-01-01 12:00:00", "price": 1000, "effective_price": 950}],
        )
        assert history.store_name == "TestStore"
        assert history.color == "#3b82f6"
        assert len(history.history) == 1

    def test_frozen(self):
        """frozen であること"""
        import pytest

        history = StoreHistory(store_name="Test", color="#000000", history=[])
        with pytest.raises(AttributeError):
            history.store_name = "Changed"  # type: ignore


class TestOgpData:
    """OgpData データクラスのテスト"""

    def test_create(self):
        """インスタンス生成"""
        data = OgpData(
            item_name="テスト商品",
            best_price=1000,
            best_store="TestStore",
            lowest_price=950,
            thumb_path=None,
            store_histories=[],
        )
        assert data.item_name == "テスト商品"
        assert data.best_price == 1000
        assert data.best_store == "TestStore"
        assert data.lowest_price == 950

    def test_optional_fields(self):
        """オプショナルフィールド"""
        data = OgpData(
            item_name="テスト商品",
            best_price=None,
            best_store="",
            lowest_price=None,
            thumb_path=None,
            store_histories=[],
        )
        assert data.best_price is None
        assert data.lowest_price is None


class TestGenerateOgpImage:
    """generate_ogp_image のテスト"""

    def test_generate_basic(self, font_paths: FontPaths):
        """基本的な OGP 画像生成"""
        data = OgpData(
            item_name="テスト商品",
            best_price=1000,
            best_store="TestStore",
            lowest_price=950,
            thumb_path=None,
            store_histories=[],
        )
        img = generate_ogp_image(data, font_paths=font_paths)

        assert isinstance(img, Image.Image)
        assert img.size == (OGP_WIDTH, OGP_HEIGHT)
        assert img.mode == "RGB"

    def test_generate_with_history(self, font_paths: FontPaths):
        """価格履歴付きの OGP 画像生成"""
        store_history = StoreHistory(
            store_name="TestStore",
            color="#3b82f6",
            history=[
                {"time": "2026-01-01 12:00:00", "price": 1000, "effective_price": 950},
                {"time": "2026-01-02 12:00:00", "price": 1100, "effective_price": 1050},
            ],
        )
        data = OgpData(
            item_name="テスト商品",
            best_price=1000,
            best_store="TestStore",
            lowest_price=950,
            thumb_path=None,
            store_histories=[store_history],
        )
        img = generate_ogp_image(data, font_paths=font_paths)

        assert isinstance(img, Image.Image)
        assert img.size == (OGP_WIDTH, OGP_HEIGHT)

    def test_generate_with_multiple_stores(self, font_paths: FontPaths):
        """複数ストアの価格履歴"""
        histories = [
            StoreHistory(
                store_name=f"Store{i}",
                color=DEFAULT_COLORS[i],
                history=[
                    {
                        "time": "2026-01-01 12:00:00",
                        "price": 1000 + i * 100,
                        "effective_price": 950 + i * 100,
                    },
                ],
            )
            for i in range(3)
        ]
        data = OgpData(
            item_name="テスト商品",
            best_price=950,
            best_store="Store0",
            lowest_price=950,
            thumb_path=None,
            store_histories=histories,
        )
        img = generate_ogp_image(data, font_paths=font_paths)

        assert isinstance(img, Image.Image)

    def test_generate_with_none_prices(self, font_paths: FontPaths):
        """価格が None の場合"""
        data = OgpData(
            item_name="テスト商品",
            best_price=None,
            best_store="TestStore",
            lowest_price=None,
            thumb_path=None,
            store_histories=[],
        )
        img = generate_ogp_image(data, font_paths=font_paths)

        assert isinstance(img, Image.Image)

    def test_generate_with_long_name(self, font_paths: FontPaths):
        """長い商品名の場合（切り詰めが発生）"""
        long_name = "これは非常に長い商品名です" * 10
        data = OgpData(
            item_name=long_name,
            best_price=1000,
            best_store="TestStore",
            lowest_price=950,
            thumb_path=None,
            store_histories=[],
        )
        img = generate_ogp_image(data, font_paths=font_paths)

        assert isinstance(img, Image.Image)


class TestGenerateOgpImageSquare:
    """generate_ogp_image_square のテスト"""

    def test_generate_basic(self, font_paths: FontPaths):
        """基本的な正方形 OGP 画像生成"""
        data = OgpData(
            item_name="テスト商品",
            best_price=1000,
            best_store="TestStore",
            lowest_price=950,
            thumb_path=None,
            store_histories=[],
        )
        img = generate_ogp_image_square(data, font_paths=font_paths)

        assert isinstance(img, Image.Image)
        assert img.size == (OGP_SQUARE_SIZE, OGP_SQUARE_SIZE)
        assert img.mode == "RGB"

    def test_generate_with_history(self, font_paths: FontPaths):
        """価格履歴付きの正方形 OGP 画像生成"""
        store_history = StoreHistory(
            store_name="TestStore",
            color="#3b82f6",
            history=[
                {"time": "2026-01-01 12:00:00", "price": 1000, "effective_price": 950},
                {"time": "2026-01-02 12:00:00", "price": 1100, "effective_price": 1050},
            ],
        )
        data = OgpData(
            item_name="テスト商品",
            best_price=1000,
            best_store="TestStore",
            lowest_price=950,
            thumb_path=None,
            store_histories=[store_history],
        )
        img = generate_ogp_image_square(data, font_paths=font_paths)

        assert isinstance(img, Image.Image)
        assert img.size == (OGP_SQUARE_SIZE, OGP_SQUARE_SIZE)

    def test_generate_with_multiple_stores(self, font_paths: FontPaths):
        """複数ストアの価格履歴"""
        histories = [
            StoreHistory(
                store_name=f"Store{i}",
                color=DEFAULT_COLORS[i],
                history=[
                    {
                        "time": "2026-01-01 12:00:00",
                        "price": 1000 + i * 100,
                        "effective_price": 950 + i * 100,
                    },
                ],
            )
            for i in range(3)
        ]
        data = OgpData(
            item_name="テスト商品",
            best_price=950,
            best_store="Store0",
            lowest_price=950,
            thumb_path=None,
            store_histories=histories,
        )
        img = generate_ogp_image_square(data, font_paths=font_paths)

        assert isinstance(img, Image.Image)
        assert img.size == (OGP_SQUARE_SIZE, OGP_SQUARE_SIZE)

    def test_generate_with_none_prices(self, font_paths: FontPaths):
        """価格が None の場合"""
        data = OgpData(
            item_name="テスト商品",
            best_price=None,
            best_store="TestStore",
            lowest_price=None,
            thumb_path=None,
            store_histories=[],
        )
        img = generate_ogp_image_square(data, font_paths=font_paths)

        assert isinstance(img, Image.Image)
        assert img.size == (OGP_SQUARE_SIZE, OGP_SQUARE_SIZE)

    def test_generate_with_long_name(self, font_paths: FontPaths):
        """長い商品名の場合（切り詰めが発生）"""
        long_name = "これは非常に長い商品名です" * 10
        data = OgpData(
            item_name=long_name,
            best_price=1000,
            best_store="TestStore",
            lowest_price=950,
            thumb_path=None,
            store_histories=[],
        )
        img = generate_ogp_image_square(data, font_paths=font_paths)

        assert isinstance(img, Image.Image)
        assert img.size == (OGP_SQUARE_SIZE, OGP_SQUARE_SIZE)


class TestCacheFunctions:
    """キャッシュ関連関数のテスト"""

    def test_get_cache_path(self):
        """キャッシュパス生成"""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = pathlib.Path(tmpdir)
            path = get_cache_path("test_item", cache_dir)

            assert path.parent == cache_dir / "ogp"
            assert path.suffix == ".png"
            assert "test_item" in path.stem

    def test_get_cache_path_special_chars(self):
        """特殊文字を含む item_key"""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = pathlib.Path(tmpdir)
            path = get_cache_path("item/with:special?chars", cache_dir)

            assert path.exists() is False
            # 特殊文字がサニタイズされていること
            assert "/" not in path.name
            assert ":" not in path.name
            assert "?" not in path.name

    def test_get_cache_path_square(self):
        """正方形 OGP のキャッシュパス生成"""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = pathlib.Path(tmpdir)
            path = get_cache_path("test_item", cache_dir, square=True)

            assert path.parent == cache_dir / "ogp"
            assert path.suffix == ".png"
            assert "test_item" in path.stem
            assert "_square" in path.stem

    def test_get_cache_path_square_vs_normal(self):
        """正方形と通常のキャッシュパスが異なること"""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = pathlib.Path(tmpdir)
            path_normal = get_cache_path("test_item", cache_dir, square=False)
            path_square = get_cache_path("test_item", cache_dir, square=True)

            assert path_normal != path_square
            assert "_square" not in path_normal.stem
            assert "_square" in path_square.stem

    def test_is_cache_valid_not_exists(self):
        """キャッシュファイルが存在しない場合"""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = pathlib.Path(tmpdir) / "nonexistent.png"
            assert is_cache_valid(cache_path) is False

    def test_is_cache_valid_fresh(self):
        """有効なキャッシュ"""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = pathlib.Path(tmpdir) / "test.png"
            cache_path.write_text("test")  # ダミーファイル作成

            assert is_cache_valid(cache_path, ttl_sec=3600) is True

    def test_is_cache_valid_expired(self):
        """期限切れキャッシュ"""
        import os
        import time

        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = pathlib.Path(tmpdir) / "test.png"
            cache_path.write_text("test")

            # ファイルの更新時刻を過去に設定
            old_time = time.time() - 7200  # 2時間前
            os.utime(cache_path, (old_time, old_time))

            assert is_cache_valid(cache_path, ttl_sec=3600) is False

    def test_save_ogp_image(self):
        """OGP 画像の保存"""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = pathlib.Path(tmpdir) / "subdir" / "test.png"
            img = Image.new("RGB", (100, 100), color="white")

            save_ogp_image(img, output_path)

            assert output_path.exists()
            saved_img = Image.open(output_path)
            assert saved_img.size == (100, 100)


class TestGetOrGenerateOgpImage:
    """get_or_generate_ogp_image のテスト"""

    def test_generate_new(self, font_paths: FontPaths):
        """新規生成"""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = pathlib.Path(tmpdir)
            data = OgpData(
                item_name="テスト商品",
                best_price=1000,
                best_store="TestStore",
                lowest_price=950,
                thumb_path=None,
                store_histories=[],
            )

            path = get_or_generate_ogp_image("test_item", data, cache_dir, font_paths=font_paths)

            assert path.exists()
            img = Image.open(path)
            assert img.size == (OGP_WIDTH, OGP_HEIGHT)

    def test_use_cache(self, font_paths: FontPaths):
        """キャッシュの利用"""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = pathlib.Path(tmpdir)
            data = OgpData(
                item_name="テスト商品",
                best_price=1000,
                best_store="TestStore",
                lowest_price=950,
                thumb_path=None,
                store_histories=[],
            )

            # 1回目: 生成
            path1 = get_or_generate_ogp_image("test_item", data, cache_dir, font_paths=font_paths)
            mtime1 = path1.stat().st_mtime

            # 2回目: キャッシュ利用（ファイルは更新されない）
            path2 = get_or_generate_ogp_image("test_item", data, cache_dir, font_paths=font_paths)
            mtime2 = path2.stat().st_mtime

            assert path1 == path2
            assert mtime1 == mtime2


class TestGetOrGenerateOgpImageSquare:
    """get_or_generate_ogp_image_square のテスト"""

    def test_generate_new(self, font_paths: FontPaths):
        """新規生成"""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = pathlib.Path(tmpdir)
            data = OgpData(
                item_name="テスト商品",
                best_price=1000,
                best_store="TestStore",
                lowest_price=950,
                thumb_path=None,
                store_histories=[],
            )

            path = get_or_generate_ogp_image_square("test_item", data, cache_dir, font_paths=font_paths)

            assert path.exists()
            assert "_square" in path.stem
            img = Image.open(path)
            assert img.size == (OGP_SQUARE_SIZE, OGP_SQUARE_SIZE)

    def test_use_cache(self, font_paths: FontPaths):
        """キャッシュの利用"""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = pathlib.Path(tmpdir)
            data = OgpData(
                item_name="テスト商品",
                best_price=1000,
                best_store="TestStore",
                lowest_price=950,
                thumb_path=None,
                store_histories=[],
            )

            # 1回目: 生成
            path1 = get_or_generate_ogp_image_square("test_item", data, cache_dir, font_paths=font_paths)
            mtime1 = path1.stat().st_mtime

            # 2回目: キャッシュ利用（ファイルは更新されない）
            path2 = get_or_generate_ogp_image_square("test_item", data, cache_dir, font_paths=font_paths)
            mtime2 = path2.stat().st_mtime

            assert path1 == path2
            assert mtime1 == mtime2

    def test_separate_cache_from_normal(self, font_paths: FontPaths):
        """通常版と正方形版で別々にキャッシュされること"""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = pathlib.Path(tmpdir)
            data = OgpData(
                item_name="テスト商品",
                best_price=1000,
                best_store="TestStore",
                lowest_price=950,
                thumb_path=None,
                store_histories=[],
            )

            # 通常版を生成
            path_normal = get_or_generate_ogp_image("test_item", data, cache_dir, font_paths=font_paths)
            # 正方形版を生成
            path_square = get_or_generate_ogp_image_square(
                "test_item", data, cache_dir, font_paths=font_paths
            )

            # 別々のファイルであること
            assert path_normal != path_square
            assert path_normal.exists()
            assert path_square.exists()

            # サイズが異なること
            img_normal = Image.open(path_normal)
            img_square = Image.open(path_square)
            assert img_normal.size == (OGP_WIDTH, OGP_HEIGHT)
            assert img_square.size == (OGP_SQUARE_SIZE, OGP_SQUARE_SIZE)


class TestFontHandling:
    """フォント関連のテスト"""

    def test_get_pillow_font_fallback(self):
        """フォールバック時はデフォルトフォントを使用"""
        from unittest.mock import patch

        import price_watch.webapi.ogp

        # フォールバックを None にして、デフォルトフォントを返すことを確認
        with patch.object(price_watch.webapi.ogp, "_find_fallback_font", return_value=None):
            font = price_watch.webapi.ogp._get_pillow_font(20, None)
            assert font is not None

    def test_get_pillow_font_with_invalid_path(self):
        """無効なパスが指定された場合はフォールバック"""
        from unittest.mock import patch

        import price_watch.webapi.ogp

        invalid_path = pathlib.Path("/nonexistent/font.ttf")

        # フォールバックフォントも見つからない場合
        with patch.object(price_watch.webapi.ogp, "_find_fallback_font", return_value=None):
            font = price_watch.webapi.ogp._get_pillow_font(20, invalid_path)
            # デフォルトフォントが返される
            assert font is not None

    def test_setup_matplotlib_font_with_invalid_path(self):
        """無効なフォントパスでも例外が発生しない"""
        from unittest.mock import patch

        import price_watch.webapi.ogp

        invalid_path = pathlib.Path("/nonexistent/font.ttf")

        # フォールバックフォントも見つからない場合
        with patch.object(price_watch.webapi.ogp, "_find_fallback_font", return_value=None):
            # 例外が発生しないことを確認
            price_watch.webapi.ogp._setup_matplotlib_font(invalid_path)

    def test_find_fallback_font_not_found(self):
        """フォールバックフォントが見つからない場合"""
        from unittest.mock import patch

        import price_watch.webapi.ogp

        # すべてのフォントパスが存在しない
        with patch.object(pathlib.Path, "exists", return_value=False):
            result = price_watch.webapi.ogp._find_fallback_font()
            assert result is None

    def test_font_paths_from_config_none(self):
        """FontConfig が None の場合"""
        result = FontPaths.from_config(None)
        assert result.jp_regular is None
        assert result.jp_medium is None
        assert result.jp_bold is None


class TestGraphGeneration:
    """グラフ生成のテスト"""

    def test_generate_price_graph_no_data(self, font_paths: FontPaths):
        """データがない場合"""
        import price_watch.webapi.ogp

        # 空の履歴
        result = price_watch.webapi.ogp._generate_price_graph([], font_paths)
        assert isinstance(result, Image.Image)

    def test_generate_price_graph_none_prices(self, font_paths: FontPaths):
        """価格がすべて None の場合"""
        import price_watch.webapi.ogp

        store_history = StoreHistory(
            store_name="TestStore",
            color="#3b82f6",
            history=[
                {"time": "2026-01-01 12:00:00", "price": None, "effective_price": None},
            ],
        )

        result = price_watch.webapi.ogp._generate_price_graph([store_history], font_paths)
        assert isinstance(result, Image.Image)

    def test_generate_price_graph_invalid_datetime(self, font_paths: FontPaths):
        """無効な日時形式の場合"""
        import price_watch.webapi.ogp

        store_history = StoreHistory(
            store_name="TestStore",
            color="#3b82f6",
            history=[
                {"time": "invalid-datetime", "price": 1000, "effective_price": 950},
            ],
        )

        result = price_watch.webapi.ogp._generate_price_graph([store_history], font_paths)
        assert isinstance(result, Image.Image)

    def test_generate_price_graph_x_axis_only_no_data(self, font_paths: FontPaths):
        """X軸のみグラフでデータがない場合"""
        import price_watch.webapi.ogp

        result = price_watch.webapi.ogp._generate_price_graph_x_axis_only(
            [], OGP_SQUARE_SIZE, OGP_SQUARE_SIZE, font_paths
        )
        assert isinstance(result, Image.Image)

    def test_generate_price_graph_single_point(self, font_paths: FontPaths):
        """1点のみのデータの場合"""
        import price_watch.webapi.ogp

        store_history = StoreHistory(
            store_name="TestStore",
            color="#3b82f6",
            history=[
                {"time": "2026-01-01 12:00:00", "price": 1000, "effective_price": 950},
            ],
        )

        result = price_watch.webapi.ogp._generate_price_graph([store_history], font_paths)
        assert isinstance(result, Image.Image)

    def test_generate_price_graph_many_points(self, font_paths: FontPaths):
        """多数のデータポイントの場合（マーカーなし）"""
        import price_watch.webapi.ogp

        # 30日分のデータ（マーカー非表示条件: > 20ポイント）
        history = [
            {"time": f"2026-01-{i:02d} 12:00:00", "price": 1000 + i * 10, "effective_price": 950 + i * 10}
            for i in range(1, 31)
        ]
        store_history = StoreHistory(
            store_name="TestStore",
            color="#3b82f6",
            history=history,
        )

        result = price_watch.webapi.ogp._generate_price_graph([store_history], font_paths)
        assert isinstance(result, Image.Image)


class TestImageComposition:
    """画像合成のテスト"""

    def test_generate_ogp_with_thumbnail(self, font_paths: FontPaths):
        """サムネイルありの OGP 画像生成"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # ダミーサムネイルを作成
            thumb_path = pathlib.Path(tmpdir) / "thumb.png"
            thumb_img = Image.new("RGB", (200, 300), color="blue")
            thumb_img.save(thumb_path)

            data = OgpData(
                item_name="テスト商品",
                best_price=1000,
                best_store="TestStore",
                lowest_price=950,
                thumb_path=thumb_path,
                store_histories=[],
            )

            img = generate_ogp_image(data, font_paths=font_paths)

            assert isinstance(img, Image.Image)
            assert img.size == (OGP_WIDTH, OGP_HEIGHT)

    def test_generate_ogp_square_with_thumbnail(self, font_paths: FontPaths):
        """サムネイルありの正方形 OGP 画像生成"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # ダミーサムネイルを作成
            thumb_path = pathlib.Path(tmpdir) / "thumb.png"
            thumb_img = Image.new("RGB", (200, 300), color="blue")
            thumb_img.save(thumb_path)

            data = OgpData(
                item_name="テスト商品",
                best_price=1000,
                best_store="TestStore",
                lowest_price=950,
                thumb_path=thumb_path,
                store_histories=[],
            )

            img = generate_ogp_image_square(data, font_paths=font_paths)

            assert isinstance(img, Image.Image)
            assert img.size == (OGP_SQUARE_SIZE, OGP_SQUARE_SIZE)

    def test_generate_ogp_with_invalid_thumbnail(self, font_paths: FontPaths):
        """無効なサムネイルパスの場合"""
        data = OgpData(
            item_name="テスト商品",
            best_price=1000,
            best_store="TestStore",
            lowest_price=950,
            thumb_path=pathlib.Path("/nonexistent/thumb.png"),
            store_histories=[],
        )

        # 例外が発生せず画像が生成されること
        img = generate_ogp_image(data, font_paths=font_paths)
        assert isinstance(img, Image.Image)

    def test_generate_ogp_with_rgba_thumbnail(self, font_paths: FontPaths):
        """RGBA サムネイルの場合"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # RGBA サムネイルを作成
            thumb_path = pathlib.Path(tmpdir) / "thumb.png"
            thumb_img = Image.new("RGBA", (200, 300), color=(0, 0, 255, 128))
            thumb_img.save(thumb_path)

            data = OgpData(
                item_name="テスト商品",
                best_price=1000,
                best_store="TestStore",
                lowest_price=950,
                thumb_path=thumb_path,
                store_histories=[],
            )

            img = generate_ogp_image(data, font_paths=font_paths)
            assert isinstance(img, Image.Image)

    def test_generate_ogp_with_history_and_thumbnail(self, font_paths: FontPaths):
        """履歴とサムネイル両方がある場合"""
        with tempfile.TemporaryDirectory() as tmpdir:
            thumb_path = pathlib.Path(tmpdir) / "thumb.png"
            thumb_img = Image.new("RGB", (200, 300), color="green")
            thumb_img.save(thumb_path)

            store_history = StoreHistory(
                store_name="TestStore",
                color="#3b82f6",
                history=[
                    {"time": "2026-01-01 12:00:00", "price": 1000, "effective_price": 950},
                    {"time": "2026-01-02 12:00:00", "price": 1100, "effective_price": 1050},
                ],
            )
            data = OgpData(
                item_name="テスト商品",
                best_price=1000,
                best_store="TestStore",
                lowest_price=950,
                thumb_path=thumb_path,
                store_histories=[store_history],
            )

            img = generate_ogp_image(data, font_paths=font_paths)
            assert isinstance(img, Image.Image)
            assert img.size == (OGP_WIDTH, OGP_HEIGHT)


class TestTextHelpers:
    """テキストヘルパー関数のテスト"""

    def test_format_price(self):
        """価格フォーマット"""
        import price_watch.webapi.ogp

        assert price_watch.webapi.ogp._format_price(1000) == "¥1,000"
        assert price_watch.webapi.ogp._format_price(1234567) == "¥1,234,567"
        assert price_watch.webapi.ogp._format_price(None) == "---"

    def test_truncate_text_short(self):
        """短いテキストは切り詰めなし"""
        import price_watch.webapi.ogp

        img = Image.new("RGB", (100, 100))
        font = price_watch.webapi.ogp._get_pillow_font(20)
        result = price_watch.webapi.ogp._truncate_text(img, "Short", font, 1000)
        assert result == "Short"

    def test_truncate_text_long(self):
        """長いテキストは切り詰め"""
        import price_watch.webapi.ogp

        img = Image.new("RGB", (100, 100))
        font = price_watch.webapi.ogp._get_pillow_font(20)
        long_text = "This is a very long text that should be truncated"
        result = price_watch.webapi.ogp._truncate_text(img, long_text, font, 50)
        assert result.endswith("...")
        assert len(result) < len(long_text)

    def test_sanitize_filename(self):
        """ファイル名サニタイズ"""
        import price_watch.webapi.ogp

        # 特殊文字がアンダースコアに置換される
        assert price_watch.webapi.ogp._sanitize_filename("test/item:key?") == "test_item_key_"
        # 長いファイル名は切り詰め
        long_name = "a" * 150
        assert len(price_watch.webapi.ogp._sanitize_filename(long_name)) <= 100


class TestDrawRoundedRect:
    """角丸矩形描画のテスト"""

    def test_draw_rounded_rect_overlay(self):
        """角丸矩形オーバーレイ"""
        import price_watch.webapi.ogp

        img = Image.new("RGB", (200, 200), color="white")
        result = price_watch.webapi.ogp._draw_rounded_rect_overlay(
            img, (10, 10, 100, 100), radius=10, alpha=200
        )

        assert isinstance(result, Image.Image)
        assert result.mode == "RGB"
        assert result.size == (200, 200)


class TestFontFunctions:
    """フォント関連機能のテスト"""

    def test_find_fallback_font_success(self):
        """フォールバックフォントが見つかる場合"""
        from unittest.mock import patch

        import price_watch.webapi.ogp

        # フォントが存在する場合をシミュレート
        with patch("pathlib.Path.exists", return_value=True):
            result = price_watch.webapi.ogp._find_fallback_font()

        # パスが返される
        assert result is not None
        assert isinstance(result, str)

    def test_get_pillow_font_with_invalid_path(self):
        """無効なフォントパスの場合の処理"""
        import pathlib

        import price_watch.webapi.ogp

        # 存在しないフォントパスを指定
        invalid_path = pathlib.Path("/nonexistent/font.ttf")
        result = price_watch.webapi.ogp._get_pillow_font(20, invalid_path)

        # デフォルトフォントが返される
        assert result is not None

    def test_setup_matplotlib_font_exception(self):
        """matplotlib フォント設定失敗時の処理"""
        import pathlib
        from unittest.mock import MagicMock, patch

        import price_watch.webapi.ogp

        mock_font_path = MagicMock(spec=pathlib.Path)
        mock_font_path.exists.return_value = True
        mock_font_path.__str__ = MagicMock(return_value="/test/font.ttf")

        # addfont が例外を発生させる場合
        with patch("matplotlib.font_manager.fontManager.addfont", side_effect=Exception("Font error")):
            # 例外が発生しても処理が続行される
            price_watch.webapi.ogp._setup_matplotlib_font(mock_font_path)


class TestThumbnailProcessing:
    """サムネイル処理のテスト"""

    def test_thumbnail_width_limited(self, tmp_path):
        """サムネイルが幅で制限される場合"""
        # 横長の画像を作成（幅で制限される）
        wide_thumb = Image.new("RGB", (400, 100), color="blue")
        thumb_path = tmp_path / "wide_thumb.png"
        wide_thumb.save(thumb_path)

        data = OgpData(
            item_name="Test Item",
            best_price=1000,
            best_store="Store",
            lowest_price=900,
            store_histories=[],
            thumb_path=thumb_path,
        )

        result = generate_ogp_image(data)

        assert result.size == (OGP_WIDTH, OGP_HEIGHT)

    def test_thumbnail_load_failure(self, tmp_path):
        """サムネイル読み込み失敗時の処理"""
        # 壊れた画像ファイルを作成
        bad_thumb_path = tmp_path / "bad_thumb.png"
        bad_thumb_path.write_text("not an image")

        data = OgpData(
            item_name="Test Item",
            best_price=1000,
            best_store="Store",
            lowest_price=900,
            store_histories=[],
            thumb_path=bad_thumb_path,
        )

        # 例外が発生しても画像は生成される
        result = generate_ogp_image(data)
        assert result.size == (OGP_WIDTH, OGP_HEIGHT)

    def test_thumbnail_load_failure_square(self, tmp_path):
        """正方形画像のサムネイル読み込み失敗時"""
        bad_thumb_path = tmp_path / "bad_thumb.png"
        bad_thumb_path.write_text("not an image")

        data = OgpData(
            item_name="Test Item",
            best_price=1000,
            best_store="Store",
            lowest_price=900,
            store_histories=[],
            thumb_path=bad_thumb_path,
        )

        result = generate_ogp_image_square(data)
        assert result.size == (OGP_SQUARE_SIZE, OGP_SQUARE_SIZE)


class TestFontFallbackPath:
    """フォントフォールバックパスのテスト"""

    def test_generate_image_with_default_font(self):
        """デフォルトフォントで画像を生成"""
        from unittest.mock import patch

        data = OgpData(
            item_name="Test Item",
            best_price=1000,
            best_store="Store",
            lowest_price=900,
            store_histories=[],
            thumb_path=None,
        )

        # フォールバックフォントが見つからない場合
        with patch("price_watch.webapi.ogp._find_fallback_font", return_value=None):
            result = generate_ogp_image(data)

        assert result.size == (OGP_WIDTH, OGP_HEIGHT)

    def test_generate_square_image_with_default_font(self):
        """デフォルトフォントで正方形画像を生成"""
        from unittest.mock import patch

        data = OgpData(
            item_name="Test Item",
            best_price=1000,
            best_store="Store",
            lowest_price=900,
            store_histories=[],
            thumb_path=None,
        )

        with patch("price_watch.webapi.ogp._find_fallback_font", return_value=None):
            result = generate_ogp_image_square(data)

        assert result.size == (OGP_SQUARE_SIZE, OGP_SQUARE_SIZE)


class TestGraphEmptyAfterParsing:
    """datetime パース後にデータが空になるケースのテスト"""

    def test_all_invalid_datetime(self):
        """全ての datetime が無効な場合"""
        # 無効な形式の時間データ
        invalid_history = [
            StoreHistory(
                store_name="Store1",
                color="#4285F4",
                history=[
                    {"time": "invalid_time", "effective_price": 1000},
                    {"time": "also_invalid", "effective_price": 900},
                ],
            )
        ]

        data = OgpData(
            item_name="Test",
            best_price=1000,
            best_store="Store1",
            lowest_price=900,
            store_histories=invalid_history,
            thumb_path=None,
        )

        # 画像は生成される（グラフ部分は "価格情報なし" 表示になる）
        result = generate_ogp_image(data)
        assert result.size == (OGP_WIDTH, OGP_HEIGHT)


class TestThumbnailHeightLimited:
    """サムネイルが高さで制限されるケースのテスト"""

    def test_thumbnail_height_limited_square(self, tmp_path):
        """正方形画像でサムネイルが高さで制限される場合"""
        # 縦長の画像を作成（高さで制限される）
        tall_thumb = Image.new("RGB", (100, 800), color="red")
        thumb_path = tmp_path / "tall_thumb.png"
        tall_thumb.save(thumb_path)

        data = OgpData(
            item_name="Test Item",
            best_price=1000,
            best_store="Store",
            lowest_price=900,
            store_histories=[],
            thumb_path=thumb_path,
        )

        result = generate_ogp_image_square(data)
        assert result.size == (OGP_SQUARE_SIZE, OGP_SQUARE_SIZE)
