#!/usr/bin/env python3
"""
ターゲット設定ファイルの構造を定義する dataclass

target.yaml に基づいて型付けされた設定クラスを提供します。
Protocol を使って型階層を構成しています。
"""

from __future__ import annotations

import pathlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol

import my_lib.config

TARGET_FILE_PATH = pathlib.Path("target.yaml")


# =============================================================================
# Enum 定義
# =============================================================================


class CheckMethod(str, Enum):
    """価格チェック方法"""

    SCRAPE = "scrape"
    AMAZON_PAAPI = "my_lib.store.amazon.api"
    MERCARI_SEARCH = "my_lib.store.mercari.search"


class ActionType(str, Enum):
    """アクションの種類"""

    CLICK = "click"
    INPUT = "input"
    SIXDIGIT = "sixdigit"
    RECAPTCHA = "recaptcha"


# =============================================================================
# Protocol 定義
# =============================================================================


class HasName(Protocol):
    """名前を持つオブジェクトの Protocol"""

    @property
    def name(self) -> str: ...


class HasUrl(Protocol):
    """URL を持つオブジェクトの Protocol"""

    @property
    def url(self) -> str: ...


class HasStore(Protocol):
    """ストア名を持つオブジェクトの Protocol"""

    @property
    def store(self) -> str: ...


class HasXPathConfig(Protocol):
    """XPath 設定を持つオブジェクトの Protocol"""

    @property
    def price_xpath(self) -> str | None: ...

    @property
    def thumb_img_xpath(self) -> str | None: ...

    @property
    def unavailable_xpath(self) -> str | None: ...


class HasCheckMethod(Protocol):
    """チェックメソッドを持つオブジェクトの Protocol"""

    @property
    def check_method(self) -> CheckMethod: ...


class WatchItem(HasName, HasUrl, HasStore, Protocol):
    """監視対象アイテムの Protocol"""

    @property
    def asin(self) -> str | None: ...

    @property
    def price_unit(self) -> str: ...

    @property
    def check_method(self) -> CheckMethod: ...


# =============================================================================
# dataclass 定義
# =============================================================================


@dataclass(frozen=True)
class ActionStep:
    """アクションステップ定義"""

    type: ActionType
    xpath: str | None = None
    value: str | None = None

    @classmethod
    def parse(cls, data: dict[str, Any]) -> ActionStep:
        """dict から ActionStep を生成"""
        return cls(
            type=ActionType(data["type"]),
            xpath=data.get("xpath"),
            value=data.get("value"),
        )


@dataclass(frozen=True)
class PreloadConfig:
    """プリロード設定"""

    url: str
    every: int = 1

    @classmethod
    def parse(cls, data: dict[str, Any]) -> PreloadConfig:
        """dict から PreloadConfig を生成"""
        return cls(
            url=data["url"],
            every=data.get("every", 1),
        )


@dataclass(frozen=True)
class StoreDefinition:
    """ストア定義"""

    name: str
    check_method: CheckMethod = CheckMethod.SCRAPE
    price_xpath: str | None = None
    thumb_img_xpath: str | None = None
    unavailable_xpath: str | None = None
    price_unit: str = "円"
    point_rate: float = 0.0  # ポイント還元率（%）
    color: str | None = None  # ストアの色（hex形式, 例: "#3b82f6"）
    actions: list[ActionStep] = field(default_factory=list)

    @classmethod
    def parse(cls, data: dict[str, Any]) -> StoreDefinition:
        """dict から StoreDefinition を生成"""
        actions = []
        if "action" in data:
            actions = [ActionStep.parse(a) for a in data["action"]]

        check_method = CheckMethod.SCRAPE
        if "check_method" in data:
            raw_method = data["check_method"]
            # 後方互換性: 旧名称をサポート
            if raw_method == "amazon-paapi":
                raw_method = CheckMethod.AMAZON_PAAPI.value
            check_method = CheckMethod(raw_method)

        # point_rate は assumption.point_rate またはトップレベルの point_rate から取得
        assumption = data.get("assumption", {})
        point_rate = float(assumption.get("point_rate", data.get("point_rate", 0.0)))

        return cls(
            name=data["name"],
            check_method=check_method,
            price_xpath=data.get("price_xpath"),
            thumb_img_xpath=data.get("thumb_img_xpath"),
            unavailable_xpath=data.get("unavailable_xpath"),
            price_unit=data.get("price_unit", "円"),
            point_rate=point_rate,
            color=data.get("color"),
            actions=actions,
        )


