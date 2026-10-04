"""Explicit replay time; never consult the wall clock."""

from ..contracts import ContractError, utc


class ReplayClock:
    def __init__(self, initial_time):
        self._now = utc(initial_time)

    @property
    def now(self):
        return self._now

    def advance(self, value):
        value = utc(value)
        if value < self._now:
            raise ContractError('CLOCK_REWIND')
        self._now = value

    def checkpoint(self):
        return self._now

    @classmethod
    def restore(cls, checkpoint):
        return cls(checkpoint)
