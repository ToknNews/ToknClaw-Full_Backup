"""Offline design samples. All values are fictional; this module cannot publish."""

import argparse
from copy import deepcopy
from dataclasses import asdict, replace
from datetime import datetime, timezone
import html
import json

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
    cards = []
    for item in items:
        embed = item['presentation']['discord']
        fields = ''.join('<section class="field"><h3>' + html.escape(field['name'])
                         + '</h3><p>' + html.escape(field['value']) + '</p></section>' for field in embed['fields'])
        cards.append('<article class="message" data-kind="' + html.escape(item['kind']) + '">'
                     '<div class="byline"><span class="avatar">T</span><strong>Tokn Market Watch</strong>'
                     '<span class="app">APP</span><span class="demo">DEMO</span></div>'
                     '<div class="card" style="--accent:#' + format(embed['color'], '06x') + '">'
                     '<div class="brand">' + html.escape(embed['author']['name']) + '</div>'
                     '<h2>' + html.escape(embed['title']) + '</h2><p class="description">'
                     + html.escape(embed['description']) + '</p>' + fields
                     + '<footer>' + html.escape(embed['footer']['text']) + '</footer></div></article>')
    options = ''.join('<option value="' + html.escape(item['kind']) + '">'
                      + html.escape(item['kind'].replace('_', ' ').title()) + '</option>' for item in items)
    return '''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Tokn Market Watch · Message design</title><style>
*{box-sizing:border-box}body{margin:0;background:#101316;color:#edf0f5;font:15px/1.5 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
.page{max-width:1240px;margin:auto;padding:42px 28px}.eyebrow{color:#38bdf8;font-size:11px;letter-spacing:3px;font-weight:750}
h1{font-size:38px;line-height:1.15;letter-spacing:-1.4px;margin:12px 0}.intro{color:#aab3bf;max-width:770px;margin:0 0 20px}
.notice{display:inline-block;border:1px solid #665225;background:#302919;color:#f8d177;border-radius:8px;padding:9px 14px;font-size:12px;font-weight:700}
.toolbar{display:flex;gap:12px;align-items:center;margin:26px 0;color:#aab3bf}select{background:#242932;border:1px solid #3c4350;color:#edf0f5;padding:10px 14px;border-radius:8px;font:inherit}
.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));align-items:start;gap:26px}.message{min-width:0}.byline{display:flex;align-items:center;gap:9px;margin-bottom:10px;font-size:13px}
.avatar{display:grid;place-items:center;width:30px;height:30px;border-radius:50%;background:#38bdf8;color:#071c27;font-size:18px;font-weight:850}
.app{font-size:10px;background:#5865f2;border-radius:3px;color:white;padding:0 4px;font-weight:700}.demo{color:#77828f;font-size:10px;letter-spacing:1px}
.card{background:#20252c;border:1px solid #303741;border-left:4px solid var(--accent);padding:22px 23px;border-radius:4px 10px 10px 4px;min-width:0}
.brand{font-size:10px;letter-spacing:2px;color:#b3bdca;font-weight:750}h2{font-size:20px;line-height:1.3;margin:10px 0;color:#fff;letter-spacing:-.3px}
.description{color:#adb8c7;font-size:12px;margin:0;white-space:pre-line}.field{margin-top:19px}.field h3{font-size:13px;margin:0 0 5px;color:#f4f6f8;font-weight:750}
.field p{white-space:pre-line;margin:0;color:#d0d7e1;font-size:13px;font-variant-numeric:tabular-nums;overflow-wrap:anywhere}
footer{border-top:1px solid #343b45;margin-top:20px;padding-top:12px;color:#909cab;font-size:10px;line-height:1.5}.fine{margin-top:30px;color:#7d8896;font-size:12px}
[hidden]{display:none!important}@media(max-width:760px){.page{padding:26px 16px}h1{font-size:30px}.grid{grid-template-columns:1fr}.card{padding:18px 16px}.toolbar{flex-wrap:wrap}.field p{font-size:12px}}
</style></head><body><main class="page"><div class="eyebrow">TOKN / MARKET WATCH</div>
<h1>Read the market. Skip the noise.</h1><p class="intro">What changed. Why it matters. What to check next. Current rule thresholds make each interpretation reviewable. Discord uses native cards; Telegram gets the same information as plain text.</p>
<div class="notice">DESIGN PREVIEW · ALL MARKET VALUES ARE FICTIONAL</div>
<div class="toolbar"><label for="kind">Preview a message</label><select id="kind"><option value="all">All formats</option>''' + options + '''</select></div>
<div class="grid">''' + ''.join(cards) + '''</div><p class="fine">Independent fictional examples, not one chronological watch. Illustrative layout. Discord fonts, wrapping and timestamp placement vary by device. Colors identify message types, not confidence or expected returns. No network calls, webhooks or tracking are embedded in this preview.</p></main>
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
