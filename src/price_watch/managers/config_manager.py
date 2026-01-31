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
import price_watch.models
import price_watch.target

if TYPE_CHECKING:
    from price_watch.config import AppConfig
    from price_watch.models import ItemChange, TargetDiff
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
    _previous_items: list[ResolvedItem] | None = field(default=None, init=False, repr=False)

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

    def get_resolved_items(self) -> tuple[list[ResolvedItem], TargetDiff | None]:
        """解決済みアイテムリストを取得.

        ターゲット設定を毎回再読み込みしてから解決します。
        これにより、実行中でも target.yaml の変更が反映されます。

        Returns:
            解決済みアイテムのリストと差分（初回は None）
        """
        self.reload_target()
        new_items = self.target.resolve_items()

        # 差分検出（前回状態がある場合のみ）
        diff: TargetDiff | None = None
        if self._previous_items is not None:
            diff = self._compute_diff(self._previous_items, new_items)

        self._previous_items = new_items
        return new_items, diff

    def _compute_diff(self, old_items: list[ResolvedItem], new_items: list[ResolvedItem]) -> TargetDiff:
        """新旧アイテムリストの差分を計算.

        Args:
            old_items: 前回のアイテムリスト
            new_items: 今回のアイテムリスト

        Returns:
            差分情報
        """
        # (name, store) をキーとしてインデックス化
        old_dict: dict[tuple[str, str], ResolvedItem] = {(item.name, item.store): item for item in old_items}
        new_dict: dict[tuple[str, str], ResolvedItem] = {(item.name, item.store): item for item in new_items}

        old_keys = set(old_dict.keys())
        new_keys = set(new_dict.keys())

        # 追加・削除されたアイテム
        added = [new_dict[key] for key in (new_keys - old_keys)]
        removed = [old_dict[key] for key in (old_keys - new_keys)]

        # 変更されたアイテム
        changed: list[tuple[ResolvedItem, list[ItemChange]]] = []
        for key in old_keys & new_keys:
            old_item = old_dict[key]
            new_item = new_dict[key]
            changes = self._compare_items(old_item, new_item)
            if changes:
                changed.append((new_item, changes))

        return price_watch.models.TargetDiff(
            added=added,
            removed=removed,
            changed=changed,
        )

    def _compare_items(self, old_item: ResolvedItem, new_item: ResolvedItem) -> list[ItemChange]:
        """2つのアイテムを比較して変更内容を取得.

        Args:
            old_item: 変更前のアイテム
            new_item: 変更後のアイテム

        Returns:
            変更内容のリスト
        """
        changes: list[ItemChange] = []

        # 比較対象フィールド
        fields_to_compare = [
            ("url", "URL"),
            ("asin", "ASIN"),
            ("search_keyword", "検索キーワード"),
            ("exclude_keyword", "除外キーワード"),
            ("price_range", "価格範囲"),
            ("cond", "商品状態"),
            ("jan_code", "JANコード"),
            ("category", "カテゴリー"),
        ]

        for field_name, display_name in fields_to_compare:
            old_value = getattr(old_item, field_name)
            new_value = getattr(new_item, field_name)

            if old_value != new_value:
                changes.append(
                    price_watch.models.ItemChange(
                        field=display_name,
                        old_value=self._format_value(old_value),
                        new_value=self._format_value(new_value),
                    )
                )

        return changes

    def _format_value(self, value: object) -> str:
        """値を表示用に整形.

        Args:
            value: 整形する値

        Returns:
            表示用文字列
        """
        if value is None:
            return "(なし)"
        if isinstance(value, list):
            return str(value)
        return str(value)
