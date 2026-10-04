"""Offline design samples. All values are fictional; this module cannot publish."""

import argparse
import base64
from copy import deepcopy
from dataclasses import asdict, replace
from datetime import datetime, timezone
import html
import json
from pathlib import Path

from .config import Config
from .models import Observation
from .presentation import ALERT_COPY, alert_card, brief_card, followup_card, health_card


NOW = datetime(2026, 9, 29, 12, 0, tzinfo=timezone.utc).timestamp()


def sample(asset, venue, mark, notional, bps=1.2):
    interval = 1 if venue == 'hyperliquid' else 4
    return Observation(venue, asset, asset if venue == 'hyperliquid' else asset + '-USDT-SWAP',
                       NOW - 4, NOW - 2, 'receipt' if venue == 'hyperliquid' else 'exchange',
                       mark, notional / mark, notional, bps / 10000 * interval / 8, interval)


def sample_changes(rows, price_pct=1.28, oi_pct=4.6, now=NOW):
    changes = []
    for row in rows:
        base_price = row.mark_price / (1 + price_pct / 100)
        base_oi = row.oi_base / (1 + oi_pct / 100)
        base = replace(row, observed_at=now - 904, fetched_at=now - 902,
                       mark_price=base_price, oi_base=base_oi, oi_usd=base_price * base_oi)
        changes.append({'venue': row.venue, 'price_pct': price_pct, 'oi_base_pct': oi_pct,
                        'baseline': base.to_dict()})
    return changes


def examples():
    cfg = Config()
    btc = [sample('BTC', 'hyperliquid', 64820, 12.4e9), sample('BTC', 'okx', 64802, 5.1e9, 1.8)]
    eth = [sample('ETH', 'hyperliquid', 3388, 3.2e9, -0.6), sample('ETH', 'okx', 3386, 1.8e9, -0.8)]
    sol = [sample('SOL', 'hyperliquid', 143.10, 920e6, 1.0), sample('SOL', 'okx', 143.06, 610e6, 1.4)]
    results = []
    for rule in ALERT_COPY:
        rows = btc
        change = 1.28
        if rule == 'price_oi_down':
            rows = [replace(o, mark_price=o.mark_price * 0.98, oi_usd=o.oi_usd * 0.98) for o in btc]
            change = -1.02
        if rule in {'positive_funding', 'negative_funding', 'funding_divergence'}:
            rates = (5, 4) if rule == 'positive_funding' else (-5, -4) if rule == 'negative_funding' else (1.2, 4.8)
            rows = [replace(o, funding_rate=bps / 10000 * o.funding_interval_hours / 8) for o, bps in zip(btc, rates)]
        text, presentation = alert_card(cfg, rule, 'BTC', rows, sample_changes(rows, change), NOW, reference='demo-btc-watch')
        results.append({'kind': rule, 'text': text, 'presentation': presentation})
    # Independent alternatives, not one chronological lifecycle.
    for kind, condition, reason, recovered, minute, sequence in [
        ('followup_holding', 'holding', '', False, 5, 1),
        ('followup_faded', 'faded', 'condition_faded', False, 10, 2),
        ('followup_unavailable', 'unavailable', '', False, 10, 2),
        ('followup_recovered', 'holding', '', True, 15, 3),
        ('followup_ended', 'holding', 'horizon_elapsed', False, 60, 4),
    ]:
        checked = NOW + minute * 60
        rows = [] if condition == 'unavailable' else [
            replace(o, observed_at=checked - 4, fetched_at=checked - 2,
                    mark_price=o.mark_price * 1.01, oi_base=o.oi_base * 1.02, oi_usd=o.oi_usd * 1.01 * 1.02)
            for o in btc]
        detail = {'original_id': 'demo-btc-watch', 'original_created_at': NOW, 'asset': 'BTC',
                  'rule': 'price_oi_up', 'config': asdict(cfg), 'horizon_at': NOW + 3600,
                  'checked_at': checked, 'condition': condition, 'closed_reason': reason,
                  'assessment': 'coverage_unavailable' if condition == 'unavailable' else 'fresh_check',
                  'recovered': recovered, 'sequence': sequence,
                  'observations': [o.to_dict() for o in rows],
                  'comparisons': sample_changes(rows, price_pct=0.2 if condition == 'faded' else 1.28, now=checked),
                  'since_original': [{'venue': o.venue, 'price_pct': 1.0, 'oi_base_pct': 2.0,
                                      'funding_delta_bps_8h': 0.0} for o in rows]}
        text, presentation = followup_card(cfg, detail, rows)
        results.append({'kind': kind, 'text': text, 'presentation': presentation})
    # Funding can remain elevated while the separate directional scenario changes.
    checked = NOW + 600
    rows = [replace(o, observed_at=checked-4, fetched_at=checked-2,
                    mark_price=o.mark_price*0.98, oi_base=o.oi_base*1.03, oi_usd=o.oi_usd*0.98*1.03,
                    funding_rate=bps/10000*o.funding_interval_hours/8) for o,bps in zip(btc,(5,4))]
    detail = {'original_id': 'demo-funding-watch', 'original_created_at': NOW, 'asset': 'BTC',
              'rule': 'positive_funding', 'checked_at': checked, 'condition': 'holding',
              'closed_reason': '', 'recovered': False, 'sequence': 2, 'direction_changed': True,
              'comparisons': sample_changes(rows, price_pct=-1.02, now=checked),
              'since_original': [{'venue': o.venue, 'price_pct': -2.0, 'oi_base_pct': 3.0,
                                  'funding_delta_bps_8h': 0.0} for o in rows]}
    text, presentation = followup_card(cfg, detail, rows)
    results.append({'kind': 'followup_trade_read_changed', 'text': text, 'presentation': presentation})
    all_rows = btc + eth + sol
    changes = {'BTC': sample_changes(btc), 'ETH': sample_changes(eth, -0.35, 1.2),
               'SOL': sample_changes(sol, 0.63, -1.1)}
    for audience, kind, covered, rows in [('paid', 'am_brief', cfg.assets, all_rows),
                                          ('free', 'free_look', ('BTC',), btc)]:
        text, presentation = brief_card(cfg, audience, covered, rows, changes, {}, NOW)
        results.append({'kind': kind, 'text': text, 'presentation': presentation})
    for kind, issues in [('data_limited', {'okx:SOL': 'stale_or_future_measurement'}), ('data_restored', {})]:
        text, presentation = health_card(cfg, issues, NOW)
        results.append({'kind': kind, 'text': text, 'presentation': presentation})
    for result in results:
        result['text'] = 'DEMO VALUES — NOT LIVE DATA\n\n' + result['text']
        result['presentation'] = deepcopy(result['presentation'])
        result['presentation']['discord']['title'] = 'DEMO · ' + result['presentation']['discord']['title']
    return results


