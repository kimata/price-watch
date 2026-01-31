#!/usr/bin/env python3
# ruff: noqa: S101, S105, S108
"""
config モジュールのユニットテスト

設定ファイル構造を検証します。
"""

from __future__ import annotations

import pathlib
from unittest.mock import patch

from price_watch.config import (
    AppConfig,
    CheckConfig,
    CurrencyRate,
    DataConfig,
    DropConfig,
    FontConfig,
    FontMapConfig,
    IgnoreConfig,
    JudgeConfig,
    LivenessConfig,
    LivenessFileConfig,
    LowestConfig,
    PriceDropWindow,
    StoreConfig,
    TargetConfig,
    load,
)


class TestPriceDropWindow:
    """PriceDropWindow のテスト"""

    def test_parse_with_all_fields(self) -> None:
        """全フィールド指定"""
        data = {"days": 7, "rate": 5.0, "value": 1000}
        result = PriceDropWindow.parse(data)
        assert result.days == 7
        assert result.rate == 5.0
        assert result.value == 1000

    def test_parse_with_defaults(self) -> None:
        """デフォルト値を使用"""
        data: dict[str, int] = {}
        result = PriceDropWindow.parse(data)
        assert result.days == 30
        assert result.rate is None
        assert result.value is None

    def test_parse_with_only_days(self) -> None:
        """days のみ指定"""
        data = {"days": 14}
        result = PriceDropWindow.parse(data)
        assert result.days == 14
        assert result.rate is None
        assert result.value is None

    def test_parse_nested_price_format(self) -> None:
        """ネスト形式: price: {rate, value}"""
        data = {"days": 7, "price": {"rate": 10.0, "value": 1000}}
        result = PriceDropWindow.parse(data)
        assert result.days == 7
        assert result.rate == 10.0
        assert result.value == 1000

    def test_parse_nested_price_partial(self) -> None:
        """ネスト形式: price に rate のみ"""
        data = {"days": 7, "price": {"rate": 5.0}}
        result = PriceDropWindow.parse(data)
        assert result.days == 7
        assert result.rate == 5.0
        assert result.value is None


class TestIgnoreConfig:
    """IgnoreConfig のテスト"""

    def test_parse_with_hour(self) -> None:
        """hour 指定"""
        data = {"hour": 48}
        result = IgnoreConfig.parse(data)
        assert result.hour == 48

    def test_parse_with_default(self) -> None:
        """デフォルト値"""
        data: dict[str, int] = {}
        result = IgnoreConfig.parse(data)
        assert result.hour == 24


class TestDropConfig:
    """DropConfig のテスト"""

    def test_parse_with_windows(self) -> None:
        """windows 配列を解析"""
        data = {
            "ignore": {"hour": 12},
            "windows": [
                {"days": 30, "rate": 10.0},
                {"days": 7, "rate": 5.0},  # 順番がバラバラ
            ],
        }
        result = DropConfig.parse(data)
        assert result.ignore.hour == 12
        # days で昇順ソートされる
        assert len(result.windows) == 2
        assert result.windows[0].days == 7
        assert result.windows[1].days == 30

    def test_parse_empty(self) -> None:
        """空の設定"""
        data: dict[str, list[dict[str, int]]] = {}
        result = DropConfig.parse(data)
        assert result.ignore.hour == 24
        assert result.windows == []

    def test_judge_config_alias(self) -> None:
        """JudgeConfig は DropConfig のエイリアス"""
        assert JudgeConfig is DropConfig


class TestLowestConfig:
    """LowestConfig のテスト"""

    def test_parse_with_all_fields(self) -> None:
        """全フィールド指定"""
        data = {"rate": 1.0, "value": 100}
        result = LowestConfig.parse(data)
        assert result.rate == 1.0
        assert result.value == 100

    def test_parse_with_defaults(self) -> None:
        """デフォルト値"""
        data: dict[str, float] = {}
        result = LowestConfig.parse(data)
        assert result.rate is None
        assert result.value is None

    def test_parse_rate_only(self) -> None:
        """rate のみ指定"""
        data = {"rate": 5.0}
        result = LowestConfig.parse(data)
        assert result.rate == 5.0
        assert result.value is None


