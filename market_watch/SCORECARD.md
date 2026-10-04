# Operator shadow-results scorecard

`scorecard` describes archived Setup Engine evidence. It is local and operator-only:
it does not collect data, replay strategy rules, enqueue messages, migrate a schema,
change configuration or calculate trading performance. The existing `outcomes`
command continues to describe original market alerts, independently of setups.

## Invocation

Use a reviewed checkout and an existing, locally authorized schema-3 archive:

```bash
python3 -m market_watch --database /path/to/existing/archive.sqlite3 scorecard \
  --start 2026-10-04T00:00:00+00:00 \
  --end 2026-10-05T00:00:00+00:00 \
  --timezone America/New_York --details
```

The command emits JSON to stdout. `--database`, `--start`, `--end` and
`--timezone` are required. Dates need explicit UTC offsets; local daylight-saving
ambiguities must be resolved by the operator. The timezone only controls display.
The window is **start inclusive, end exclusive**, at most 365 elapsed days; `end`
is also the evidence cutoff. Events or samples at/after the cutoff are excluded.
No implicit current-time cutoff or "latest state" is substituted.
Numeric timestamps are UTC Unix seconds; the explicitly labeled local window
includes its applicable UTC offsets.

`--config` is rejected for this command. Runtime settings, environment destinations
and credentials are not read. A missing archive is an error; it is not created.
An older schema is rejected without migration. The connection uses SQLite
`mode=ro`, `query_only`, and a single explicit read transaction covering schema,
events and screening samples. Concurrent writes cannot enter midway through the
report. SQLite may coordinate readers through its existing WAL/shared-memory
mechanism; no application state, queue, schema or archive rows are written.

Do not publish actual reports or operator archives in the public repository or a
PR. This command neither downloads a production database nor grants access to one.

## Populations and denominators

Only formations whose **frozen** `spec.config.setup_publish` is false are included.
That is shadow intent, not proof of delivery or non-delivery. Live-intent records
are listed as exclusions. No historical watch receives today's configuration.

| Population | Definition |
| --- | --- |
| `formed_in_window` | Distinct original setup IDs created in `[start, end)` |
| `carry_in` | Earlier original IDs still nonterminal immediately before `start`; terminal events exactly at start belong here |
| Prior closed | Earlier IDs conclusively terminal before start; counted separately, excluded from both populations |
| Excluded evidence | Live-intent, malformed formation, unlinked event or missing original; reasons remain visible |

Each population reports its own denominator, confirmations and phase breakdown.
Exclusions audit the retained event prefix before cutoff, including older
originals. They are event/ID diagnostics, not a distinct-setup denominator to add
to either population's count.
Carry-in is never added to the new-formation conversion denominator. A setup can
produce many cards but contributes once per count. Confirmations `by_cutoff`
include its earlier history; `in_window` counts the first archived confirmation
only when it occurred inside the window. Repeated updates do not reconfirm a watch.

The phase denominators partition included IDs:

- `before_retest`: no archived retest and no unresolved event-integrity issue.
- `after_retest`: an archived `triggered` event exists before cutoff. It means a
  retest and indicative-quote check passed, **not an entry fill**.
- `unknown_retest`: missing/inconsistent evidence prevents assigning that phase.

States come from immutable `events` plus `setup_events` links, never the mutable
current `setups.payload`. A later terminal state cannot leak into an earlier cutoff.
The report does not infer missing transitions from later candles or current state.

## State and sample interpretation

`forming`, `armed`, `triggered` and `target_1` remain active until an archived
terminal event exists. Passing a configured deadline without a recorded closing
event does not invent an expiry. Active reasons describe the last emitted lifecycle
event, not every quiet check. `last_event_at` in details is not a collector heartbeat.

`paused`/`resumed` overlay observability without replacing lifecycle stage. Paused
counts and reasons are separate. Terminal counts retain exact stage and reason:
pre-entry failure, entry expiry/extension, post-retest invalidation, target two,
same-bar/issuance-bar ambiguity, missed candles, tracking expiry, update limit and
cancellation are not pooled as wins or losses. Event-sequence gaps are explicitly
`evidence_unavailable`; they are not presumed successful price paths.

`target_1_event_observed` counts IDs with an explicit first-target event.
`target_2_event_observed` counts IDs with a completion event. A direct jump to
target two does not invent a separate first-target event. Both counts cover the
selected IDs' history before cutoff. First-target then invalidation is shown
explicitly; the terminal outcome stays invalidation. No partial exit is assumed.

`insufficient_sample` means the particular population has no unambiguous archived
post-retest completion/invalidation path. Empty archives, pre-entry-only samples,
all-open, all-ambiguous or all-unavailable paths therefore remain insufficient.
At least one such path changes the label to `descriptive_only`, **never to
statistically sufficient**. This is an availability label, not a calibrated sample
size or significance test. Counts cannot establish expected profit or a win rate.

