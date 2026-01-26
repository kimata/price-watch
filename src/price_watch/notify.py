#!/usr/bin/env python3
"""Slack 通知処理."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

import my_lib.notify.slack

import price_watch.event

if TYPE_CHECKING:
    import PIL.Image


@runtime_checkable
class HasItemInfo(Protocol):
    """アイテム情報を持つオブジェクトのプロトコル."""

    @property
    def name(self) -> str:
        """アイテム名."""
        ...

    @property
    def url(self) -> str | None:
        """URL."""
        ...


def _get_attr(item: HasItemInfo | dict[str, Any], key: str, default: Any = None) -> Any:
    """dict または dataclass から属性を取得."""
    if isinstance(item, dict):
        return item.get(key, default)  # type: ignore[no-matching-overload]
    return getattr(item, key, default)


MESSAGE_TMPL = """\
[
    {{
        "type": "header",
        "text": {{
            "type": "plain_text",
            "text": {name},
            "emoji": true
        }}
    }},
    {{
        "type": "section",
        "text": {{
            "type": "mrkdwn",
            "text": {message}
        }},
        "accessory": {{
            "type": "image",
            "image_url": {thumb_url},
            "alt_text": {name}
        }}
    }}
]
"""

ERROR_TMPL = """\
[
    {{
        "type": "header",
        "text": {{
            "type": "plain_text",
            "text": {name},
            "emoji": true
        }}
    }},
    {{
        "type": "section",
        "text": {{
            "type": "mrkdwn",
            "text": {message}
        }}
    }}
]
"""


def info(
    slack_config: my_lib.notify.slack.SlackConfigTypes,
    item: HasItemInfo | dict[str, Any],
    is_record: bool = False,
) -> str | None:
    """価格変更の情報を通知."""
    if isinstance(slack_config, my_lib.notify.slack.SlackEmptyConfig):
        return None

    message_text = ":tada: {old_price:,} ⇒ *{price:,}{price_unit}* {record}\n{stock}\n<{url}|詳細>".format(
        old_price=_get_attr(item, "old_price"),
        price=_get_attr(item, "price"),
        price_unit=_get_attr(item, "price_unit"),
        url=_get_attr(item, "url"),
        record=":fire:" if is_record else "",
        stock="out of stock" if _get_attr(item, "stock") == 0 else "in stock",
    )

    message_json = MESSAGE_TMPL.format(
        message=json.dumps(message_text),
        name=json.dumps(_get_attr(item, "name")),
        thumb_url=json.dumps(_get_attr(item, "thumb_url", "")),
    )

    formatted = my_lib.notify.slack.FormattedMessage(
        text=_get_attr(item, "name"),
        json=json.loads(message_json),
    )

    return my_lib.notify.slack.send(slack_config, slack_config.info.channel.name, formatted)  # type: ignore[union-attr, return-value]


def error(
    slack_config: my_lib.notify.slack.SlackConfigTypes,
    item: HasItemInfo | dict[str, Any],
    error_msg: str,
) -> str | None:
    """エラーを通知."""
    if isinstance(slack_config, my_lib.notify.slack.SlackEmptyConfig):
        return None

    message_text = "<{url}|URL>\n{error_msg}".format(url=_get_attr(item, "url"), error_msg=error_msg)

    message_json = ERROR_TMPL.format(
        message=json.dumps(message_text),
        name=json.dumps(_get_attr(item, "name")),
    )

    formatted = my_lib.notify.slack.FormattedMessage(
        text=_get_attr(item, "name"),
        json=json.loads(message_json),
    )

    try:
        return my_lib.notify.slack.send(slack_config, slack_config.error.channel.name, formatted)  # type: ignore[union-attr, return-value]
    except Exception:
        logging.exception("Failed to send error notification")
        return None


def error_with_page(
    slack_config: my_lib.notify.slack.SlackConfigTypes,
    item: HasItemInfo | dict[str, Any],
    exception: Exception,
    screenshot: PIL.Image.Image | None = None,
    page_source: str | None = None,
) -> str | None:
    """スクリーンショットとページソース付きでエラーを通知.

    my_lib.selenium_util.error_handler のコールバックとして使用します。
    スクリーンショットはメッセージに添付、ページソースは gzip 圧縮してスレッドに添付します。

    Args:
        slack_config: Slack 設定
        item: アイテム情報
        exception: 発生した例外
        screenshot: スクリーンショット画像（PIL.Image）
        page_source: ページの HTML ソース

    Returns:
        スレッドのタイムスタンプ、または通知失敗時は None
    """
    if isinstance(slack_config, my_lib.notify.slack.SlackEmptyConfig):
        return None

    title = f"[{_get_attr(item, 'store', 'unknown')}] {_get_attr(item, 'name', 'unknown')}"

    try:
        return my_lib.notify.slack.notify_error_with_page(
            slack_config,  # type: ignore[arg-type]
            title,
            exception,
            screenshot,
            page_source,
        )
    except Exception:
        logging.exception("Failed to send error notification with page")
        return None


# --- イベント通知テンプレート ---

EVENT_TMPL = """\
[
    {{
        "type": "header",
        "text": {{
            "type": "plain_text",
            "text": {title},
            "emoji": true
        }}
    }},
    {{
        "type": "section",
        "text": {{
            "type": "mrkdwn",
            "text": {message}
        }},
        "accessory": {{
            "type": "image",
            "image_url": {thumb_url},
            "alt_text": {name}
        }}
    }}
]
"""

EVENT_TMPL_NO_THUMB = """\
[
    {{
        "type": "header",
        "text": {{
            "type": "plain_text",
            "text": {title},
            "emoji": true
        }}
    }},
    {{
        "type": "section",
        "text": {{
            "type": "mrkdwn",
            "text": {message}
        }}
    }}
]
"""


def event(
    slack_config: my_lib.notify.slack.SlackConfigTypes,
    event_result: price_watch.event.EventResult,
    item: HasItemInfo | dict[str, Any],
) -> str | None:
    """イベントを通知.

    Args:
        slack_config: Slack 設定
        event_result: イベント判定結果
        item: アイテム情報

    Returns:
        スレッドのタイムスタンプ、または通知失敗時は None
    """
    if isinstance(slack_config, my_lib.notify.slack.SlackEmptyConfig):
        return None

    # イベントタイプに応じたアイコンを選択
    icon = _get_event_icon(event_result.event_type)
    title = f"{icon} {price_watch.event.format_event_title(event_result.event_type.value)}"

    # メッセージを構築
    message_text = _build_event_message(event_result, item)

    # テンプレートを選択
    thumb_url = _get_attr(item, "thumb_url", "")
    if thumb_url:
        message_json = EVENT_TMPL.format(
            title=json.dumps(title),
            message=json.dumps(message_text),
            thumb_url=json.dumps(thumb_url),
            name=json.dumps(_get_attr(item, "name")),
        )
    else:
        message_json = EVENT_TMPL_NO_THUMB.format(
            title=json.dumps(title),
            message=json.dumps(message_text),
        )

    formatted = my_lib.notify.slack.FormattedMessage(
        text=f"{title}: {_get_attr(item, 'name')}",
        json=json.loads(message_json),
    )

    # DATA_RETRIEVAL_FAILURE は error チャンネルに通知、それ以外は info チャンネルに通知
    try:
        if event_result.event_type == price_watch.event.EventType.DATA_RETRIEVAL_FAILURE:
            return my_lib.notify.slack.send(slack_config, slack_config.error.channel.name, formatted)  # type: ignore[union-attr, return-value]
        return my_lib.notify.slack.send(slack_config, slack_config.info.channel.name, formatted)  # type: ignore[union-attr, return-value]
    except Exception:
        logging.exception("Failed to send event notification")
        return None


def _get_event_icon(event_type: price_watch.event.EventType) -> str:
    """イベントタイプに応じたアイコンを取得."""
    match event_type:
        case price_watch.event.EventType.BACK_IN_STOCK:
            return ":package:"
        case price_watch.event.EventType.CRAWL_FAILURE:
            return ":warning:"
        case price_watch.event.EventType.DATA_RETRIEVAL_FAILURE:
            return ":x:"
        case price_watch.event.EventType.LOWEST_PRICE:
            return ":fire:"
        case price_watch.event.EventType.PRICE_DROP:
            return ":chart_with_downwards_trend:"


def _build_event_message(
    event_result: price_watch.event.EventResult,
    item: HasItemInfo | dict[str, Any],
) -> str:
    """イベント通知メッセージを構築."""
    parts: list[str] = []

    match event_result.event_type:
        case price_watch.event.EventType.BACK_IN_STOCK:
            parts.append("*在庫が復活しました*")
            if event_result.price is not None:
                parts.append(f"価格: *{event_result.price:,}円*")

        case price_watch.event.EventType.CRAWL_FAILURE:
            parts.append("*24時間以上クロールに失敗しています*")
            parts.append("サイトの構造が変わった可能性があります")

        case price_watch.event.EventType.DATA_RETRIEVAL_FAILURE:
            parts.append("*6時間以上情報を取得できていません*")
            parts.append("価格・在庫情報の取得に失敗しています")

        case price_watch.event.EventType.LOWEST_PRICE:
            if event_result.old_price is not None and event_result.price is not None:
                drop = event_result.old_price - event_result.price
                parts.append("*過去最安値を更新！*")
                parts.append(f"{event_result.old_price:,}円 → *{event_result.price:,}円* (-{drop:,}円)")
            else:
                parts.append("*過去最安値を更新しました*")

        case price_watch.event.EventType.PRICE_DROP:
            if (
                event_result.old_price is not None
                and event_result.price is not None
                and event_result.threshold_days is not None
            ):
                drop = event_result.old_price - event_result.price
                parts.append(f"*{event_result.threshold_days}日間の最安値から値下げ*")
                parts.append(f"{event_result.old_price:,}円 → *{event_result.price:,}円* (-{drop:,}円)")
            else:
                parts.append("*価格が下がりました*")

    parts.append(f"<{_get_attr(item, 'url')}|詳細を見る>")

    return "\n".join(parts)
