#!/usr/bin/env python3
"""Slack 通知処理."""

from __future__ import annotations

import json
import logging
from typing import Any

import my_lib.notify.slack

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
    item: dict[str, Any],
    is_record: bool = False,
) -> str | None:
    """価格変更の情報を通知."""
    if isinstance(slack_config, my_lib.notify.slack.SlackEmptyConfig):
        return None

    message_text = ":tada: {old_price:,} ⇒ *{price:,}{price_unit}* {record}\n{stock}\n<{url}|詳細>".format(
        old_price=item["old_price"],
        price=item["price"],
        price_unit=item["price_unit"],
        url=item["url"],
        record=":fire:" if is_record else "",
        stock="out of stock" if item["stock"] == 0 else "in stock",
    )

    message_json = MESSAGE_TMPL.format(
        message=json.dumps(message_text),
        name=json.dumps(item["name"]),
        thumb_url=json.dumps(item.get("thumb_url", "")),
    )

    formatted = my_lib.notify.slack.FormattedMessage(
        text=item["name"],
        json=json.loads(message_json),
    )

    return my_lib.notify.slack.send(slack_config, slack_config.info.channel.name, formatted)  # type: ignore[union-attr]


def error(
    slack_config: my_lib.notify.slack.SlackConfigTypes,
    item: dict[str, Any],
    error_msg: str,
) -> str | None:
    """エラーを通知."""
    if isinstance(slack_config, my_lib.notify.slack.SlackEmptyConfig):
        return None

    message_text = "<{url}|URL>\n{error_msg}".format(url=item["url"], error_msg=error_msg)

    message_json = ERROR_TMPL.format(
        message=json.dumps(message_text),
        name=json.dumps(item["name"]),
    )

    formatted = my_lib.notify.slack.FormattedMessage(
        text=item["name"],
        json=json.loads(message_json),
    )

    try:
        return my_lib.notify.slack.send(slack_config, slack_config.error.channel.name, formatted)  # type: ignore[union-attr]
    except Exception:
        logging.exception("Failed to send error notification")
        return None
