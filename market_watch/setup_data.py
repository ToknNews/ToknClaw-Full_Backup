"""Bounded public market data for five-minute setups; every source keeps its units."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from datetime import datetime
import time
from urllib.parse import urlencode

from .http import RemoteError
from .models import number
from .sources import HL_URL, OKX_HOSTS

INTERVAL = 300


@dataclass(frozen=True)
class Candle:
    venue: str
    asset: str
    open_at: float
    open: float
    high: float
    low: float
    close: float
    volume_base: float
    received_at: float

    def __post_init__(self):
        if self.venue not in {'hyperliquid', 'okx'} or self.asset not in {'BTC', 'ETH', 'SOL'}:
            raise ValueError('unsupported candle instrument')
        for key in ('open_at', 'open', 'high', 'low', 'close', 'received_at'):
            number(getattr(self, key), positive=True)
        if number(self.volume_base) < 0 or self.open_at % INTERVAL:
            raise ValueError('invalid candle volume or alignment')
        if self.low > min(self.open, self.close) or self.high < max(self.open, self.close):
            raise ValueError('invalid OHLC geometry')
        if self.close_at > self.received_at:
            raise ValueError('unfinished candle')

    @property
    def close_at(self):
        return self.open_at + INTERVAL

    def to_dict(self):
        return asdict(self)


@dataclass
class SetupBatch:
    requested_close: float
    candles: list = field(default_factory=list)
    books: dict = field(default_factory=dict)
    spots: dict = field(default_factory=dict)
    errors: dict = field(default_factory=dict)


def expected_close(now, grace=15):
    return int((now - grace) // INTERVAL) * INTERVAL


def _ordered(rows):
    rows.sort(key=lambda row: row.open_at)
    if len({row.open_at for row in rows}) != len(rows):
        raise ValueError('duplicate candle timestamp')
    return rows


def parse_hl_candles(payload, asset, received, grace=15):
    if not isinstance(payload, list) or len(payload) > 5000:
        raise ValueError('invalid candle envelope')
    rows = []
    for row in payload:
        if row['s'] != asset or row['i'] != '5m':
            raise ValueError('wrong candle instrument or timeframe')
        start = number(row['t'], positive=True) / 1000
        end_ms = number(row['T'], positive=True)
        if not (start + INTERVAL) * 1000 - 1 <= end_ms <= (start + INTERVAL) * 1000:
            raise ValueError('wrong candle close time')
        if start > received + 10:
            raise ValueError('future candle')
        if start + INTERVAL > received - grace:
            continue
        rows.append(Candle('hyperliquid', asset, start, *[
            number(row[k], positive=True) for k in ('o', 'h', 'l', 'c')],
            number(row['v']), received))
    return _ordered(rows)


def parse_okx_candles(payload, asset, received, grace=15):
    if not isinstance(payload, dict) or payload.get('code') != '0':
        raise ValueError('invalid OKX candle envelope')
    data = payload['data']
    if not isinstance(data, list) or len(data) > 300:
        raise ValueError('invalid OKX candle count')
    rows = []
    for row in data:
        if not isinstance(row, list) or len(row) != 9 or row[8] not in ('0', '1'):
            raise ValueError('invalid OKX candle row')
        start = number(row[0], positive=True) / 1000
        if start > received + 10:
            raise ValueError('future candle')
        if row[8] != '1' or start + INTERVAL > received - grace:
            continue
        # For swaps vol is contracts; volCcy (index 6) is base-asset volume.
        rows.append(Candle('okx', asset, start, *[
            number(row[i], positive=True) for i in (1, 2, 3, 4)], number(row[6]), received))
    return _ordered(rows)


def parse_book(payload, asset, received):
    if payload['coin'] != asset:
        raise ValueError('wrong book instrument')
    observed = number(payload['time'], positive=True) / 1000
    if not -5 <= received - observed <= 60:
        raise ValueError('stale or future book')
    sides = payload['levels']
    if not isinstance(sides, list) or len(sides) != 2:
        raise ValueError('invalid book sides')
    parsed = []
    for i, side in enumerate(sides):
        if not isinstance(side, list) or not 1 <= len(side) <= 20:
            raise ValueError('invalid book depth')
        levels = [(number(r['px'], positive=True), number(r['sz'], positive=True)) for r in side]
        prices = [p for p, _ in levels]
        if prices != sorted(set(prices), reverse=i == 0):
            raise ValueError('unordered or duplicate book levels')
        parsed.append(levels)
    bid, ask = parsed[0][0][0], parsed[1][0][0]
    if bid >= ask:
        raise ValueError('crossed or locked book')
    mid = bid / 2 + ask / 2
    depths = [sum(p * size for p, size in side if abs(p / mid - 1) <= 0.001)
              for side in parsed]
    for value in [mid, *depths, sum(depths), (ask - bid) / mid * 10000]:
        number(value)
    return {'venue': 'hyperliquid', 'asset': asset, 'observed_at': observed,
            'received_at': received, 'mid': mid, 'bid': bid, 'ask': ask,
            'spread_bps': (ask - bid) / mid * 10000,
            'bid_depth_usd': depths[0], 'ask_depth_usd': depths[1],
            'depth_band_bps': 10, 'returned_levels': [len(side) for side in parsed],
            'depth_is_partial': True,
            'imbalance': ((depths[0] - depths[1]) / sum(depths)) if sum(depths) else None}


def parse_spot(payload, asset, received):
    parsed_time = datetime.fromisoformat(payload['time'].replace('Z', '+00:00'))
    if parsed_time.tzinfo is None:
        raise ValueError('spot timestamp needs timezone')
    observed = parsed_time.timestamp()
    if not -5 <= received - observed <= 120:
        raise ValueError('stale or future spot trade')
    last, bid, ask = [number(payload[k], positive=True) for k in ('price', 'bid', 'ask')]
    volume = number(payload['volume'])
    if bid > ask or volume < 0:
        raise ValueError('invalid spot quote')
    return {'venue': 'coinbase', 'asset': asset, 'instrument': asset + '-USD',
            'quote': 'USD', 'last': last, 'bid': bid, 'ask': ask, 'volume_base_24h': volume,
            'trade_at': observed, 'received_at': received}


def collect_setup_data(config, client, store, clock=time.time):
    """Once per closed bar; retry failures no faster than once/minute, honor 429s."""
    if not config.setup_enabled:
        return None
    now = clock()
    end = expected_close(now, config.setup_close_grace_seconds)
    prior = store.get_meta('setup_poll') or {}
    if (prior.get('close') == end and prior.get('complete')) or now - prior.get('at', 0) < 60:
        return None
    with store.db:
        store.set_meta('setup_poll', {'close': end, 'at': now, 'complete': False})
    batch = SetupBatch(end)
    tasks = []
    for asset in config.assets:
        tasks.extend([('hl_candles', asset), ('hl_book', asset)])
        if 'okx' in config.venues:
            tasks.append(('okx_candles', asset))
        if config.setup_coinbase_enabled:
            tasks.append(('coinbase_spot', asset))

    def fetch(kind, asset):
        grace = config.setup_close_grace_seconds
        if kind == 'hl_candles':
            payload = client.call(HL_URL, {'type': 'candleSnapshot', 'req': {
                'coin': asset, 'interval': '5m',
                'startTime': int((end - config.setup_history_bars * INTERVAL) * 1000),
                'endTime': int(end * 1000 - 1)}})
            return parse_hl_candles(payload, asset, clock(), grace)
        if kind == 'hl_book':
            return parse_book(client.call(HL_URL, {'type': 'l2Book', 'coin': asset}), asset, clock())
        if kind == 'okx_candles':
            params = urlencode({'instId': asset + '-USDT-SWAP', 'bar': '5m',
                                'limit': config.setup_history_bars + 1})
            payload = client.call('https://' + OKX_HOSTS[config.okx_region] + '/api/v5/market/candles?' + params)
            return parse_okx_candles(payload, asset, clock(), grace)
        payload = client.call('https://api.exchange.coinbase.com/products/' + asset + '-USD/ticker')
        return parse_spot(payload, asset, clock())

    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {}
        for kind, asset in tasks:
            provider = kind.split('_')[0]
            if now < (store.get_meta('setup_backoff:' + provider) or 0):
                batch.errors[kind + ':' + asset] = 'source_backoff'
            else:
                futures[pool.submit(fetch, kind, asset)] = (kind, asset)
        for future, (kind, asset) in futures.items():
            try:
                value = future.result()
                if kind.endswith('candles'):
                    batch.candles.extend(value)
                elif kind == 'hl_book':
                    batch.books[asset] = value
                else:
                    batch.spots[asset] = value
            except RemoteError as exc:
                batch.errors[kind + ':' + asset] = exc.code
                if exc.code == 'http_429':
                    try:
                        delay = max(60, min(86400, number(exc.retry_after)))
                    except (ValueError, TypeError, OverflowError):
                        delay = 60
                    with store.db:
                        store.set_meta('setup_backoff:' + kind.split('_')[0], clock() + delay)
            except (ValueError, KeyError, TypeError, AttributeError, IndexError, OverflowError):
                batch.errors[kind + ':' + asset] = 'invalid_source_response'
    return batch
