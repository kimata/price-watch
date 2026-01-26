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
