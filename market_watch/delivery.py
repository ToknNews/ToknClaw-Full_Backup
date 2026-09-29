"""Audience-separated Discord/Telegram delivery with bounded, durable retries."""

from dataclasses import dataclass
import hashlib
import json
import re
import time
from urllib.parse import urlparse, urlunparse

from .branding import ICON_URL, WEBHOOK_NAME
from .http import RemoteError
from .presentation import validate_presentation


@dataclass(frozen=True, repr=False)
class Route:
    platform: str
    audience: str
    endpoint: str
    chat_id: str = ''

    @property
    def name(self):
        fingerprint = hashlib.sha256((self.endpoint + ':' + self.chat_id).encode()).hexdigest()[:16]
        return self.platform + ':' + self.audience + ':' + fingerprint

    def __repr__(self):
        return 'Route(' + self.platform + ', ' + self.audience + ', <redacted>)'


def routes_from_env(env):
    routes = []
    token = env.get('MARKET_WATCH_TELEGRAM_BOT_TOKEN', '')
    for audience in ('paid', 'free'):
        webhook = env.get('MARKET_WATCH_DISCORD_' + audience.upper() + '_WEBHOOK', '')
        chat = env.get('MARKET_WATCH_TELEGRAM_' + audience.upper() + '_CHAT_ID', '')
        if webhook:
            parts = urlparse(webhook)
            if (parts.scheme != 'https' or parts.netloc != 'discord.com'
                    or not re.fullmatch(r'/api(?:/v\d+)?/webhooks/\d+/[A-Za-z0-9_.-]+', parts.path)
                    or parts.query or parts.fragment):
                raise ValueError('invalid Discord webhook configuration')
            routes.append(Route('discord', audience, urlunparse(parts)))
        if chat:
            if not re.fullmatch(r'\d+:[A-Za-z0-9_-]+', token) or not re.fullmatch(r'-?\d+', chat):
                raise ValueError('Telegram requires a bot token and numeric channel id')
            routes.append(Route('telegram', audience, 'https://api.telegram.org/bot' + token + '/sendMessage', chat))
    destinations = [(r.platform, urlparse(r.endpoint).path.split('/')[-2] if r.platform == 'discord' else r.chat_id) for r in routes]
    if len(set(destinations)) != len(destinations):
        raise ValueError('free and paid destinations must be different')
    return routes


def send(route, text, client, presentation=None):
    # One message per event keeps retries unambiguous. Never truncate paid evidence.
    if len(text.encode('utf-16-le')) // 2 > (6000 if route.platform == 'discord' and presentation else 1900 if route.platform == 'discord' else 3900):
        raise RemoteError('message_too_long')
    if route.platform == 'discord':
        payload = {'allowed_mentions': {'parse': []}}
        if presentation is None:
            payload['content'] = text
        else:
            try:
                payload['embeds'] = [validate_presentation(presentation)]
                if presentation['format'] == 'tokn-card-v2':
                    payload.update(username=WEBHOOK_NAME, avatar_url=ICON_URL)
            except (ValueError, TypeError, KeyError, OverflowError):
                raise RemoteError('invalid_presentation') from None
        response = client.call(route.endpoint + '?wait=true', payload)
        if not isinstance(response, dict) or not response.get('id'):
            raise RemoteError('missing_delivery_receipt', ambiguous=True)
        return str(response['id'])
    response = client.call(route.endpoint, {
        'chat_id': route.chat_id, 'text': text, 'protect_content': route.audience == 'paid',
        'link_preview_options': {'is_disabled': True},
    })
    if not isinstance(response, dict) or response.get('ok') is not True:
        code = response.get('error_code') if isinstance(response, dict) else None
        if code == 429:
            raise RemoteError('http_429', retry_after=response.get('parameters', {}).get('retry_after', 60))
        raise RemoteError('telegram_rejected', ambiguous=True)
    receipt = response.get('result', {}).get('message_id')
    if receipt is None:
        raise RemoteError('missing_delivery_receipt', ambiguous=True)
    return str(receipt)


def dispatch(store, routes, client, clock=time.time):
    mapping = {r.name: r for r in routes}
    totals = {'sent': 0, 'pending': 0, 'unknown': 0, 'failed': 0, 'expired': 0}
    blocked = set()
    for row in store.pending(clock()):
        now = clock()
        if row['expires_at'] <= now:
            store.delivery_state(row['id'], 'expired', now, error='message_expired')
            totals['expired'] += 1
            continue
        route = mapping.get(row['route'])
        if not route or route.audience != row['audience']:
            store.delivery_state(row['id'], 'failed', now, error='destination_changed')
            totals['failed'] += 1
            continue
        retry_at = store.get_meta('rate_limit:' + route.name) or 0
        if route.name in blocked or now < retry_at:
            continue
        store.delivery_state(row['id'], 'sending', now)
        try:
            try:
                presentation = json.loads(row['evidence']).get('presentation')
            except (ValueError, TypeError, AttributeError):
                raise RemoteError('invalid_archived_presentation') from None
            receipt = send(route, row['text'], client, presentation)
            store.delivery_state(row['id'], 'sent', clock(), remote_id=receipt)
            totals['sent'] += 1
        except RemoteError as exc:
            blocked.add(route.name)
            status = 'unknown' if exc.ambiguous else 'failed'
            delay = 0
            if exc.code == 'http_429':
                status = 'pending'
                try:
                    delay = max(1, min(86400, float(exc.retry_after)))
                except (ValueError, TypeError):
                    delay = 60
                blocked.add(route.name)
                with store.db:
                    store.set_meta('rate_limit:' + route.name, clock() + delay)
            store.delivery_state(row['id'], status, clock(), error=exc.code, delay=delay)
            totals[status] += 1
    return totals
