#!/usr/bin/env python3
"""
設定ファイルの構造を定義する dataclass

config.yaml に基づいて型付けされた設定クラスを提供します。
my_lib の既存 dataclass を活用しています。
"""

from __future__ import annotations

import pathlib
from dataclasses import dataclass
from typing import Any

import my_lib.config
import my_lib.notify.slack
import my_lib.store.amazon.config
import my_lib.store.yahoo.config
import my_lib.webapp.config

import price_watch.const

CONFIG_FILE_PATH = pathlib.Path("config.yaml")


@dataclass(frozen=True)
class PriceDropWindow:
    """価格下落判定ウィンドウ"""

    days: int
    rate: float | None = None  # パーセント（例: 5.0 = 5%）
    value: int | None = None  # 絶対値（例: 1000 = 1000円）

    @classmethod
    def parse(cls, data: dict[str, Any]) -> PriceDropWindow:
        """dict から PriceDropWindow を生成.

        以下の2形式に対応:
        - ネスト形式: {days: 7, price: {rate: 10, value: 1000}}
        - フラット形式（後方互換）: {days: 7, rate: 10, value: 1000}
        """
        days = data.get("days", 30)
        price = data.get("price")
        if isinstance(price, dict):
            return cls(
                days=days,
                rate=price.get("rate"),
                value=price.get("value"),
            )
        return cls(
            days=days,
            rate=data.get("rate"),
            value=data.get("value"),
        )


@dataclass(frozen=True)
class IgnoreConfig:
    """無視区間設定"""

    hour: int = 24

    @classmethod
    def parse(cls, data: dict[str, Any]) -> IgnoreConfig:
        """dict から IgnoreConfig を生成"""
        return cls(hour=data.get("hour", 24))


@dataclass(frozen=True)
class DropConfig:
    """価格下落イベント判定設定"""

    ignore: IgnoreConfig
    windows: list[PriceDropWindow]

    @classmethod
    def parse(cls, data: dict[str, Any]) -> DropConfig:
        """dict から DropConfig を生成"""
        ignore = IgnoreConfig.parse(data.get("ignore", {}))
        windows_data = data.get("windows", [])
        windows = [PriceDropWindow.parse(w) for w in windows_data]
        # days が小さい順にソート
        windows = sorted(windows, key=lambda w: w.days)
        return cls(ignore=ignore, windows=windows)


# 後方互換エイリアス
JudgeConfig = DropConfig


@dataclass(frozen=True)
class LowestConfig:
    """最安値更新イベント判定設定"""

    rate: float | None = None  # パーセント（例: 1.0 = 1%）
    value: int | None = None  # 絶対値（例: 100 = 100円）

    @classmethod
    def parse(cls, data: dict[str, Any]) -> LowestConfig:
        """dict から LowestConfig を生成"""
        return cls(
            rate=data.get("rate"),
            value=data.get("value"),
        )


@dataclass(frozen=True)
class CurrencyRate:
    """通貨レート設定"""

    label: str
    rate: float

    @classmethod
    def parse(cls, data: dict[str, Any]) -> CurrencyRate:
        """dict から CurrencyRate を生成"""
        return cls(
            label=data["label"],
            rate=data["rate"],
        )


@dataclass(frozen=True)
class CheckConfig:
    """チェック間隔設定"""

    interval_sec: int = 1800
    drop: DropConfig | None = None
    lowest: LowestConfig | None = None
    currency: list[CurrencyRate] = ()  # type: ignore[assignment]

    @classmethod
    def parse(cls, data: dict[str, Any]) -> CheckConfig:
        """dict から CheckConfig を生成.

        以下の2形式に対応:
        - 新形式: {drop: {...}, lowest: {...}, currency: [...]}
        - 旧形式（後方互換）: {judge: {...}}
        """
        drop = None
        if "drop" in data:
            drop = DropConfig.parse(data["drop"])
        elif "judge" in data:
            drop = DropConfig.parse(data["judge"])

        lowest = None
        if "lowest" in data:
            lowest = LowestConfig.parse(data["lowest"])

        currency_data = data.get("currency", [])
        currency = [CurrencyRate.parse(c) for c in currency_data]

        return cls(
            interval_sec=data.get("interval_sec", 1800),
            drop=drop,
            lowest=lowest,
            currency=currency,
        )


