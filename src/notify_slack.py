#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

import json
import logging

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


def send(config, item, is_record=False):
    client = WebClient(token=config["slack"]["bot_token"])

    message = MESSAGE_TMPL.format(
        message=json.dumps(
            ":tada: {old_price:,} ⇒ *{price:,}{price_unit}* {record}\n{stock}\n<{url}|詳細>".format(
                old_price=item["old_price"],
                price=item["price"],
                price_unit=item["price_unit"],
                url=item["url"],
                record=":fire:" if is_record else "",
                stock="out of stock" if item["stock"] == 0 else "in stock",
            )
        ),
        name=json.dumps(item["name"]),
        thumb_url=json.dumps(item["thumb_url"]),
    )
    try:
        client.chat_postMessage(
            channel=config["slack"]["channel"],
            text=item["name"],
            blocks=json.loads(message),
        )
    except SlackApiError as e:
        logging.warning(e.response["error"])


def error(config, item, error_msg):
    client = WebClient(token=config["slack"]["bot_token"])

    message = ERROR_TMPL.format(
        message=json.dumps(
            "<{url}|URL>\n{error_msg}".format(url=item["url"], error_msg=error_msg)
        ),
        name=json.dumps(item["name"]),
    )
    try:
        client.chat_postMessage(
            channel=config["slack"]["error_channel"],
            text=item["name"],
            blocks=json.loads(message),
        )
    except SlackApiError as e:
        logging.warning(e.response["error"])
