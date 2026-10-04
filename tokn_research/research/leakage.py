"""Sensitivity and future-poisoning controls, not proof of strategy validity."""

from dataclasses import dataclass, field

from ..contracts import text
from ..simulation.replay import InvalidRun, ReplayTrace


@dataclass(frozen=True)
class ShiftEvidence:
    original: tuple[str, ...]
    shifted: tuple[str, ...]
    changed_indices: tuple[int, ...]
    evidence_kind: str = field(default='synthetic', init=False)
    establishes_no_leakage: bool = field(default=False, init=False)


def check_forward_shift(trace, diagnostic):
    """Intentionally replace features with the next bar for a diagnostic only.

    Shifted values never enter normal replay and cannot yield an order or P&L.
    The last frame is excluded from both paths, preserving equal denominators.
    A feature-independent negative control is expected to fail this gate.
    """
    if not isinstance(trace, ReplayTrace) or len(trace.frames) < 2:
        raise InvalidRun('SHIFT_REQUIRES_TWO_OR_MORE_FRAMES')
    for left, right in zip(trace.frames, trace.frames[1:]):
        if right.anchor_open != left.anchor_close:
            raise InvalidRun('SHIFT_REQUIRES_ADJACENT_BARS')
    # Evaluate identical vectors consistently, including after intervening
    # inputs and in a different order. Consecutive paired calls alone let a
    # callback that increments its output every two calls fake sensitivity.
    # Finite checks still cannot prove purity of arbitrary Python callbacks.
    outputs = {}
    for frame in trace.frames:
        if frame.values in outputs:
            continue
        try:
            outputs[frame.values] = text(diagnostic(frame.values))
        except Exception as exc:
            raise InvalidRun('SHIFT_DIAGNOSTIC_FAILED') from exc
    vectors = tuple(outputs)
    for order in (tuple(reversed(vectors)), vectors):
        for vector in order:
            try:
                repeated = text(diagnostic(vector))
            except Exception as exc:
                raise InvalidRun('SHIFT_DIAGNOSTIC_FAILED') from exc
            if outputs[vector] != repeated:
                raise InvalidRun('SHIFT_DIAGNOSTIC_NONDETERMINISTIC')
    original = tuple(outputs[frame.values] for frame in trace.frames[:-1])
    shifted = tuple(outputs[frame.values] for frame in trace.frames[1:])
    changed = tuple(i for i, (before, after) in enumerate(zip(original, shifted)) if before != after)
    if not changed:
        raise InvalidRun('SHIFT_NO_EFFECT')
    return ShiftEvidence(original, shifted, changed)


def check_prefix_invariance(prefix, extended):
    if (not isinstance(prefix, ReplayTrace) or not isinstance(extended, ReplayTrace)
            or prefix.feature_id != extended.feature_id or prefix.series != extended.series
            or not prefix.frames or len(prefix.frames) > len(extended.frames)):
        raise InvalidRun('INCOMPARABLE_TRACE')
    if prefix.frames != extended.frames[:len(prefix.frames)]:
        raise InvalidRun('PREFIX_CHANGED')
    return True
