"""Offline, fictional setup-card previews. Never collects data or sends a message."""

import argparse
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone
import json

from .config import Config
from .message_preview import render_html
from .setup_cards import setup_card
from .setup_costs import confirmation_economics, screen_candidate
from .setup_data import Candle
from .setup_rules import candidate

NOW = datetime(2026, 10, 4, 12, 0, 20, tzinfo=timezone.utc).timestamp()


def examples():
    cfg = Config(setup_enabled=True)
    rows = []
    for i in range(64):
        center = [2808, 2816, 2824, 2832, 2824, 2816][i % 6]
        rows.append(Candle('hyperliquid','ETH',NOW-20-(64-i)*300,
                           center-2,center+4,center-4,center,1200,NOW))
    rows[-1] = replace(rows[-1],open=2829,high=2835,low=2828,close=2833)
    spec = candidate(cfg,'ETH',rows,NOW)
    if not spec:
        raise RuntimeError('invalid fictional preview fixture')
    spec, _ = screen_candidate(spec, cfg)
    if not spec:
        raise RuntimeError('fictional preview must pass the cost screen')
    book = {'observed_at':NOW-1,'received_at':NOW,'spread_bps':0.71,
            'bid_depth_usd':248000,'ask_depth_usd':217000}
    context = {'hyperliquid':{'change_15m_pct':.42,'oi_change_pct':2.31,'funding_bps_8h':1.2},
               'okx':{'change_15m_pct':.38,'oi_change_pct':1.74,'funding_bps_8h':1.6},
               'book':book,'spot':{'last':2832.7},'missing':[]}
    variants = [
        ('forming','range_edge_approach',0), ('armed','volume_backed_breakout',5),
        ('triggered','retest_closed_and_quote_in_band',10),
        ('target_1','first_reference_target_touched',20),
        ('completed','second_reference_target_touched',35),
        ('invalidated','invalidation_touched',20),
        ('paused','book_unavailable',15), ('resumed','fresh_check',20),
        ('ambiguous','both_boundaries_same_bar',25),
        ('unavailable','missed_candle',25), ('expired','entry_window_elapsed',60),
    ]
    items = []
    for stage, reason, minutes in variants:
        checked = NOW + minutes*60
        track = {'id':'DEMO-ETH-5M-004','spec':deepcopy(spec),
                 'stage':'armed' if stage in {'paused','resumed'} else stage}
        detail = {'reason':reason,'context':deepcopy(context),
                  'volume_ratio':1.64 if stage=='armed' else .93,
                  'candle':{**rows[-1].to_dict(),'open_at':checked-20-300}}
        if stage=='armed':
            detail['candle'].update(open=spec['level']-.1*spec['atr'],
                                   high=spec['trigger']+.2*spec['atr'],
                                   low=spec['level']-.3*spec['atr'],
                                   close=spec['trigger']+.1*spec['atr'])
        if stage in {'target_1','completed'}:
            target=spec['target_1' if stage=='target_1' else 'target_2']
            detail['candle'].update(open=spec['trigger'],high=target+.1*spec['atr'],
                                   low=spec['trigger']-.1*spec['atr'],close=target-.05*spec['atr'])
        if stage=='invalidated':
            detail['candle'].update(open=spec['trigger'],high=spec['trigger']+.1*spec['atr'],
                                   low=spec['invalidation']-.1*spec['atr'],close=spec['invalidation']-.05*spec['atr'])
        if stage=='ambiguous':
            detail['candle'].update(open=spec['trigger'],high=spec['target_1']+.1*spec['atr'],
                                   low=spec['invalidation']-.1*spec['atr'],close=spec['trigger'])
        if stage=='triggered':
            quote=(spec['trigger']+spec['entry_limit'])/2
            detail.update(indicative_quote=quote,
                          execution_costs=confirmation_economics(spec,quote),
                          remaining_reward_risk=(spec['target_2']-quote)/(quote-spec['invalidation']))
            detail['candle'].update(open=spec['level']+.05*spec['atr'],high=quote+.1*spec['atr'],
                                   low=spec['level']-.1*spec['atr'],close=(quote+spec['trigger'])/2)
        if stage in {'paused','unavailable'}:
            detail['context']={'missing':['Hyperliquid book','OKX 15m','Coinbase spot']}
            detail.pop('candle');detail.pop('volume_ratio')
        text,presentation=setup_card(cfg,track,stage,detail,checked)
        presentation['discord']['title']='DEMO · '+presentation['discord']['title']
        items.append({'kind':'setup_'+stage,'text':'DEMO VALUES — NOT LIVE DATA\n\n'+text,
                      'presentation':presentation})
    # A separate short scenario demonstrates direction-aware language and levels.
    mirrored=[replace(r,open=5600-r.open,high=5600-r.low,low=5600-r.high,close=5600-r.close) for r in rows]
    short=candidate(cfg,'ETH',mirrored,NOW)
    short, _ = screen_candidate(short, cfg)
    track={'id':'DEMO-ETH-SHORT-005','spec':short,'stage':'forming'}
    short_context=deepcopy(context)
    for venue in ('hyperliquid','okx'):
        short_context[venue]['change_15m_pct'] *= -1
    short_context['spot']['last']=5600-context['spot']['last']
    text,presentation=setup_card(cfg,track,'forming',{'candle':mirrored[-1].to_dict(),
                               'context':short_context,'volume_ratio':1.0},NOW)
    presentation['discord']['title']='DEMO · '+presentation['discord']['title']
    items.append({'kind':'setup_short','text':'DEMO VALUES — NOT LIVE DATA\n\n'+text,
                  'presentation':presentation})
    return items


def preview_html(items):
    return (render_html(items)
            .replace('Read the market. Stay with the story.', 'Know the setup. Follow the thesis.')
            .replace('Tokn Market Watch · Branded cards', 'Tokn Market Watch · Setup Engine')
            .replace('A conditional trade read. Long/short position guidance. Funding costs and follow-through. Tokn’s original coin and electric-blue palette carry through the feed; the circuit-board banner signs off scheduled briefs.',
                     'From a forming range to a confirmed retest. Fixed decision levels, a clear plan for each side, and an honest record of what happened next. Explore twelve fictional setup cards.')
            .replace('MESSAGE DESIGN','SETUP ENGINE'))


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--format',choices=('text','json','html'),default='text')
    parser.add_argument('--kind',choices=[item['kind'] for item in examples()])
    args=parser.parse_args(argv)
    items=[item for item in examples() if not args.kind or item['kind']==args.kind]
    if args.format=='html': print(preview_html(items))
    elif args.format=='json': print(json.dumps(items,indent=2,ensure_ascii=False))
    else: print('\n\n'.join(item['text'] for item in items))


if __name__=='__main__':
    main()
