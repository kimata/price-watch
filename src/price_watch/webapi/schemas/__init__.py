#!/usr/bin/env python3
"""Pydantic schemas for Web API."""

from price_watch.webapi.schemas.items import (
    ErrorResponse,
    HistoryQueryParams,
    HistoryResponse,
    ItemsQueryParams,
    ItemsResponse,
    Period,
    PriceHistoryPoint,
    ResultItem,
    StoreDefinition,
    StoreEntry,
)

__all__ = [
    "ErrorResponse",
    "HistoryQueryParams",
    "HistoryResponse",
    "ItemsQueryParams",
    "ItemsResponse",
    "Period",
    "PriceHistoryPoint",
    "ResultItem",
    "StoreDefinition",
    "StoreEntry",
]
