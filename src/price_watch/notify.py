#!/usr/bin/env python3
"""Slack 通知処理."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING
from urllib.parse import urljoin

import my_lib.notify.slack

import price_watch.event

if TYPE_CHECKING:
    import PIL.Image

    from price_watch.models import CheckedItem, TargetDiff


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


def _resolve_thumb_url(thumb_url: str | None, external_url: str | None) -> str:
    """サムネイルの相対URLを絶対URLに変換.

    Args:
        thumb_url: サムネイルの相対URL（例: /price/thumb/abc.png）
        external_url: アプリケーションの外部URL（例: https://example.com/price/）

    Returns:
        絶対URL。変換できない場合は空文字列。
    """
    if not thumb_url:
        return ""
    if not external_url:
        return thumb_url
    # urljoin を使用して正しく URL を結合
    # thumb_url が絶対パス（/price/...）の場合、ホストからのパスとして解釈される
    return urljoin(external_url, thumb_url)


def info(
    slack_config: my_lib.notify.slack.SlackConfigTypes,
    item: CheckedItem,
    is_record: bool = False,
) -> str | None:
    """価格変更の情報を通知."""
    if isinstance(slack_config, my_lib.notify.slack.SlackEmptyConfig):
        return None

    message_text = ":tada: {old_price:,} ⇒ *{price:,}{price_unit}* {record}\n{stock}\n<{url}|詳細>".format(
        old_price=item.old_price or 0,
        price=item.price or 0,
        price_unit=item.price_unit,
        url=item.url or "",
        record=":fire:" if is_record else "",
        stock="out of stock" if item.stock_as_int() == 0 else "in stock",
    )

    message_json = MESSAGE_TMPL.format(
        message=json.dumps(message_text),
        name=json.dumps(item.name),
        thumb_url=json.dumps(item.thumb_url or ""),
    )

    formatted = my_lib.notify.slack.FormattedMessage(
        text=item.name,
        json=json.loads(message_json),
    )

    return my_lib.notify.slack.send(slack_config, slack_config.info.channel.name, formatted)  # type: ignore[union-attr, return-value]


def error(
    slack_config: my_lib.notify.slack.SlackConfigTypes,
    item: CheckedItem,
    error_msg: str,
) -> str | None:
    """エラーを通知."""
    if isinstance(slack_config, my_lib.notify.slack.SlackEmptyConfig):
        return None

    message_text = "<{url}|URL>\n{error_msg}".format(url=item.url or "", error_msg=error_msg)

    message_json = ERROR_TMPL.format(
        message=json.dumps(message_text),
        name=json.dumps(item.name),
    )

    formatted = my_lib.notify.slack.FormattedMessage(
        text=item.name,
        json=json.loads(message_json),
    )

    try:
        return my_lib.notify.slack.send(slack_config, slack_config.error.channel.name, formatted)  # type: ignore[union-attr, return-value]
    except Exception:
        logging.exception("Failed to send error notification")
        return None


def error_with_page(
    slack_config: my_lib.notify.slack.SlackConfigTypes,
    item: CheckedItem,
    exception: Exception,
    screenshot: PIL.Image.Image | None = None,
    page_source: str | None = None,
) -> str | None:
    """スクリーンショットとページソース付きでエラーを通知.

    my_lib.selenium_util.error_handler のコールバックとして使用します。
    スクリーンショットはメッセージに添付、ページソースは gzip 圧縮してスレッドに添付します。

    Args:
        slack_config: Slack 設定
        item: チェック済みアイテム
        exception: 発生した例外
        screenshot: スクリーンショット画像（PIL.Image）
        page_source: ページの HTML ソース

    Returns:
        スレッドのタイムスタンプ、または通知失敗時は None
    """
    if isinstance(slack_config, my_lib.notify.slack.SlackEmptyConfig):
        return None

    title = f"[{item.store}] {item.name}"

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
    item: CheckedItem,
    external_url: str | None = None,
) -> str | None:
    """イベントを通知.

    Args:
        slack_config: Slack 設定
        event_result: イベント判定結果
        item: チェック済みアイテム
        external_url: アプリケーションの外部URL

    Returns:
        スレッドのタイムスタンプ、または通知失敗時は None
    """
    if isinstance(slack_config, my_lib.notify.slack.SlackEmptyConfig):
        return None

    # イベントタイプに応じたアイコンを選択
    icon = _get_event_icon(event_result.event_type)
    title = f"{icon}{price_watch.event.format_event_title(event_result.event_type.value)}: {item.name}"

    # メッセージを構築
    message_text = _build_event_message(event_result, item)

    # テンプレートを選択
    thumb_url = _resolve_thumb_url(item.thumb_url, external_url)
    if thumb_url:
        message_json = EVENT_TMPL.format(
            title=json.dumps(title),
            message=json.dumps(message_text),
            thumb_url=json.dumps(thumb_url),
            name=json.dumps(item.name),
        )
    else:
        message_json = EVENT_TMPL_NO_THUMB.format(
            title=json.dumps(title),
            message=json.dumps(message_text),
        )

    formatted = my_lib.notify.slack.FormattedMessage(
        text=title,
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
    item: CheckedItem,
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

    parts.append(f"<{item.url or ''}|詳細を見る>")

    return "\n".join(parts)


# --- 認証失敗通知 ---

AUTH_FAILURE_TMPL = """\
[
    {{
        "type": "header",
        "text": {{
            "type": "plain_text",
            "text": ":warning: 認証失敗アラート",
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


def auth_failure(
    slack_config: my_lib.notify.slack.SlackConfigTypes,
    client_ip: str,
    failure_count: int,
) -> str | None:
    """認証失敗を通知.

    1時間に5回失敗するごとに error チャンネルに通知します。

    Args:
        slack_config: Slack 設定
        client_ip: クライアントIPアドレス
        failure_count: 1時間以内の失敗回数

    Returns:
        スレッドのタイムスタンプ、または通知失敗時は None
    """
    if isinstance(slack_config, my_lib.notify.slack.SlackEmptyConfig):
        return None

    message_text = (
        f"*1時間に{failure_count}回の認証失敗を検出しました*\n"
        f"IP: `{client_ip}`\n"
        "ブルートフォース攻撃の可能性があります。"
    )

    message_json = AUTH_FAILURE_TMPL.format(
        message=json.dumps(message_text),
    )

    formatted = my_lib.notify.slack.FormattedMessage(
        text=f"認証失敗: {client_ip} ({failure_count}回)",
        json=json.loads(message_json),
    )

    try:
        return my_lib.notify.slack.send(slack_config, slack_config.error.channel.name, formatted)  # type: ignore[union-attr, return-value]
    except Exception:
        logging.exception("Failed to send auth failure notification")
        return None


# --- target.yaml 変更通知 ---

TARGET_CHANGED_TMPL = """\
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


def target_changed(
    slack_config: my_lib.notify.slack.SlackConfigTypes,
    diff: TargetDiff,
) -> str | None:
    """target.yaml の変更を通知.

    Args:
        slack_config: Slack 設定（SlackEmptyConfig の場合は何もしない）
        diff: 差分情報

    Returns:
        スレッドのタイムスタンプ、または通知失敗時は None
    """
    if not diff.has_changes():
        return None

    # メッセージを構築
    message_parts: list[str] = []

    if diff.added:
        message_parts.append(f"*➕ 追加 ({len(diff.added)}件)*")
        message_parts.extend(f"  • {item.name} ({item.store})" for item in diff.added)
        message_parts.append("")

    if diff.removed:
        message_parts.append(f"*➖ 削除 ({len(diff.removed)}件)*")
        message_parts.extend(f"  • {item.name} ({item.store})" for item in diff.removed)
        message_parts.append("")

    if diff.changed:
        message_parts.append(f"*✏️ 変更 ({len(diff.changed)}件)*")
        for item, changes in diff.changed:
            message_parts.append(f"  • {item.name} ({item.store})")
            message_parts.extend(
                f'    - {change.field}: "{change.old_value}" → "{change.new_value}"' for change in changes
            )
        message_parts.append("")

    message_text = "\n".join(message_parts).strip()

    title = "📝 target.yaml が更新されました"
    message_json = TARGET_CHANGED_TMPL.format(
        title=json.dumps(title),
        message=json.dumps(message_text),
    )

    formatted = my_lib.notify.slack.FormattedMessage(
        text=title,
        json=json.loads(message_json),
    )

    try:
        # NullObject パターン: SlackEmptyConfig の場合は send() 内で早期リターン
        return my_lib.notify.slack.send(slack_config, slack_config.info.channel.name, formatted)  # type: ignore[union-attr, return-value]
    except Exception:
        logging.exception("Failed to send target change notification")
        return None
