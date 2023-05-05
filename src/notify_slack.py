#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import slack_sdk
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


def send(token, channel, message):
    client = slack_sdk.WebClient(token=token)

    try:
        client.chat_postMessage(
            channel=channel,
            text=message["text"],
            blocks=json.loads(message["json"]),
        )
    except slack_sdk.errors.SlackApiError as e:
        logging.warning(e.response["error"])


def info(token, channel, item, is_record=False):
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

    send(
        token,
        channel,
        {
            "text": item["name"],
            "json": message,
        },
    )


def error(token, channel, item, error_msg):
    message = ERROR_TMPL.format(
        message=json.dumps(
            "<{url}|URL>\n{error_msg}".format(url=item["url"], error_msg=error_msg)
        ),
        name=json.dumps(item["name"]),
    )

    send(
        token,
        channel,
        {
            "text": item["name"],
            "json": message,
        },
    )
