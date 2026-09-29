from copy import deepcopy
import hashlib
from pathlib import Path
import unittest

from market_watch.branding import ASSET_HASHES, BANNER_URL, ICON_URL, WEBHOOK_NAME
from market_watch.delivery import Route, dispatch, send
from market_watch.engine import market_alerts
from market_watch.http import RemoteError
from market_watch.message_preview import examples, render_html
from market_watch.presentation import validate_presentation
from market_watch.storage import Store
from test_market_watch import DISCORD, FakeClient, NOW, StoreCase, observation


class BrandCompatibilityTests(StoreCase):
    def test_legacy_card_survives_restart_and_delivers_without_reformatting(self):
        self.add_history()
        event = market_alerts(self.cfg, self.store,
                              [observation(v, price=102, oi=1040) for v in self.cfg.venues], NOW)[0]
        legacy = event.evidence['presentation']
        legacy['format'] = 'tokn-card-v1'
        legacy['discord']['author'].pop('icon_url')
        legacy['discord'].pop('thumbnail')
        original = deepcopy(legacy['discord'])
        route = Route('discord', 'paid', DISCORD)
        with self.store.db:
            self.store.add_event(event, [route])
        self.store.close()
        self.store = Store(self.path)
        client = FakeClient([{'id': 'legacy-receipt'}])
        self.assertEqual(dispatch(self.store, [route], client, lambda: NOW)['sent'], 1)
        self.assertEqual(client.calls[0][1], {'allowed_mentions': {'parse': []}, 'embeds': [original]})

    def test_branded_cards_send_only_one_receipted_request_with_fixed_identity(self):
        for item in examples():
            with self.subTest(kind=item['kind']):
                client = FakeClient([{'id': 'branded-receipt'}])
                self.assertEqual(send(Route('discord', 'paid', DISCORD), item['text'], client,
                                      item['presentation']), 'branded-receipt')
                self.assertEqual(len(client.calls), 1)
                endpoint, payload = client.calls[0]
                self.assertEqual(endpoint, DISCORD + '?wait=true')
                self.assertEqual(payload['username'], WEBHOOK_NAME)
                self.assertEqual(payload['avatar_url'], ICON_URL)
                self.assertEqual(payload['embeds'], [item['presentation']['discord']])
                self.assertEqual(payload['allowed_mentions'], {'parse': []})

    def test_asset_schema_rejects_mutable_external_or_extra_destinations_before_send(self):
        changes = [
            ('author', {'name': 'Tokn', 'icon_url': ICON_URL + '?redirect=1'}),
            ('author', {'name': 'Tokn', 'icon_url': ICON_URL, 'url': 'https://example.com'}),
            ('thumbnail', {'url': ICON_URL.replace('/70fcd4b37147acbb34294b5086d597d7d04bf2ce/', '/main/')}),
            ('thumbnail', {'url': BANNER_URL}),
            ('thumbnail', {'url': ICON_URL, 'proxy_url': 'https://example.com'}),
            ('image', {'url': 'https://example.com/private'}),
            ('image', {'url': BANNER_URL + '#fragment'}),
            ('image', None),
            ('footer', {'text': 'Tokn', 'icon_url': 'https://example.com'}),
            ('url', 'https://example.com'),
        ]
        for key, value in changes:
            item = examples()[0]
            item['presentation']['discord'][key] = value
            client = FakeClient([])
            with self.subTest(key=key, value=value), self.assertRaises(RemoteError):
                send(Route('discord', 'paid', DISCORD), item['text'], client, item['presentation'])
            self.assertFalse(client.calls)

    def test_legacy_schema_cannot_smuggle_branding_fields(self):
        for item in examples():
            item['presentation']['format'] = 'tokn-card-v1'
            with self.subTest(kind=item['kind']), self.assertRaises(ValueError):
                validate_presentation(item['presentation'])

    def test_preview_assets_match_originals_and_render_without_remote_image_requests(self):
        assets = Path(__file__).resolve().parents[1] / 'assets'
        for name, expected in ASSET_HASHES.items():
            with self.subTest(name=name):
                self.assertEqual(hashlib.sha256((assets / name).read_bytes()).hexdigest(), expected)
        output = render_html(examples())
        self.assertEqual(output.count('data:image/png;base64,'), 2)
        self.assertEqual(output.count('data:image/jpeg;base64,'), 1)
        self.assertNotIn('https://', output)
        self.assertNotIn('http://', output)
        self.assertNotIn(DISCORD, output)


if __name__ == '__main__':
    unittest.main()