class TestCurrencyRate:
    """CurrencyRate のテスト"""

    def test_parse(self) -> None:
        """基本的なパース"""
        data = {"label": "ドル", "rate": 150.0}
        result = CurrencyRate.parse(data)
        assert result.label == "ドル"
        assert result.rate == 150.0


class TestCheckConfig:
    """CheckConfig のテスト"""

    def test_parse_with_drop(self) -> None:
        """新形式: drop 指定"""
        data = {"interval_sec": 3600, "drop": {"ignore": {"hour": 6}, "windows": []}}
        result = CheckConfig.parse(data)
        assert result.interval_sec == 3600
        assert result.drop is not None
        assert result.drop.ignore.hour == 6

    def test_parse_with_judge_backward_compat(self) -> None:
        """旧形式: judge は drop にマッピングされる"""
        data = {"interval_sec": 3600, "judge": {"ignore": {"hour": 6}, "windows": []}}
        result = CheckConfig.parse(data)
        assert result.drop is not None
        assert result.drop.ignore.hour == 6

    def test_parse_with_lowest(self) -> None:
        """lowest 設定"""
        data = {"lowest": {"rate": 1.0, "value": 100}}
        result = CheckConfig.parse(data)
        assert result.lowest is not None
        assert result.lowest.rate == 1.0
        assert result.lowest.value == 100

    def test_parse_with_currency(self) -> None:
        """currency 設定"""
        data = {"currency": [{"label": "ドル", "rate": 150.0}]}
        result = CheckConfig.parse(data)
        assert len(result.currency) == 1
        assert result.currency[0].label == "ドル"
        assert result.currency[0].rate == 150.0

    def test_parse_with_defaults(self) -> None:
        """デフォルト値"""
        data: dict[str, int] = {}
        result = CheckConfig.parse(data)
        assert result.interval_sec == 1800
        assert result.drop is None
        assert result.lowest is None
        assert len(result.currency) == 0


class TestStoreConfig:
    """StoreConfig のテスト"""

    def test_parse_with_amazon(self) -> None:
        """Amazon 設定あり"""
        data = {
            "amazon": {
                "associate": "test-22",
                "access_key": "ACCESSKEY",
                "secret_key": "SECRETKEY",
                "host": "webservices.amazon.co.jp",
                "region": "us-west-2",
            }
        }
        result = StoreConfig.parse(data)
        assert result.amazon_api is not None
        assert result.amazon_api.associate == "test-22"

    def test_parse_without_amazon(self) -> None:
        """Amazon 設定なし"""
        data: dict[str, str] = {}
        result = StoreConfig.parse(data)
        assert result.amazon_api is None

    def test_default_instance(self) -> None:
        """デフォルトインスタンス"""
        config = StoreConfig()
        assert config.amazon_api is None


class TestDataConfig:
    """DataConfig のテスト"""

    def test_parse_with_all_paths(self) -> None:
        """全パス指定"""
        data = {
            "selenium": "/data/selenium",
            "dump": "/data/dump",
            "price": "/data/price",
            "thumb": "/data/thumb",
            "metrics": "/data/metrics",
            "cache": "/data/cache",
        }
        result = DataConfig.parse(data)
        assert result.selenium == pathlib.Path("/data/selenium")
        assert result.dump == pathlib.Path("/data/dump")
        assert result.price == pathlib.Path("/data/price")
        assert result.thumb == pathlib.Path("/data/thumb")
        assert result.metrics == pathlib.Path("/data/metrics")
        assert result.cache == pathlib.Path("/data/cache")

    def test_parse_with_defaults(self) -> None:
        """デフォルト値"""
        data: dict[str, str] = {}
        result = DataConfig.parse(data)
        # デフォルトパスが設定される（絶対パスかどうかは環境依存）
        assert isinstance(result.selenium, pathlib.Path)
        assert isinstance(result.dump, pathlib.Path)


