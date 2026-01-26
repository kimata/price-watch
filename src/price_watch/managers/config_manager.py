#!/usr/bin/env python3
"""設定管理.

設定ファイルの読み込みとホットリロードを管理します。
"""

from __future__ import annotations

import logging
import pathlib
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import price_watch.config
import price_watch.exceptions
import price_watch.target

if TYPE_CHECKING:
    from price_watch.config import AppConfig
    from price_watch.target import ResolvedItem, TargetConfig


@dataclass
class ConfigManager:
    """設定管理クラス.

    設定ファイルの読み込み、キャッシュ、ホットリロードを管理します。
    """

    config_file: pathlib.Path
    target_file: pathlib.Path
    _config: AppConfig | None = field(default=None, init=False, repr=False)
    _target: TargetConfig | None = field(default=None, init=False, repr=False)

    @property
    def config(self) -> AppConfig:
        """アプリケーション設定を取得.

        初回アクセス時にファイルから読み込みます。

        Returns:
            アプリケーション設定

        Raises:
            ConfigError: 設定ファイルの読み込みに失敗した場合
        """
        if self._config is None:
            self._config = self._load_config()
        return self._config

    @property
    def target(self) -> TargetConfig:
        """ターゲット設定を取得.

        初回アクセス時にファイルから読み込みます。

        Returns:
            ターゲット設定

        Raises:
            ConfigError: 設定ファイルの読み込みに失敗した場合
        """
        if self._target is None:
            self._target = self._load_target()
        return self._target

    def _load_config(self) -> AppConfig:
        """設定ファイルを読み込む.

        Returns:
            アプリケーション設定

        Raises:
            ConfigError: 読み込みに失敗した場合
        """
        try:
            logging.info("Loading config from %s", self.config_file)
            return price_watch.config.load(self.config_file)
        except Exception as e:
            raise price_watch.exceptions.ConfigError(f"Failed to load config file: {self.config_file}") from e

    def _load_target(self) -> TargetConfig:
        """ターゲット設定ファイルを読み込む.

        Returns:
            ターゲット設定

        Raises:
            ConfigError: 読み込みに失敗した場合
        """
        try:
            logging.info("Loading target config from %s", self.target_file)
            return price_watch.target.load(self.target_file)
        except Exception as e:
            raise price_watch.exceptions.ConfigError(f"Failed to load target file: {self.target_file}") from e

    def reload_config(self) -> None:
        """設定ファイルを再読み込み.

        Raises:
            ConfigError: 読み込みに失敗した場合
        """
        logging.info("Reloading config...")
        self._config = self._load_config()

    def reload_target(self) -> None:
        """ターゲット設定を再読み込み.

        監視対象のホットリロードを実現します。

        Raises:
            ConfigError: 読み込みに失敗した場合
        """
        logging.info("Reloading target config...")
        self._target = self._load_target()

    def get_resolved_items(self) -> list[ResolvedItem]:
        """解決済みアイテムリストを取得.

        ターゲット設定を毎回再読み込みしてから解決します。
        これにより、実行中でも target.yaml の変更が反映されます。

        Returns:
            解決済みアイテムのリスト
        """
        self.reload_target()
        return self.target.resolve_items()
