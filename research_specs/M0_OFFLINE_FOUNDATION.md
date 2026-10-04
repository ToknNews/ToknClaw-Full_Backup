# M0: approved offline research foundation

Approval covers data contracts, honest capability availability, a causal replay
clock and leakage tests. Synthetic fixtures only. It does not resolve the owner's
asset, instrument, timeframe, volatility, cooldown, risk-budget, exit or manual
approval choices. Test values must never be promoted to those choices.

Working base: inspected local release snapshot
`79b7b0f119fe6fe4e57d51a55ed159f6a63ed4c4`. The isolated feature branch is
`feature/research-offline-foundation`. Remote freshness remains unverified while
the permitted GitHub settings change is being confirmed. No denied API retry or
alternative network route is part of this milestone.

The separately reviewed scorecard at
`7b87cc9a2640fe8b8b717bf6d9924f0f2cc884d3` is preserved in its own worktree and
branch. M0 does not depend on that unpublished feature or modify its code.

## Requirement and review map

| Requirement | Implemented boundary | Synthetic evidence |
| --- | --- | --- |
| Explicit data identity, units and chronology | `SeriesKey`, `Bar`, `Provenance` | Reject missing identity, invalid interval, naive timestamps, impossible receipt ordering, nonfinite prices and inconsistent OHLC |
| Honest missing inputs | Capability results with scope and reason codes | Missing receipt stays missing; unsupported series return `NotAvailable`; candle venues do not become tick capability |
| Point-in-time revisions | `SyntheticArchive` | Duplicate idempotency; conflicting revisions and unrelated correction lineage rejected; record identity cannot be reused across intervals/series; later receipt cannot change an earlier view |
| Quality restrictions | As-of reader checks the selected revision | Flagged evidence restricts availability instead of silently restoring an older clean revision |
| Causal injected clock | `ReplayClock` and explicit decision schedule | No rewind; explicit checkpoint/restore; no wall-clock dependency; repeated decision times rejected |
| Feature timing and source isolation | `ReplayContext`, `FeatureResult`, replay validation | Same-close use, future references, backdated features and callback failures reject without a partial trace |
| Train/test and transform/label isolation | `TrainingManifest`, `TrainingSlice` | Fit before first use; transform cutoff inside training; labels before fit; late receipts excluded; future poisoning preserves training fingerprint |
| One-bar shift sensitivity | `check_forward_shift` | Actual adjacent bars change three of three diagnostic positions; constant/B0-like controls reject; reordered reevaluation rejects the reproduced stateful and pairwise-stable call-order probes |
| Prefix invariance | `check_prefix_invariance` | Future appends/revisions preserve earlier frames; deliberately leaked future values fail |
| Evidence integrity | Validated references, immutable frames, traces and hashes | Reconstructed references require synthetic provenance and valid intervals; future-dated, empty, reversed or mismatched traces and malformed source digest sets reject |
| No runtime authority | Package has no estimator, risk policy, book, order, execution, collector or adapter to the existing systems | No path exists here to change risk controls or submit an order; this is a scope boundary, not a claim to have implemented a production kill switch |

## Acceptance and nonclaims

Acceptance is passing offline behavioral tests plus a source/specification review.
It is not model selection, a backtest, evidence of alpha or promotion of H0–H8.
Actual assets, data access and fit/risk choices remain unresolved. Available fixture
records do not certify completeness, freshness, historical coverage or suitability
for any research hypothesis. Training metadata does not implement a fitted model.

One-bar sensitivity is necessary for the requested candidate gate but not sufficient
to establish causal correctness. A feature-independent negative control is expected
to fail that gate without being characterized as leaky. All proof is bounded to the
specified synthetic cases; callbacks are trusted Python code, not sandboxed code.

Review must cover input validation, strict timestamp boundaries, revision selection,
source references, training isolation, immutable evidence, meaningful negative
controls and absence of changes to existing modules or runtime authority. An
independent reviewer may be requested only after the parent confirms a portfolio
slot; Social OS is the other implementation task.

## Local verification and review record

Initially, 49 foundation tests and 206 tests from the pinned Market Watch release passed
on Python 3.12.14: 255 total, zero failures/errors. A process-local audit guard
recorded zero network/subprocess attempts. All 11 new Python files parse with
Python 3.10 grammar; a Python 3.10 runtime was not tested. Runtime imports were
reviewed and are limited to the standard library and this package.

Tests were authored before implementation; the initial red run failed on the
missing contracts module. During subsequent self-review, additional tests first
reproduced eight assertion failures across four test methods: malformed source
digest sets, a future-dated reconstructed frame, malformed reconstructed traces,
and a stateful diagnostic falsely reporting shift sensitivity. The corrections
then passed those cases and the full guarded suite. A fifth added test confirms
that changing source metadata alone is not feature sensitivity.

After the parent confirmed a portfolio slot, one independent read-only reviewer
examined exact commit `f4729e5147e0256b1a58127abe2a5953a99bc061` and independently
passed all 49 tests with zero guarded network/subprocess attempts. The reviewer
confirmed three P2 findings: unrelated correction lineage could replace a bar;
reconstructed references lacked validation; and a diagnostic that changed output
only every two calls could fake shift sensitivity.

Seven new regression tests reproduced 14 assertion failures before correction.
The fixes enforce one stable source/record identity per event, validate references
at construction, and reevaluate diagnostic vectors after intervening inputs in
reverse and original order. The two-venue fixture now uses distinct source
identities. All 56 foundation tests pass after these changes. Follow-up independent
verification and final full-suite results are recorded in the handoff.

The requirement map above was checked against the implementation. No estimator,
empirical coverage claim, trading authority or change to existing Market Watch,
legacy or News modules is included. Review findings were addressed sequentially;
no implementation ran concurrently with the reviewer. Review is not deployment
approval, and finite callback checks cannot establish arbitrary Python purity.

## Stop conditions

No estimator, strategy, P&L/fill ledger, provider request, live dataset, order,
risk-control change, deployment, merge, purchase, permission change or broader
product work is authorized. Do not install packages or infer missing series.
Do not retry the denied GitHub call or route around it before the permitted
settings change is verified. Preserve all other worktrees and their commits.

The module README includes the required account-failure section and explicitly
states that historical backtesting and missing verified history cannot substantiate
profitability. Later research and paper execution require separately approved
specifications and controls.
