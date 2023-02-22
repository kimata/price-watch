#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import pathlib
import sqlite3

DATA_PATH = pathlib.Path(os.path.dirname(__file__)).parent / "data"
DB_FILE = "price_history.db"


def dict_factory(cursor, row):
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d


def connect():
    return sqlite3.connect(str(DATA_PATH / DB_FILE))


def insert(item):
    conn = connect()
    cur = conn.cursor()

    cur.execute(
        """
INSERT INTO price_history
(name, url, price, stock, store) values("{name}", "{url}", {price}, {stock}, "{store}")
""".format(
            name=item["name"],
            url=item["url"],
            price=item["price"],
            stock=item["stock"],
            store=item["store"],
        )
    )
    conn.commit()
    conn.close()


def last(url):
    conn = connect()
    conn.row_factory = dict_factory
    cur = conn.cursor()

    cur.execute(
        """
select * from price_history WHERE url="{url} ORDER BY time DESC
""".format(
            url=url
        )
    )

    price_hist = cur.fetchone()

    conn.commit()
    conn.close()

    return price_hist


def collect(url, func):
    conn = connect()
    conn.row_factory = dict_factory
    cur = conn.cursor()

    for price_hist in cur.execute(
        """
select * from price_history WHERE url="{url}" ORDER BY time DESC
""".format(
            url=url
        )
    ):
        func(price_hist)
    conn.commit()
    conn.close()


def init():
    conn = connect()
    cur = conn.cursor()
    cur.execute(
        """
CREATE TABLE IF NOT EXISTS price_history(
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    name    TEXT NOT NULL,
    url     TEXT NOT NULL,
    price   INTEGER NOT NULL,
    stock   INTEGER NOT NULL,
    store   TEXT NOT NULL,
    time    TIMESTAMP DEFAULT(DATETIME('now','localtime'))
)
"""
    )
    conn.commit()
    conn.close()


if __name__ == "__main__":
    init()
