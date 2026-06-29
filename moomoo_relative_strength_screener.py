#!/usr/bin/env python3
"""
Moomoo Relative Strength Screener

Simple version:
- Looks at SG, HK, and US stocks
- Checks 1 month, 3 month, and 6 month performance
- Compares each stock with its sector and market index
- Ranks strongest stocks at the top

You need:
  pip install futu-api pandas
  moomoo OpenD running locally
"""

from __future__ import annotations

import argparse
import datetime as dt
import math
import time
from pathlib import Path

import pandas as pd
from futu import (
    AuType,
    KL_FIELD,
    KLType,
    Market,
    OpenQuoteContext,
    RET_OK,
    SecurityType,
)

LOOKBACK_DAYS = {
    "1m": 21,
    "3m": 63,
    "6m": 126,
}

DEFAULT_INDEX = {
    "SG": "SG.STI",
    "HK": "HK.HSI",
    "US": "US.SPX",
}

MOOMOO_MARKET = {
    "SG": Market.SG,
    "HK": Market.HK,
    "US": Market.US,
}


def stop_if_bad(ret, data, action):
    if ret != RET_OK:
        raise RuntimeError(f"Moomoo could not do this: {action}\nReason: {data}")


def small_groups(items, size):
    for start in range(0, len(items), size):
        yield items[start:start + size]


def read_index_overrides(overrides):
    indexes = dict(DEFAULT_INDEX)
    for item in overrides:
        market, code = item.split("=", 1)
        indexes[market.strip().upper()] = code.strip()
    return indexes


def get_all_stocks(quote, markets, limit_per_market):
    all_stocks = []

    for market in markets:
        ret, data = quote.get_stock_basicinfo(MOOMOO_MARKET[market], SecurityType.STOCK)
        stop_if_bad(ret, data, f"get stocks for {market}")

        stocks = data.copy()
        stocks["market"] = market

        if "delisting" in stocks.columns:
            stocks = stocks[~stocks["delisting"].fillna(False)]
        if "suspension" in stocks.columns:
            stocks = stocks[~stocks["suspension"].fillna(False)]

        if limit_per_market:
            stocks = stocks.head(limit_per_market)

        all_stocks.append(stocks)

    return pd.concat(all_stocks, ignore_index=True)


def add_sector_codes(quote, stocks):
    sector_tables = []
    stock_codes = stocks["code"].astype(str).tolist()

    for group in small_groups(stock_codes, 100):
        ret, data = quote.get_owner_plate(group)
        stop_if_bad(ret, data, "find each stock's sector")
        sector_tables.append(data.copy())

    if not sector_tables:
        stocks["sector_code"] = pd.NA
        stocks["sector_name"] = pd.NA
        return stocks

    sectors = pd.concat(sector_tables, ignore_index=True)

    # Moomoo can return several plates. Prefer industry/sector over theme/concept plates.
    plate_type = sectors.get("plate_type", pd.Series("", index=sectors.index)).astype(str).str.upper()
    sectors["best_match"] = 9
    sectors.loc[plate_type.str.contains("INDUSTRY"), "best_match"] = 0
    sectors.loc[plate_type.str.contains("SECTOR"), "best_match"] = 1
    sectors.loc[plate_type.str.contains("CONCEPT"), "best_match"] = 5

    sectors = sectors.sort_values(["code", "best_match", "plate_code"])
    sectors = sectors.drop_duplicates("code", keep="first")
    sectors = sectors.rename(columns={"plate_code": "sector_code", "plate_name": "sector_name"})

    return stocks.merge(sectors[["code", "sector_code", "sector_name"]], on="code", how="left")


def get_returns(quote, code, as_of_date, cache, sleep_seconds):
    if not isinstance(code, str) or not code or code == "nan":
        return None

    if code in cache:
        return cache[code]

    start_date = as_of_date - dt.timedelta(days=230)

    ret, data, next_page = quote.request_history_kline(
        code,
        start=start_date.isoformat(),
        end=as_of_date.isoformat(),
        ktype=KLType.K_DAY,
        autype=AuType.QFQ,
        fields=[KL_FIELD.DATE_TIME, KL_FIELD.CLOSE],
        max_count=1000,
    )
    stop_if_bad(ret, data, f"get price history for {code}")

    pages = [data]
    while next_page:
        ret, data, next_page = quote.request_history_kline(
            code,
            start=start_date.isoformat(),
            end=as_of_date.isoformat(),
            ktype=KLType.K_DAY,
            autype=AuType.QFQ,
            fields=[KL_FIELD.DATE_TIME, KL_FIELD.CLOSE],
            max_count=1000,
            page_req_key=next_page,
        )
        stop_if_bad(ret, data, f"get more price history for {code}")
        pages.append(data)

    time.sleep(sleep_seconds)

    prices = pd.concat(pages, ignore_index=True)
    prices = prices.sort_values("time_key").dropna(subset=["close"])

    if prices.empty:
        return None

    latest_close = prices.iloc[-1]["close"]
    answer = {}

    for label, days in LOOKBACK_DAYS.items():
        if len(prices) <= days:
            answer[label] = math.nan
        else:
            old_close = prices.iloc[-days - 1]["close"]
            answer[label] = latest_close / old_close - 1

    cache[code] = answer
    return answer


def main():
    parser = argparse.ArgumentParser(description="Rank stocks by relative strength using moomoo OpenD.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=11111)
    parser.add_argument("--markets", nargs="+", default=["SG", "HK", "US"], choices=["SG", "HK", "US"])
    parser.add_argument("--index-code", action="append", default=[], help="Example: --index-code US=US.SPX")
    parser.add_argument("--limit-per-market", type=int, help="Use this for a small test run first")
    parser.add_argument("--top", type=int, default=50)
    parser.add_argument("--sleep", type=float, default=0.08)
    parser.add_argument("--output", default="relative_strength_screener.csv")
    parser.add_argument("--as-of", default=dt.date.today().isoformat())
    args = parser.parse_args()

    as_of_date = dt.date.fromisoformat(args.as_of)
    indexes = read_index_overrides(args.index_code)
    cache = {}
    rows = []

    print("Opening moomoo OpenD...")
