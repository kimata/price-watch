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
from my_lib.notify.slack import SlackConfig, SlackConfigTypes, SlackEmptyConfig
from my_lib.store.amazon.config import AmazonApiConfig

CONFIG_FILE_PATH = "config.yaml"


@dataclass(frozen=True)
class CheckConfig:
    """チェック間隔設定"""

    interval_sec: int = 1800

    @classmethod
    def parse(cls, data: dict[str, Any]) -> CheckConfig:
        """dict から CheckConfig を生成"""
        return cls(interval_sec=data.get("interval_sec", 1800))


@dataclass(frozen=True)
class StoreConfig:
    """ストア設定"""

    amazon_api: AmazonApiConfig | None = None

    @classmethod
    def parse(cls, data: dict[str, Any]) -> StoreConfig:
        """dict から StoreConfig を生成"""
        amazon_api = None
        if "amazon" in data:
            amazon_api = AmazonApiConfig.parse(data["amazon"])
        return cls(amazon_api=amazon_api)


@dataclass(frozen=True)
class DataConfig:
    """データ保存設定"""

    selenium: pathlib.Path
    dump: pathlib.Path
    price: pathlib.Path
    thumb: pathlib.Path
    metrics: pathlib.Path

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
    slack: SlackConfigTypes
    store: StoreConfig
    data: DataConfig
    target: TargetConfig
    liveness: LivenessConfig

    @classmethod
    def parse(cls, data: dict[str, Any]) -> AppConfig:
        """dict から AppConfig を生成"""
        # Check 設定
        check = CheckConfig.parse(data.get("check", {}))

        # Slack 設定
        slack: SlackConfigTypes = SlackEmptyConfig()
        if "slack" in data:
            slack = SlackConfig.parse(data["slack"])

        # Store 設定
        store = StoreConfig()
        if "store" in data:
            store = StoreConfig.parse(data["store"])

        # Data 設定
        data_config = DataConfig.parse(data.get("data", {}))

        # Target 設定
        target = TargetConfig.parse(data.get("target", {}))

        # Liveness 設定
        liveness = LivenessConfig.parse(data.get("liveness", {}))

        return cls(
            check=check,
            slack=slack,
            store=store,
            data=data_config,
            target=target,
            liveness=liveness,
        )


def load(config_file: str = CONFIG_FILE_PATH) -> AppConfig:
    """設定ファイルを読み込んで AppConfig を返す"""
    raw = my_lib.config.load(config_file)
    return AppConfig.parse(raw)