@dataclass(frozen=True)
class StoreConfig:
    """ストア設定"""

    amazon_api: my_lib.store.amazon.config.AmazonApiConfig | None = None
    yahoo_api: my_lib.store.yahoo.config.YahooApiConfig | None = None

    @classmethod
    def parse(cls, data: dict[str, Any]) -> StoreConfig:
        """dict から StoreConfig を生成"""
        amazon_api = None
        if "amazon" in data:
            amazon_api = my_lib.store.amazon.config.AmazonApiConfig.parse(data["amazon"])
        yahoo_api = None
        if "yahoo" in data:
            yahoo_api = my_lib.store.yahoo.config.YahooApiConfig.parse(data["yahoo"])
        return cls(amazon_api=amazon_api, yahoo_api=yahoo_api)


@dataclass(frozen=True)
class DataConfig:
    """データ保存設定"""

    selenium: pathlib.Path
    dump: pathlib.Path
    price: pathlib.Path
    thumb: pathlib.Path
    metrics: pathlib.Path
    cache: pathlib.Path

    @classmethod
    def parse(cls, data: dict[str, Any]) -> DataConfig:
        """dict から DataConfig を生成"""
        default_path = pathlib.Path(__file__).parent.parent.parent / "data"
        return cls(
            selenium=pathlib.Path(data.get("selenium", str(default_path))),
            dump=pathlib.Path(data.get("dump", str(default_path / "debug"))),
            price=pathlib.Path(data.get("price", str(default_path))),
            thumb=pathlib.Path(data.get("thumb", str(default_path / "thumb"))),
            metrics=pathlib.Path(data.get("metrics", str(default_path / "metrics"))),
            cache=pathlib.Path(data.get("cache", str(default_path / "cache"))),
        )


@dataclass(frozen=True)
class TargetConfig:
    """ターゲット設定"""

    define: str = "target.yaml"

    @classmethod
    def parse(cls, data: dict[str, Any]) -> TargetConfig:
        """dict から TargetConfig を生成"""
        return cls(define=data.get("define", "target.yaml"))


@dataclass(frozen=True)
class FontMapConfig:
    """フォントマッピング設定"""

    jp_regular: str | None = None
    jp_medium: str | None = None
    jp_bold: str | None = None
    en_medium: str | None = None
    en_bold: str | None = None

    @classmethod
    def parse(cls, data: dict[str, Any]) -> FontMapConfig:
        """dict から FontMapConfig を生成"""
        return cls(
            jp_regular=data.get("jp_regular"),
            jp_medium=data.get("jp_medium"),
            jp_bold=data.get("jp_bold"),
            en_medium=data.get("en_medium"),
            en_bold=data.get("en_bold"),
        )


@dataclass(frozen=True)
class FontConfig:
    """フォント設定"""

    path: pathlib.Path | None
    map: FontMapConfig

    @classmethod
    def parse(cls, data: dict[str, Any]) -> FontConfig:
        """dict から FontConfig を生成"""
        path = None
        if "path" in data:
            path = pathlib.Path(data["path"])
        return cls(
            path=path,
            map=FontMapConfig.parse(data.get("map", {})),
        )

    def get_font_path(self, font_key: str) -> pathlib.Path | None:
        """フォントキーからフルパスを取得.

        Args:
            font_key: "jp_regular", "jp_medium", "jp_bold", "en_medium", "en_bold"

        Returns:
            フォントファイルのフルパス。設定されていない場合は None。
        """
        font_file = getattr(self.map, font_key, None)
        if font_file is None or self.path is None:
            return None
        return self.path / font_file


@dataclass(frozen=True)
class GitSyncConfig:
    """Git 同期設定"""

    remote_url: str
    file_path: str
    access_token: str
    branch: str = "main"

    @classmethod
    def parse(cls, data: dict[str, Any]) -> GitSyncConfig:
        """dict から GitSyncConfig を生成"""
        return cls(
            remote_url=data["remote_url"],
            file_path=data["file_path"],
            access_token=data["access_token"],
            branch=data.get("branch", "main"),
        )


