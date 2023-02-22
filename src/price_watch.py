#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
import logging.handlers

import time
import os
import sys
import pathlib
import traceback

from selenium_util import create_driver

import logger
import history
import notify_slack
import store_amazon
import store_scrape
from config import load_config
from item_list import load_item_list

SLEEP_UNIT = 60
SCRAPE_INTERVAL_SEC = 5

ERROR_NOTIFY_COUNT = 6


def sleep_until(end_time):
    sleep_remain = end_time - time.time()
    logging.info("sleep {sleep:,} sec...".format(sleep=int(sleep_remain)))

    while True:
        # NOTE: Livenss がタイムアウトしないよう，定期的に更新する
        pathlib.Path(config["liveness"]["file"]).touch()

        sleep_remain = end_time - time.time()
        if sleep_remain < 0:
            return
        elif sleep_remain < SLEEP_UNIT:
            time.sleep(sleep_remain)
        else:
            time.sleep(SLEEP_UNIT)


def process_data(config, item, last):
    if ((last is None) and (item["stock"] == 1)) or (
        (last is not None)
        and (
            ((item["stock"] == 1) and (item["price"] != last["price"]))
            or (item["stock"] != last["stock"])
        )
    ):
        # NOTE: 下記いずれかの場合，履歴を記録する．
        # - 履歴データが無く，在庫がある場合
        # - 在庫がある状態で価格が変化した
        # - 在庫状況が変化した
        # (在庫が無い状態で価格が変化した場合は記録しない)

        if (last is not None) and (item["stock"] == 0):
            # NOTE: 在庫がなくなった場合，価格は前回のものを採用する．
            # (在庫がなくなった瞬間に更新された価格は記録しない)
            item["price"] = last["price"]

        history.insert(item)

    if last is None:
        if item["stock"] == 1:
            logging.warning(
                "{name}: watch start {new_price:,}{price_unit}. ({stock})".format(
                    name=item["name"],
                    new_price=item["price"],
                    price_unit=item["price_unit"],
                    stock="in stock",
                )
            )
        else:
            logging.warning(
                "{name}: watch start ({stock})".format(
                    name=item["name"], stock="out of stock"
                )
            )
    else:
        item["old_price"] = last["price"]

        if item["stock"] == 1:
            if item["price"] < last["price"]:
                logging.warning(
                    "{name}: price updated {old_price:,}{price_unit} ➡ {new_price:,}{price_unit}.".format(
                        name=item["name"],
                        old_price=last["price"],
                        new_price=item["price"],
                        price_unit=item["price_unit"],
                    )
                )
                notify_slack.send(config, item)
            elif last["stock"] == 0:
                logging.warning(
                    "{name}: back in stock {new_price:,}{price_unit}.".format(
                        name=item["name"],
                        new_price=item["price"],
                        price_unit=item["price_unit"],
                    )
                )
                notify_slack.send(config, item)
            else:
                logging.info(
                    "{name}: {new_price:,}{price_unit} ({stock}).".format(
                        name=item["name"],
                        new_price=item["price"],
                        price_unit=item["price_unit"],
                        stock="out of stock" if item["stock"] == 0 else "in stock",
                    )
                )
        else:
            logging.info(
                "{name}: ({stock}).".format(name=item["name"], stock="out of stock")
            )

    return True


def do_work(config, driver, item_list, loop, error_count):
    for item in filter(lambda item: item["check_method"] == "scrape", item_list):
        try:
            store_scrape.check(config, driver, item, loop)
            process_data(config, item, history.last(item["url"]))

            pathlib.Path(config["liveness"]["file"]).touch()
            error_count[item["url"]] = 0
        except:
            error_count[item["url"]] += 1
            if error_count[item["url"]] >= ERROR_NOTIFY_COUNT:
                notify_slack.error(config, item, traceback.format_exc())
                error_count[item["url"]] = 0
            pass
        time.sleep(SCRAPE_INTERVAL_SEC)

    for item in store_amazon.check_item_list(
        config,
        list(filter(lambda item: item["check_method"] == "amazon-paapi", item_list)),
    ):
        process_data(config, item, history.last(item["url"]))
    pathlib.Path(config["liveness"]["file"]).touch()


os.chdir(os.path.dirname(os.path.abspath(sys.argv[0])))

logger.init("bot.price_watch", level=logging.INFO)
logging.info("Start.")

config = load_config()
driver = create_driver()
loop = 0

error_count = {}

while True:
    start_time = time.time()

    do_work(config, driver, load_item_list(error_count), loop, error_count)

    sleep_until(start_time + config["interval"])
    loop += 1
