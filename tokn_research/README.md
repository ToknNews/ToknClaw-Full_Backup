# Offline research foundation — synthetic M0 only

This package implements the approved first foundation milestone: immutable data
contracts, honest capability availability, a causal replay clock, training-time
isolation and leakage diagnostics. It uses only the Python standard library.
It contains **no estimator, strategy, backtest P&L, order, execution adapter,
risk policy, collector, service or deployment integration**.

All accepted bar and training provenance must be explicitly `synthetic`.
`TEST/Q`, `fixture-venue`, ten-second bars and diagnostic thresholds in the tests
are artificial fixtures. They do not approve an asset, venue, timeframe, target
volatility, cooldown, capital allocation or risk limit.

Existing historical backtesting and the absence of verified historical coverage
cannot substantiate strategy profitability. Passing these tests establishes only
the specified behavior on synthetic inputs. No empirical strategy is evaluated.

## Boundaries and interfaces

| Path | Responsibility |
| --- | --- |
| `contracts.py` | Explicit series identity/units, closed bars, revision provenance, timing declarations for training, and diagnostic feature values |
| `data/asof.py` | An immutable in-memory `SyntheticArchive`; point-in-time bar selection and training slices |
| `data/capabilities.py` | `Available` fixture records or `NotAvailable` with reason codes |
| `simulation/clock.py` | Explicit monotonic `ReplayClock`, checkpoint and restore; no wall clock |
| `simulation/replay.py` | Read-only feature contexts, causal provenance validation, immutable traces and rejected-run errors |
| `research/leakage.py` | One-bar forward-shift sensitivity and prefix-invariance diagnostics |
| `tests/test_foundation.py` | Synthetic behavior, negative controls and failure cases |

The package is a sibling of Market Watch. It does not import `market_watch`, the
legacy `signal_engine`, ToknNews or their configuration. There is no filesystem,
database, provider or live-data adapter. The archive receives in-memory tuples.
No additional dependencies, shared environment, secret or installation is needed.

### Bars and availability

`SeriesKey` requires venue, exact instrument, contract kind, base/quote/settlement
units and interval seconds. There are no default trading choices. `Bar` records
schema version, event-open/close time, receipt time, available time, OHLC,
base-denominated volume, source/record/revision and quality flags. Values must be
finite and OHLC/interval constraints must agree. Aware timestamps normalize to
UTC. Contracts copy mutable input containers into immutable tuples.

Unknown receipt and availability timestamps are both `None`. They are not filled
from event time. Such records cannot become visible in an as-of window.
Known timestamps obey `event_close <= received_at <= available_at`, and visibility
requires `available_at < decision_at`. Data known exactly at a decision is excluded.
This prevents using a candle's final values for a retrospective same-close action.

`SyntheticArchive.as_of(series, cutoff)` selects the highest known revision of
each bar at that cutoff. Later revisions cannot rewrite an earlier view. Exact
duplicates are idempotent; conflicting copies of the same revision are rejected.
Overlapping eligible bars are rejected. A flagged selected revision restricts
availability; the reader cannot silently fall back to an older clean revision.

`Available` means only that some causal, unflagged **synthetic fixture records**
exist. Its scope is `fixture_records_only`, with coverage explicitly marked
`completeness_and_freshness_not_assessed`. It does not certify contiguous history,
a minimum sample, two years of data, a current feed or suitability for fitting.
M0 deliberately selects no freshness threshold. Record gaps and partial training
windows remain visible through the returned records; no series is forward-filled.

`capabilities(series, cutoff)` reports only closed fixture bars as potentially
available. Settled funding, historical spot hedges, trade prints, liquidation
prints, depth history, synchronized two-venue ticks and fitted models return
`NotAvailable(UNSUPPORTED_IN_M0)`. Two candle venues do not establish tick data.
Unsupported measurements are not represented by zeros or fabricated series.

### Training isolation without fitting

`TrainingManifest` is a **synthetic metadata declaration**, not a trained artifact.
It records training start/end, fit completion, transform-fit cutoff and the latest
label-availability time. Training ends before fit completion; the transform cutoff
stays inside training; labels must be available before the fit completes.