@dataclass(frozen=True)
class EditConfig:
    """エディタ設定.

    password_hash は必須。git はオプションだが、指定する場合は
    remote_url, file_path, access_token, branch の全てが必須。
    """

    password_hash: str
    git: GitSyncConfig | None = None

    @classmethod
    def parse(cls, data: dict[str, Any]) -> EditConfig:
        """dict から EditConfig を生成.

        Raises:
            KeyError: password_hash が存在しない場合
        """
        git = None
        if "git" in data:
            git = GitSyncConfig.parse(data["git"])
        return cls(
            password_hash=data["password_hash"],
            git=git,
        )


@dataclass(frozen=True)
class LivenessFileConfig:
    """Liveness ファイル設定"""

    crawler: pathlib.Path

    @classmethod
    def parse(cls, data: dict[str, Any]) -> LivenessFileConfig:
        """dict から LivenessFileConfig を生成"""
        default_file = "/dev/shm/healthz"  # noqa: S108
        # 文字列または dict の両方に対応
        if isinstance(data, str):
            return cls(crawler=pathlib.Path(data))
        return cls(crawler=pathlib.Path(data.get("crawler", default_file)))


@dataclass(frozen=True)
class LivenessConfig:
    """Liveness 設定"""

    file: LivenessFileConfig
    interval_sec: int

    @classmethod
    def parse(cls, data: dict[str, Any]) -> LivenessConfig:
        """dict から LivenessConfig を生成"""
        default_file = "/dev/shm/healthz"  # noqa: S108
        file_data = data.get("file", {"check": default_file})
        return cls(
            file=LivenessFileConfig.parse(file_data),
            interval_sec=data.get("interval_sec", 300),
        )


@dataclass(frozen=True)
class AppConfig:
    """アプリケーション設定（config.yaml）"""

    check: CheckConfig
    slack: my_lib.notify.slack.SlackConfigTypes
    store: StoreConfig
    data: DataConfig
    webapp: my_lib.webapp.config.WebappConfig
    target: TargetConfig
    liveness: LivenessConfig
    edit: EditConfig
    font: FontConfig | None = None

    @classmethod
    def parse(cls, data: dict[str, Any]) -> AppConfig:
        """dict から AppConfig を生成"""
        # Check 設定
        check = CheckConfig.parse(data.get("check", {}))

        # Slack 設定
        slack: my_lib.notify.slack.SlackConfigTypes = my_lib.notify.slack.SlackEmptyConfig()
        if "slack" in data:
            slack = my_lib.notify.slack.SlackConfig.parse(data["slack"])

        # Store 設定
        store = StoreConfig()
        if "store" in data:
            store = StoreConfig.parse(data["store"])

        # Data 設定
        data_config = DataConfig.parse(data.get("data", {}))

        # Webapp 設定（必須）
        webapp = my_lib.webapp.config.WebappConfig.parse(data["webapp"])

        # Target 設定
        target = TargetConfig.parse(data.get("target", {}))

        # Liveness 設定
        liveness = LivenessConfig.parse(data.get("liveness", {}))

        # Edit 設定（必須）
        edit = EditConfig.parse(data["edit"])

        # Font 設定
        font = None
        if "font" in data:
            font = FontConfig.parse(data["font"])

        return cls(
            check=check,
            slack=slack,
            store=store,
            data=data_config,
            webapp=webapp,
            target=target,
            liveness=liveness,
            edit=edit,
            font=font,
        )


def load(config_file: pathlib.Path | None = None) -> AppConfig:
    """設定ファイルを読み込んで AppConfig を返す.

    Args:
        config_file: 設定ファイルパス。省略時は CONFIG_FILE_PATH を使用。
    """
    if config_file is None:
        config_file = CONFIG_FILE_PATH
    raw = my_lib.config.load(str(config_file), price_watch.const.SCHEMA_CONFIG)
    return AppConfig.parse(raw)
