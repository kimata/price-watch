#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
import time
import traceback

from paapi5_python_sdk.api.default_api import DefaultApi
from paapi5_python_sdk.get_items_resource import GetItemsResource
from paapi5_python_sdk.get_items_request import GetItemsRequest
from paapi5_python_sdk.condition import Condition
from paapi5_python_sdk.partner_type import PartnerType

PAAPI_SPLIT = 10


def fetch_price_by_api(config, asin_list):
    if len(asin_list) == 0:
        return {}

    logging.info(
        "PA-API GetItems: ASIN = [ {asin_list} ]".format(asin_list=", ".join(asin_list))
    )

    default_api = DefaultApi(
        access_key=config["amazon"]["access_key"],
        secret_key=config["amazon"]["secret_key"],
        host=config["amazon"]["host"],
        region=config["amazon"]["region"],
    )

    price_map = {}
    for i, asin_sub_list in enumerate(
        [asin_list[i : i + PAAPI_SPLIT] for i in range(0, len(asin_list), PAAPI_SPLIT)]
    ):
        if i != 0:
            time.sleep(10)

        resp = default_api.get_items(
            GetItemsRequest(
                partner_tag=config["amazon"]["associate"],
                partner_type=PartnerType.ASSOCIATES,
                marketplace="www.amazon.co.jp",
                condition=Condition.NEW,
                item_ids=asin_sub_list,
                resources=[
                    GetItemsResource.OFFERS_SUMMARIES_LOWESTPRICE,
                    GetItemsResource.ITEMINFO_CLASSIFICATIONS,
                    GetItemsResource.IMAGES_PRIMARY_MEDIUM,
                    GetItemsResource.IMAGES_PRIMARY_SMALL,
                ],
            )
        )

        if resp.items_result is not None:
            for item_data in resp.items_result.items:
                if item_data.offers is None:
                    continue

                item = {}
                for offer in item_data.offers.summaries:
                    if offer.condition.value != "New":
                        continue
                    item["price"] = int(offer.lowest_price.amount)
                    break

                if "price" not in item:
                    continue

                try:
                    item[
                        "category"
                    ] = item_data.item_info.classifications.product_group.display_value
                except:
                    logging.warning(
                        "Unable to get category of {asin}.".format(asin=item_data.asin)
                    )
                    pass

                item["thumb_url"] = item_data.images.primary.medium.url

                price_map[item_data.asin] = item

    return price_map


def check_item_list(config, item_list):
    try:
        price_map = fetch_price_by_api(
            config, list(map(lambda item: item["asin"], item_list))
        )
        for item in item_list:
            if item["asin"] in price_map:
                item["stock"] = 1
                item["price"] = price_map[item["asin"]]["price"]
                item["thumb_url"] = price_map[item["asin"]]["thumb_url"]
            else:
                item["stock"] = 0
        return item_list
    except:
        logging.error(traceback.format_exc())
        return []


if __name__ == "__main__":
    import pprint
    from config import load_config

    config = load_config()

    pprint.pprint(
        fetch_price_by_api(
            config,
            ["B0BGPCH9C3", "B0BFZWW3H6"],
        )
    )
