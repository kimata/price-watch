#!/usr/bin/env python3
"""
Pydantic schemas for items API.

These schemas define the contract between frontend and backend,
ensuring type safety and validation for API requests and responses.

Frontend types are defined in: frontend/src/types/index.ts
"""

from typing import Literal

from my_lib.pydantic.base import BaseSchema

# Period type matching frontend's Period type
Period = Literal["30", "90", "180", "365", "all"]


class ItemsQueryParams(BaseSchema):
    """Query parameters for /api/items endpoint.

    Matches frontend's fetchItems(days: Period) call.
    """

    days: Period = "30"


class HistoryQueryParams(BaseSchema):
    """Query parameters for /api/items/<url_hash>/history endpoint.

    Matches frontend's fetchItemHistory(urlHash, days: Period) call.
    """

    days: Period = "30"


class PriceHistoryPoint(BaseSchema):
    """Price history entry.

    Matches frontend's PriceHistoryPoint interface.
    price と effective_price は在庫なし時に None になる場合がある。
    """

    time: str
    price: int | None
    effective_price: int | None
    stock: int


class StoreEntry(BaseSchema):
    """Store information for an item.

    Matches frontend's StoreEntry interface.
    current_price と effective_price は在庫なし時に None になる場合がある。
    """

    url_hash: str
    store: str
    url: str
    current_price: int | None
    effective_price: int | None
    point_rate: float
    lowest_price: int | None
    highest_price: int | None
    stock: int
    last_updated: str
    history: list[PriceHistoryPoint]


class ResultItem(BaseSchema):
    """Item result with multiple stores.

    Matches frontend's Item interface.
    best_effective_price は全ストア在庫なし時に None になる場合がある。
    """

    name: str
    thumb_url: str | None
    stores: list[StoreEntry]
    best_store: str
    best_effective_price: int | None


class StoreDefinition(BaseSchema):
    """Store definition with point rate and color.

    Matches frontend's StoreDefinition interface.
    """

    name: str
    point_rate: float
    color: str | None = None


class ItemsResponse(BaseSchema):
    """Response for /api/items endpoint.

    Matches frontend's ItemsResponse interface.
    """

    items: list[ResultItem]
    store_definitions: list[StoreDefinition]


class HistoryResponse(BaseSchema):
    """Response for /api/items/<url_hash>/history endpoint.

    Matches frontend's HistoryResponse interface.
    """

    history: list[PriceHistoryPoint]


class ErrorResponse(BaseSchema):
    """Error response."""

    error: str