@dataclass(frozen=True)
class ItemDefinition:
    """アイテム定義"""

    name: str
    store: str
    url: str | None = None
    asin: str | None = None
    price_xpath: str | None = None
    thumb_img_xpath: str | None = None
    unavailable_xpath: str | None = None
    price_unit: str | None = None
    preload: PreloadConfig | None = None
    # メルカリ検索用
    search_keyword: str | None = None  # 検索キーワード（省略時は name で検索）
    exclude_keyword: str | None = None  # 除外キーワード
    price_range: list[int] | None = None  # [min] or [min, max]
    cond: str | None = None  # "NEW|LIKE_NEW" 形式

    @classmethod
    def parse(cls, data: dict[str, Any]) -> ItemDefinition:
        """dict から ItemDefinition を生成"""
        preload = None
        if "preload" in data:
            preload = PreloadConfig.parse(data["preload"])

        # price_range のパース（"price" フィールド）
        price_range = None
        if "price" in data:
            price_data = data["price"]
            if isinstance(price_data, list):
                price_range = [int(p) for p in price_data]
            elif isinstance(price_data, int):
                price_range = [price_data]

        return cls(
            name=data["name"],
            store=data["store"],
            url=data.get("url"),
            asin=data.get("asin"),
            price_xpath=data.get("price_xpath"),
            thumb_img_xpath=data.get("thumb_img_xpath"),
            unavailable_xpath=data.get("unavailable_xpath"),
            price_unit=data.get("price_unit"),
            preload=preload,
            search_keyword=data.get("search_keyword"),
            exclude_keyword=data.get("exclude_keyword"),
            price_range=price_range,
            cond=data.get("cond"),
        )


@dataclass(frozen=True)
class ResolvedItem:
    """ストア定義とマージ済みのアイテム（WatchItem Protocol を実装）"""

    name: str
    store: str
    url: str  # メルカリの場合は空文字列（動的に更新される）
    asin: str | None = None
    check_method: CheckMethod = CheckMethod.SCRAPE
    price_xpath: str | None = None
    thumb_img_xpath: str | None = None
    unavailable_xpath: str | None = None
    price_unit: str = "円"
    point_rate: float = 0.0  # ポイント還元率（%）
    color: str | None = None  # ストアの色（hex形式）
    actions: list[ActionStep] = field(default_factory=list)
    preload: PreloadConfig | None = None
    # メルカリ検索用
    search_keyword: str | None = None
    exclude_keyword: str | None = None
    price_range: list[int] | None = None
    cond: str | None = None

    @classmethod
    def from_item_and_store(cls, item: ItemDefinition, store: StoreDefinition | None) -> ResolvedItem:
        """ItemDefinition と StoreDefinition をマージして ResolvedItem を生成"""
        # ストア定義からデフォルト値を取得
        store_check_method = CheckMethod.SCRAPE
        store_price_xpath = None
        store_thumb_img_xpath = None
        store_unavailable_xpath = None
        store_price_unit = "円"
        store_point_rate = 0.0
        store_color: str | None = None
        store_actions: list[ActionStep] = []

        if store is not None:
            store_check_method = store.check_method
            store_price_xpath = store.price_xpath
            store_thumb_img_xpath = store.thumb_img_xpath
            store_unavailable_xpath = store.unavailable_xpath
            store_price_unit = store.price_unit
            store_point_rate = store.point_rate
            store_color = store.color
            store_actions = store.actions

        # URL の決定
        url = item.url
        if url is None and item.asin is not None:
            url = f"https://www.amazon.co.jp/dp/{item.asin}"

        # メルカリ検索の場合は URL がなくても OK（検索結果から動的に取得）
        if url is None and store_check_method == CheckMethod.MERCARI_SEARCH:
            url = ""  # 空文字列（後から検索結果で更新）
        elif url is None:
            raise ValueError(f"Item '{item.name}' has no url or asin")

        # アイテム定義で上書き
        return cls(
            name=item.name,
            store=item.store,
            url=url,
            asin=item.asin,
            check_method=store_check_method,
            price_xpath=item.price_xpath or store_price_xpath,
            thumb_img_xpath=item.thumb_img_xpath or store_thumb_img_xpath,
            unavailable_xpath=item.unavailable_xpath or store_unavailable_xpath,
            price_unit=item.price_unit or store_price_unit,
            point_rate=store_point_rate,
            color=store_color,
            actions=store_actions,
            preload=item.preload,
            search_keyword=item.search_keyword,
            exclude_keyword=item.exclude_keyword,
            price_range=item.price_range,
            cond=item.cond,
        )


@dataclass(frozen=True)
class TargetConfig:
    """ターゲット設定（target.yaml）"""

    stores: list[StoreDefinition]
    items: list[ItemDefinition]

    @classmethod
    def parse(cls, data: dict[str, Any]) -> TargetConfig:
        """dict から TargetConfig を生成"""
        stores = []
        if "store_list" in data:
            stores = [StoreDefinition.parse(s) for s in data["store_list"]]

        items = []
        if "item_list" in data:
            items = [ItemDefinition.parse(i) for i in data["item_list"]]

        return cls(stores=stores, items=items)

    def get_store(self, name: str) -> StoreDefinition | None:
        """名前でストア定義を取得"""
        for store in self.stores:
            if store.name == name:
                return store
        return None

    def resolve_items(self) -> list[ResolvedItem]:
        """全アイテムをストア定義とマージして解決"""
        resolved = []
        for item in self.items:
            store = self.get_store(item.store)
            resolved.append(ResolvedItem.from_item_and_store(item, store))
        return resolved


def load(target_file: pathlib.Path | None = None) -> TargetConfig:
    """ターゲット設定ファイルを読み込んで TargetConfig を返す.

    Args:
        target_file: ターゲット設定ファイルパス。省略時は TARGET_FILE_PATH を使用。
    """
    if target_file is None:
        target_file = TARGET_FILE_PATH
    raw = my_lib.config.load(str(target_file))
    return TargetConfig.parse(raw)