class TestTargetConfig:
    """TargetConfig のテスト"""

    def test_parse_with_define(self) -> None:
        """define 指定"""
        data = {"define": "my_target.yaml"}
        result = TargetConfig.parse(data)
        assert result.define == "my_target.yaml"

    def test_parse_with_default(self) -> None:
        """デフォルト値"""
        data: dict[str, str] = {}
        result = TargetConfig.parse(data)
        assert result.define == "target.yaml"


class TestFontMapConfig:
    """FontMapConfig のテスト"""

    def test_parse_with_all_fonts(self) -> None:
        """全フォント指定"""
        data = {
            "jp_regular": "NotoSansJP-Regular.ttf",
            "jp_medium": "NotoSansJP-Medium.ttf",
            "jp_bold": "NotoSansJP-Bold.ttf",
            "en_medium": "Roboto-Medium.ttf",
            "en_bold": "Roboto-Bold.ttf",
        }
        result = FontMapConfig.parse(data)
        assert result.jp_regular == "NotoSansJP-Regular.ttf"
        assert result.jp_medium == "NotoSansJP-Medium.ttf"
        assert result.jp_bold == "NotoSansJP-Bold.ttf"
        assert result.en_medium == "Roboto-Medium.ttf"
        assert result.en_bold == "Roboto-Bold.ttf"

    def test_parse_empty(self) -> None:
        """空の設定"""
        data: dict[str, str] = {}
        result = FontMapConfig.parse(data)
        assert result.jp_regular is None
        assert result.jp_medium is None


class TestFontConfig:
    """FontConfig のテスト"""

    def test_parse_with_path(self) -> None:
        """パス指定"""
        data = {"path": "/fonts", "map": {"jp_regular": "jp.ttf"}}
        result = FontConfig.parse(data)
        assert result.path == pathlib.Path("/fonts")
        assert result.map.jp_regular == "jp.ttf"

    def test_parse_without_path(self) -> None:
        """パスなし"""
        data = {"map": {"jp_regular": "jp.ttf"}}
        result = FontConfig.parse(data)
        assert result.path is None

    def test_get_font_path_with_all_set(self) -> None:
        """フォントパスを取得"""
        data = {"path": "/fonts", "map": {"jp_regular": "jp.ttf"}}
        config = FontConfig.parse(data)
        result = config.get_font_path("jp_regular")
        assert result == pathlib.Path("/fonts/jp.ttf")

    def test_get_font_path_without_path(self) -> None:
        """パスがない場合は None"""
        data = {"map": {"jp_regular": "jp.ttf"}}
        config = FontConfig.parse(data)
        result = config.get_font_path("jp_regular")
        assert result is None

    def test_get_font_path_without_font(self) -> None:
        """フォントがない場合は None"""
        data = {"path": "/fonts", "map": {}}
        config = FontConfig.parse(data)
        result = config.get_font_path("jp_regular")
        assert result is None


class TestLivenessFileConfig:
    """LivenessFileConfig のテスト"""

    def test_parse_with_dict(self) -> None:
        """dict 形式"""
        data = {"crawler": "/tmp/healthz"}
        result = LivenessFileConfig.parse(data)
        assert result.crawler == pathlib.Path("/tmp/healthz")

    def test_parse_with_string(self) -> None:
        """文字列形式（後方互換性）"""
        data = "/tmp/healthz"
        result = LivenessFileConfig.parse(data)  # type: ignore[arg-type]
        assert result.crawler == pathlib.Path("/tmp/healthz")

    def test_parse_with_default(self) -> None:
        """デフォルト値"""
        data: dict[str, str] = {}
        result = LivenessFileConfig.parse(data)
        assert result.crawler == pathlib.Path("/dev/shm/healthz")


class TestLivenessConfig:
    """LivenessConfig のテスト"""

    def test_parse_with_all_fields(self) -> None:
        """全フィールド指定"""
        data = {"file": {"crawler": "/tmp/healthz"}, "interval_sec": 600}
        result = LivenessConfig.parse(data)
        assert result.file.crawler == pathlib.Path("/tmp/healthz")
        assert result.interval_sec == 600

    def test_parse_with_defaults(self) -> None:
        """デフォルト値"""
        data: dict[str, int] = {}
        result = LivenessConfig.parse(data)
        assert result.interval_sec == 300