## Versions and frozen estimated economics

Cohorts separate asset, direction, venue/instrument, quote, timeframe, setup
version, frozen `setup_*` settings and the full recorded cost policy. Legacy
formations without `cost_screen` stay `legacy`; their hypothetical costs are
unavailable, never recomputed using `execution-costs-v1` defaults. Different fee
assumptions remain separate even when the policy version string is the same.

Each cohort summarizes **archived estimated** target-one and target-two net
reward/risk at the formation trigger, entry cap and retest's indicative quote.
Available/unavailable counts accompany min/median/max. These summaries cover both
included populations in that cohort; lifecycle denominators remain separate.
`--details` includes each ID, frozen levels, complete recorded formation estimate,
confirmation estimate, observed transitions and evidence issues. It never
recalculates economic thresholds or rewrites an original watch.

Each target estimate is a separate hypothetical full exit. No fill, partial-exit
allocation, realized fee/slippage/funding, leverage, latency or account P&L is
measured. A target touch is not an execution receipt or proven profitable trade.

## Screening, retries and coverage

Screen evidence comes only from existing `setup_samples.health.screen` and
`screen_details`. For each asset/requested five-minute decision close, the
**latest health sample** and **latest explicit valid cost decision** are retained
separately, ordered by collection time then row ID. A tracking-only retry has no
new cost decision: it must not erase the acceptance that formed the watch. A
genuine later explicit cost decision supersedes the earlier decision, including
a rejection followed by acceptance. Retries do not add opportunities.

`cohorts` describes latest health/screen observations. `cost_decision_cohorts`
describes the retained explicit cost decisions with their own denominators. Raw
asset-attempt counts and explicit-cost-attempt counts each disclose their own
deduplication. Both populations deduplicate before grouping or mode exclusion.
If policy/publication mode changes only in a later tracking sample, the earlier
decision keeps its recorded context. `health_context_changed_since_cost_decision`
discloses these differences; the health and cost populations must not be conflated.

Both sample collection time and requested decision close must fall in the report
window. A late retry for an earlier decision close is disclosed separately.
Live-publication health buckets and cost-decision buckets are excluded separately
using their respective recorded publication modes. Each cohort uses its own
**sample's policy**, not the policy of an active older watch. Pre-cost or missing
health policy metadata is `unrecorded`, never backfilled.

`screen_counts` includes tracking states and noncandidate gates such as cooldown,
no range, liquidity and source issues. These are not all cost rejections.
`cost_screened_buckets` requires explicit matching policy and a reasons list.
An empty list is an accepted cost screen; a nonempty list is a rejection. Each
unique reason counts once per bucket, so **multi-reason counts can exceed the
rejected-bucket denominator**. Buckets are not distinct setups or independent trials.

Coverage lists the observed asset population, expected five-minute closes,
sampled/unobserved buckets, largest missing run, primary-issue buckets and last
collection time. Coverage includes all recorded publication modes; shadow-only
screen totals are separately labeled. A sample is not proof of usable data or a
formation. Optional-source completeness is not reconstructed. Invalid sample
rows/details are disclosed; their evidence cannot establish coverage or a decision.
No archived historical universe manifest identifies entirely absent assets or
disabled periods, so expected counts are only a time-grid reference **for observed
assets**. Missing buckets are unknown, not rejections or invented healthy readings.

## Fictional output excerpt

The fixture `test_documented_synthetic_example_totals` uses four new IDs: one
pre-retest failure, one first-target-then-invalidation, one ambiguous path, and
one still-open retest. A fifth, older open watch is carry-in. Nothing below is
operator data. Selected fields from its JSON output:

```json
{
  "formed_in_window": {
    "distinct_setups": 4,
    "breakout_confirmed_by_cutoff": 3,
    "retest_confirmed_by_cutoff": 3,
    "target_1_then_invalidation": 1,
    "after_retest": {
      "denominator_distinct_setups": 3,
      "active_at_cutoff": 1,
      "state_counts": {"ambiguous": 1, "invalidated": 1, "triggered": 1}
    },
    "sample_state": "descriptive_only"
  },
  "carry_in": {"distinct_setups": 1, "sample_state": "insufficient_sample"}
}
```

These are counts of archived conditions, not a profit report. Use the complete
cohort, exclusion, coverage and uncertainty sections alongside any excerpt.

## Offline verification

```bash
python3 -m unittest discover -s market_watch/tests -v
```

Fixtures cover empty archives, exact boundaries, carry-in, mixed policies, retries,
repeated updates, pre-entry failure, first-target then invalidation, ambiguity,
tracking gaps, paused/open cutoffs, frozen estimates, missing/old archives,
unchanged archive bytes/tables and a concurrent write between read queries. A
real-writer synthetic fixture preserves an accepted BTC screen when missing ETH
data causes a same-bucket tracking retry. Separate cases exercise policy/mode
changes and genuinely superseding cost decisions.
