#!/usr/bin/env python3
"""
ターゲット設定ファイルの構造を定義する dataclass

target.yaml に基づいて型付けされた設定クラスを提供します。
Protocol を使って型階層を構成しています。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol

import my_lib.config

TARGET_FILE_PATH = "target.yaml"


# =============================================================================
# Enum 定義
# =============================================================================


class CheckMethod(str, Enum):
    """価格チェック方法"""

    SCRAPE = "scrape"
    AMAZON_PAAPI = "amazon-paapi"


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
    actions: list[ActionStep] = field(default_factory=list)

    @classmethod
    def parse(cls, data: dict[str, Any]) -> StoreDefinition:
        """dict から StoreDefinition を生成"""
        actions = []
        if "action" in data:
            actions = [ActionStep.parse(a) for a in data["action"]]

        check_method = CheckMethod.SCRAPE
        if "check_method" in data:
            check_method = CheckMethod(data["check_method"])

        return cls(
            name=data["name"],
            check_method=check_method,
            price_xpath=data.get("price_xpath"),
            thumb_img_xpath=data.get("thumb_img_xpath"),
            unavailable_xpath=data.get("unavailable_xpath"),
            price_unit=data.get("price_unit", "円"),
            point_rate=float(data.get("point_rate", 0.0)),
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

    @classmethod
    def parse(cls, data: dict[str, Any]) -> ItemDefinition:
        """dict から ItemDefinition を生成"""
        preload = None
        if "preload" in data:
            preload = PreloadConfig.parse(data["preload"])

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
        )


@dataclass(frozen=True)
class ResolvedItem:
    """ストア定義とマージ済みのアイテム（WatchItem Protocol を実装）"""

    name: str
    store: str
    url: str
    asin: str | None = None
    check_method: CheckMethod = CheckMethod.SCRAPE
    price_xpath: str | None = None
    thumb_img_xpath: str | None = None
    unavailable_xpath: str | None = None
    price_unit: str = "円"
    point_rate: float = 0.0  # ポイント還元率（%）
    actions: list[ActionStep] = field(default_factory=list)
    preload: PreloadConfig | None = None

    @classmethod
    def from_item_and_store(cls, item: ItemDefinition, store: StoreDefinition | None) -> ResolvedItem:
        """ItemDefinition と StoreDefinition をマージして ResolvedItem を生成"""
        # URL の決定（asin がある場合は Amazon URL を生成）
        url = item.url
        if url is None and item.asin is not None:
            url = f"https://www.amazon.co.jp/dp/{item.asin}"
        if url is None:
            raise ValueError(f"Item '{item.name}' has no url or asin")

        # ストア定義からデフォルト値を取得
        store_check_method = CheckMethod.SCRAPE
        store_price_xpath = None
        store_thumb_img_xpath = None
        store_unavailable_xpath = None
        store_price_unit = "円"
        store_point_rate = 0.0
        store_actions: list[ActionStep] = []

        if store is not None:
            store_check_method = store.check_method
            store_price_xpath = store.price_xpath
            store_thumb_img_xpath = store.thumb_img_xpath
            store_unavailable_xpath = store.unavailable_xpath
            store_price_unit = store.price_unit
            store_point_rate = store.point_rate
            store_actions = store.actions

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
            actions=store_actions,
            preload=item.preload,
        )

    def to_dict(self) -> dict[str, Any]:
        """後方互換性のため dict に変換"""
        result: dict[str, Any] = {
            "name": self.name,
            "store": self.store,
            "url": self.url,
            "check_method": self.check_method.value,
            "price_unit": self.price_unit,
            "point_rate": self.point_rate,
        }
        if self.asin is not None:
            result["asin"] = self.asin
        if self.price_xpath is not None:
            result["price_xpath"] = self.price_xpath
        if self.thumb_img_xpath is not None:
            result["thumb_img_xpath"] = self.thumb_img_xpath
        if self.unavailable_xpath is not None:
            result["unavailable_xpath"] = self.unavailable_xpath
        if self.actions:
            result["action"] = [
                {"type": a.type.value, "xpath": a.xpath, "value": a.value} for a in self.actions
            ]
        if self.preload is not None:
            result["preload"] = {"url": self.preload.url, "every": self.preload.every}
        return result


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


def load(target_file: str = TARGET_FILE_PATH) -> TargetConfig:
    """ターゲット設定ファイルを読み込んで TargetConfig を返す"""
    raw = my_lib.config.load(target_file)
    return TargetConfig.parse(raw)