def render_html(items):
    def asset(name, mime):
        data = (Path(__file__).with_name('assets') / name).read_bytes()
        return 'data:' + mime + ';base64,' + base64.b64encode(data).decode('ascii')

    cards = []
    for item in items:
        embed = item['presentation']['discord']
        fields = ''.join('<section class="field"><h3>' + html.escape(field['name'])
                         + '</h3><p>' + html.escape(field['value']) + '</p></section>' for field in embed['fields'])
        thumbnail = '<span class="coin thumbnail" role="img" aria-label="Tokn coin"></span>' if 'thumbnail' in embed else ''
        banner = '<div class="banner" role="img" aria-label="Tokn circuit-board banner"></div>' if 'image' in embed else ''
        cards.append('<article class="message" data-kind="' + html.escape(item['kind']) + '">'
                     '<div class="byline"><span class="coin avatar" role="img" aria-label="Tokn avatar"></span>'
                     '<strong>Tokn Market Watch</strong><span class="app">APP</span><span class="demo">DEMO</span></div>'
                     '<div class="card" style="--accent:#' + format(embed['color'], '06x') + '">'
                     + thumbnail + '<div class="brand"><span class="coin author-icon" aria-hidden="true"></span>'
                     + html.escape(embed['author']['name']) + '</div>'
                     '<h2>' + html.escape(embed['title']) + '</h2><p class="description">'
                     + html.escape(embed['description']) + '</p>' + fields + banner
                     + '<footer>' + html.escape(embed['footer']['text']) + '</footer></div></article>')
    options = ''.join('<option value="' + html.escape(item['kind']) + '">'
                      + html.escape(item['kind'].replace('_', ' ').title()) + '</option>' for item in items)
    asset_css = ':root{--tokn-coin:url("' + asset('Tokn_Favicon.png', 'image/png') + '");--tokn-banner:url("' + asset('YT_Banner_Tokn.jpg', 'image/jpeg') + '")}'
    return '''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Tokn Market Watch · Branded cards</title><style>''' + asset_css + '''
*{box-sizing:border-box}body{margin:0;background:#080f1d;color:#edf0f5;font:15px/1.5 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
.page{max-width:1240px;margin:auto;padding:40px 28px}.masthead{display:flex;align-items:center;gap:22px;margin-bottom:26px}.wordmark{width:148px;height:auto}.eyebrow{border-left:1px solid #2d73ff;padding-left:22px;color:#ccecff;font-size:11px;letter-spacing:3px;font-weight:750}
h1{font-size:38px;line-height:1.15;letter-spacing:-1.4px;margin:12px 0}.intro{color:#aab8cc;max-width:800px;margin:0 0 20px}
.notice{display:inline-block;border:1px solid #665225;background:#302919;color:#f8d177;border-radius:6px;padding:9px 14px;font-size:12px;font-weight:700}
.toolbar{display:flex;gap:12px;align-items:center;margin:26px 0;color:#b5bfd0}select{background:#182235;border:1px solid #405575;color:#edf0f5;padding:10px 14px;border-radius:6px;font:inherit;max-width:100%}select:focus-visible{outline:2px solid #6a9cff;outline-offset:3px}
.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));align-items:start;gap:26px}.message{min-width:0}.byline{display:flex;align-items:center;gap:9px;margin-bottom:10px;font-size:13px}
.coin{display:inline-block;background-image:var(--tokn-coin);background-size:contain;background-position:center;background-repeat:no-repeat;flex-shrink:0}.avatar{width:34px;height:34px;border-radius:50%}
.app{font-size:10px;background:#5865f2;border-radius:3px;color:white;padding:0 4px;font-weight:700}.demo{color:#9aa7bb;font-size:10px;letter-spacing:1px}
.card{background:#202127;border:1px solid #30323b;border-left:4px solid var(--accent);padding:20px;border-radius:4px;min-width:0;display:flow-root}
.brand{display:flex;align-items:center;gap:7px;font-size:11px;color:#d7dce7;font-weight:700;min-height:20px}.author-icon{width:20px;height:20px}.thumbnail{float:right;width:66px;height:66px;margin:0 0 12px 14px}
h2{font-size:19px;line-height:1.3;margin:9px 0;color:#fff;letter-spacing:-.3px}.description{color:#b8bfcd;font-size:12px;margin:0;white-space:pre-line;overflow-wrap:anywhere}
.field{margin-top:18px;clear:both}.field h3{font-size:13px;margin:0 0 5px;color:#f4f6f8;font-weight:750}.field p{white-space:pre-line;margin:0;color:#d0d7e1;font-size:13px;font-variant-numeric:tabular-nums;overflow-wrap:anywhere}
.banner{width:100%;aspect-ratio:16/9;background:var(--tokn-banner) center/contain no-repeat;margin-top:20px;border-radius:4px}
footer{margin-top:18px;color:#a5afbf;font-size:10px;line-height:1.5}.fine{margin-top:30px;color:#a5b0c4;font-size:12px;max-width:870px}
[hidden]{display:none!important}@media(max-width:760px){.page{padding:26px 16px}h1{font-size:30px}.grid{grid-template-columns:1fr}.card{padding:16px}.toolbar{flex-wrap:wrap}.field p{font-size:12px}.wordmark{width:114px}.eyebrow{font-size:10px;letter-spacing:2px;padding-left:16px}.masthead{gap:16px}.thumbnail{width:54px;height:54px;margin-left:10px}.brand{font-size:10px}.byline{gap:7px;font-size:12px}}
</style></head><body><main class="page"><div class="masthead"><img class="wordmark" alt="Tokn" src="''' + asset('Tokn_Logo_Main_4.png', 'image/png') + '''"><div class="eyebrow">MARKET WATCH<br>MESSAGE DESIGN</div></div>
<h1>Read the market. Stay with the story.</h1><p class="intro">A conditional trade read. Long/short position guidance. Funding costs and follow-through. Tokn’s original coin and electric-blue palette carry through the feed; the circuit-board banner signs off scheduled briefs.</p>
<div class="notice">DESIGN PREVIEW · ALL MARKET VALUES ARE FICTIONAL</div>
<div class="toolbar"><label for="kind">Preview a message</label><select id="kind"><option value="all">All formats</option>''' + options + '''</select></div>
<div class="grid">''' + ''.join(cards) + '''</div><p class="fine">Independent fictional examples, not one chronological watch. Illustrative native Discord layout; fonts, wrapping, thumbnails and timestamp placement vary by device and theme. Native card backgrounds are controlled by Discord. Colors identify message types, not confidence or expected returns. Telegram retains matching plain text. This preview embeds the original images and makes no network requests.</p></main>
<script>document.getElementById('kind').addEventListener('change',function(){document.querySelectorAll('.message').forEach(function(card){card.hidden=this.value!=='all'&&card.dataset.kind!==this.value},this)})</script></body></html>'''


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--format', choices=('text', 'json', 'html'), default='text')
    parser.add_argument('--kind', choices=[item['kind'] for item in examples()])
    args = parser.parse_args(argv)
    items = [item for item in examples() if not args.kind or item['kind'] == args.kind]
    if args.format == 'html':
        print(render_html(items))
    elif args.format == 'json':
        print(json.dumps(items, indent=2, ensure_ascii=False))
    else:
        print('\n\n'.join(item['text'] for item in items))


if __name__ == '__main__':
    main()