class TestEditConfig:
    """EditConfig のテスト"""

    def test_parse_with_password_only(self) -> None:
        """パスワードハッシュのみ"""
        from price_watch.config import EditConfig

        data = {"password_hash": "$argon2id$v=19$m=65536,t=3,p=4$test$hash"}
        result = EditConfig.parse(data)
        assert result.password_hash == "$argon2id$v=19$m=65536,t=3,p=4$test$hash"
        assert result.git is None

    def test_parse_with_git(self) -> None:
        """Git 設定あり"""
        from price_watch.config import EditConfig

        data = {
            "password_hash": "$argon2id$v=19$m=65536,t=3,p=4$test$hash",
            "git": {
                "remote_url": "https://gitlab.example.com/user/repo.git",
                "file_path": "config/target.yaml",
                "access_token": "glpat-xxx",
                "branch": "main",
            },
        }
        result = EditConfig.parse(data)
        assert result.password_hash == "$argon2id$v=19$m=65536,t=3,p=4$test$hash"
        assert result.git is not None
        assert result.git.remote_url == "https://gitlab.example.com/user/repo.git"
        assert result.git.file_path == "config/target.yaml"
        assert result.git.access_token == "glpat-xxx"
        assert result.git.branch == "main"

    def test_parse_missing_password_hash_raises(self) -> None:
        """password_hash が欠けている場合は KeyError"""
        import pytest

        from price_watch.config import EditConfig

        data: dict[str, str] = {}
        with pytest.raises(KeyError):
            EditConfig.parse(data)


class TestAppConfig:
    """AppConfig のテスト"""

    def test_parse_minimal(self) -> None:
        """最小構成"""
        data = {
            "webapp": {"static_dir_path": "frontend/dist"},
            "edit": {"password_hash": "$argon2id$v=19$m=65536,t=3,p=4$test$hash"},
        }
        result = AppConfig.parse(data)
        assert result.check.interval_sec == 1800
        assert result.store.amazon_api is None
        assert result.font is None
        assert result.edit.password_hash.startswith("$argon2id$")

    def test_parse_with_font(self) -> None:
        """フォント設定あり"""
        data = {
            "webapp": {"static_dir_path": "frontend/dist"},
            "edit": {"password_hash": "$argon2id$v=19$m=65536,t=3,p=4$test$hash"},
            "font": {"path": "/fonts", "map": {"jp_regular": "jp.ttf"}},
        }
        result = AppConfig.parse(data)
        assert result.font is not None
        assert result.font.path == pathlib.Path("/fonts")

    def test_parse_with_store(self) -> None:
        """ストア設定あり"""
        data = {
            "webapp": {"static_dir_path": "frontend/dist"},
            "edit": {"password_hash": "$argon2id$v=19$m=65536,t=3,p=4$test$hash"},
            "store": {
                "amazon": {
                    "associate": "test-22",
                    "access_key": "key",
                    "secret_key": "secret",
                    "host": "webservices.amazon.co.jp",
                    "region": "us-west-2",
                }
            },
        }
        result = AppConfig.parse(data)
        assert result.store.amazon_api is not None


class TestLoad:
    """load 関数のテスト"""

    def test_load_with_custom_path(self, tmp_path: pathlib.Path) -> None:
        """カスタムパスから読み込み"""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            """
webapp:
    static_dir_path: frontend/dist
edit:
    password_hash: "$argon2id$v=19$m=65536,t=3,p=4$test$hash"
check:
    interval_sec: 900
"""
        )

        result = load(config_file)
        assert result.check.interval_sec == 900

    def test_load_with_none_uses_default(self) -> None:
        """None の場合はデフォルトパスを使用"""
        mock_data = {
            "webapp": {"static_dir_path": "dist"},
            "edit": {"password_hash": "$argon2id$v=19$m=65536,t=3,p=4$test$hash"},
        }

        with patch("my_lib.config.load", return_value=mock_data):
            result = load(None)
            # パス名の最後の部分が一致することを確認（絶対パス変換されている可能性あり）
            assert pathlib.Path(result.webapp.static_dir_path).name == "dist"