`training_slice(series, manifest)` includes only bars entirely inside the training
window and known strictly before fit completion. Late receipts and revisions are
excluded rather than backdated. Empty or flagged training slices are rejected.
Its fingerprint includes the actual selected records and manifest. Changes to
future test records do not affect this fingerprint.

Replay additionally requires fit completion strictly before first use and matching
series identity. This validates declared timing and supplied slices; it does not
verify an actual scaler, fit, label generator or model, none of which exists in M0.
Purging, embargo, walk-forward fitting and minimum empirical coverage are later
work requiring their own approved specifications.

### Causal feature replay

`replay(archive, series, decision_times, feature, *, feature_id, training=None)`
requires explicit, strictly increasing decision times. A callback receives a
`ReplayContext` containing only the current causal bar window and optional prior
training slice. It returns `FeatureResult(values, available_at, source_refs)`.

References must exist in that window. Feature availability cannot predate its
source availability or training completion, and must precede the decision.
Nonfinite values, empty provenance, unavailable data and callback failures reject
the run with an exception; no partly valid trace is returned. Successful output
is immutable synthetic feature evidence, with source/training fingerprints and
scope `offline_foundation_diagnostic_only`. It has no order or P&L path.

Callbacks must be pure, trusted local test code. Python callbacks are **not an OS
sandbox**: they could lie about provenance or close over external data. Structural
checks cannot prove truthfulness or universal causal correctness. The negative
controls below expose representative errors. No untrusted callback is authorized.

### Leakage controls

`check_forward_shift(trace, diagnostic)` intentionally substitutes the next bar's
feature values in a separate diagnostic. It requires actual adjacent bars, not
merely consecutive snapshots. Both paths use the same `n - 1` evaluation positions;
the final unmatched frame is excluded. The diagnostic emits nonempty text labels,
not trading actions. Identical vectors are evaluated consistently and repeated
evaluation detects a stateful probe that otherwise could fake sensitivity.

The fixture uses markers `[10, 30, 20, 40]`. A test-only threshold produces
`[below, above, below]`; the one-bar shift produces `[above, below, above]`.
All three diagnostic positions change. Constant features and feature-independent
controls reject with `SHIFT_NO_EFFECT`. Insensitivity is not proof of leakage,
but cannot pass the requested sensitivity gate. A passing result explicitly sets
`establishes_no_leakage=False`; it does not establish profitability or absence of
all future leakage. Shifted data cannot enter ordinary causal replay.

`check_prefix_invariance(prefix, extended)` compares complete earlier frames,
including feature identity, source evidence and training fingerprint. Future
appends, late revisions and poisoning must leave the prefix unchanged. A deliberate
closure over poisoned future data fails with `PREFIX_CHANGED`.

## Offline verification

From this repository root, in an authorized offline session:

```sh
python3 -B -m unittest discover -s tokn_research/tests -v
python3 -B -m unittest discover -s market_watch/tests -v
```

No installer, collection command, service start or strategy run is needed.
Tests use synthetic in-memory records only. The implementation was preceded by
the test specification and an initial missing-module red run. Further negative
tests reproduced false acceptance of malformed reconstructed traces and a stateful
shift diagnostic before those cases were corrected. See the milestone specification
for the requirement/review map.

## Stop after this milestone

The next stage is not authorized by this package. No H0–H8 estimator, strategy
promotion, live data acquisition, archive ingestion, risk-control change, product
integration, merge, deployment or live-capital action is included. Existing Market
Watch and the separately reviewed scorecard remain independent. Independent review
must wait for the parent to confirm a portfolio slot before it is requested.

## WHAT COULD BLOW UP THIS ACCOUNT

This milestone cannot operate an account. Its relevant failure modes are future
data leakage, fabricated availability, mislabeled fixtures and overstated test
evidence. Timestamp gates, provenance, explicit unavailable states and negative
controls address the demonstrated synthetic cases; they are not production
controls. Exchange outages, gap losses, funding sign errors, model drift, feed
loss, thin exits, lead reversals, key leakage and risk-override prevention still
require tested controls in separately approved later stages before any live capital.
