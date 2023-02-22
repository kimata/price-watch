#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from config import load_config

CONFIG_TARGET_PATH = "../target.yml"


def load_item_list(error_count):
    item_list = []
    target_config = load_config(CONFIG_TARGET_PATH)

    store_map = {}
    for store in target_config["store_list"]:
        store_map[store["name"]] = store

    for item in target_config["item_list"]:
        merged_item = dict(store_map[item["store"]], **item)

        if "check_method" not in merged_item:
            merged_item["check_method"] = "scrape"

        if "price_unit" not in merged_item:
            merged_item["price_unit"] = "円"

        if merged_item["check_method"] == "amazon-paapi":
            # NOTE: url は ID 的に使用するので，必ず定義されているようにする
            merged_item["url"] = "https://www.amazon.co.jp/dp/{asin}".format(
                asin=merged_item["asin"]
            )

        if merged_item["url"] not in error_count:
            error_count[merged_item["url"]] = 0

        if ("preload" in item) and ("every" not in item["preload"]):
            merged_item["preload"]["every"] = 1

        item_list.append(merged_item)

    return item_list
