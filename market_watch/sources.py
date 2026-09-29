"""Read-only public endpoints, independent of the trading engine's mutable state."""

from concurrent.futures import ThreadPoolExecutor
import time
from urllib.parse import urlencode

from .http import RemoteError
from .models import Observation, number

HL_URL = "https://api.hyperliquid.xyz/info"
OKX_HOSTS = {"global": "openapi.okx.com", "us": "us.okx.com", "eea": "eea.okx.com", "tr": "tr.okx.com"}


def parse_hyperliquid(payload, assets, fetched_at):
    if not isinstance(payload, list) or len(payload) != 2:
        raise ValueError("invalid Hyperliquid envelope")
    universe, contexts = payload[0]["universe"], payload[1]
    if len(universe) != len(contexts):
        raise ValueError("mismatched Hyperliquid arrays")
    rows, issues = [], {}
    for asset in assets:
        try:
            matches = [i for i, meta in enumerate(universe) if meta.get("name") == asset and not meta.get("isDelisted")]
            if len(matches) != 1:
                raise ValueError("missing or ambiguous instrument")
            ctx = contexts[matches[0]]
            mark = number(ctx["markPx"], positive=True)
            oi = number(ctx["openInterest"], positive=True)
            rows.append(Observation("hyperliquid", asset, asset, fetched_at, fetched_at,
                                    "receipt", mark, oi, oi * mark,
                                    number(ctx["funding"]), 1.0))
        except (KeyError, ValueError, TypeError, AttributeError, OverflowError):
            issues["hyperliquid:" + asset] = "invalid_or_missing_measurement"
    return rows, issues


def okx_row(payload, instrument):
    if not isinstance(payload, dict) or payload.get("code") != "0":
        raise ValueError("OKX rejected request")
    rows = [row for row in payload["data"] if row.get("instId") == instrument]
    if len(rows) != 1:
        raise ValueError("missing or ambiguous OKX instrument")
    return rows[0]


def parse_okx(asset, funding, interest, marks, fetched_at):
    inst = asset + "-USDT-SWAP"
    f, oi, mark = (okx_row(p, inst) for p in (funding, interest, marks))
    # Use settlement interval metadata, never a hardcoded 8-hour assumption.
    interval = (number(f["nextFundingTime"]) - number(f["fundingTime"])) / 3600000
    if interval not in (1, 2, 4, 8):
        raise ValueError("unverified funding interval")
    timestamps = [number(row["ts"], positive=True) / 1000 for row in (f, oi, mark)]
    if max(timestamps) > fetched_at + 10:
        raise ValueError("future source timestamp")
    if number(f["fundingTime"]) / 1000 < fetched_at - 180:
        raise ValueError("expired funding estimate")
    return Observation("okx", asset, inst, min(timestamps), fetched_at, "exchange",
                       number(mark["markPx"], positive=True), number(oi["oiCcy"], positive=True),
                       number(oi["oiUsd"], positive=True), number(f["fundingRate"]), interval)


def collect(config, client, clock=time.time):
    def hyperliquid():
        payload = client.call(HL_URL, {"type": "metaAndAssetCtxs"})
        return parse_hyperliquid(payload, config.assets, clock())

    def okx(asset):
        inst = asset + "-USDT-SWAP"
        def get(endpoint, params):
            return client.call("https://" + OKX_HOSTS[config.okx_region] + "/api/v5/public/" + endpoint + "?" + urlencode(params))
        funding = get("funding-rate", {"instId": inst})
        interest = get("open-interest", {"instType": "SWAP", "instId": inst})
        mark = get("mark-price", {"instType": "SWAP", "instId": inst})
        return [parse_okx(asset, funding, interest, mark, clock())], {}

    tasks = {}
    rows, issues = [], {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        if "hyperliquid" in config.venues:
            tasks[pool.submit(hyperliquid)] = ["hyperliquid:" + a for a in config.assets]
        if "okx" in config.venues:
            for asset in config.assets:
                tasks[pool.submit(okx, asset)] = ["okx:" + asset]
        for future, scopes in tasks.items():
            try:
                observations, errors = future.result()
                rows.extend(observations)
                issues.update(errors)
            except RemoteError as exc:
                issues.update({scope: exc.code for scope in scopes})
            except (KeyError, ValueError, TypeError, AttributeError, OverflowError):
                issues.update({scope: "invalid_source_response" for scope in scopes})
    return rows, issues
