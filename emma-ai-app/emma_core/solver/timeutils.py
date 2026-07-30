"""Minute-based, cross-midnight-aware time helpers - no DB or ortools deps, so
the model builder and loading service share one definition of on-duty/conflict.
"""
from __future__ import annotations


def to_minutes(hhmm: str | None) -> int | None:
    """'HH:MM[:SS]' -> minutes from midnight; None passes through."""
    if not hhmm:
        return None
    parts = hhmm.split(":")
    return int(parts[0]) * 60 + int(parts[1])


def absolute_interval(day_index: int, start_min: int, end_min: int,
                      cross_midnight: bool) -> tuple[int, int]:
    """Lift a shift to an absolute ``[start, end)`` in minutes from period start
    so shifts on different days compare directly. A cross-midnight shift (or one
    whose end is not after its start) ends the next day."""
    base = day_index * 1440
    end = end_min + (1440 if (cross_midnight or end_min <= start_min) else 0)
    return base + start_min, base + end


def intervals_conflict(a: tuple[int, int], b: tuple[int, int], min_rest_min: int) -> bool:
    """True if two absolute intervals overlap or their rest gap is under
    ``min_rest_min`` - hard #1 (overlap) and #5 (rest) in one predicate."""
    (a_start, a_end), (b_start, b_end) = a, b
    if a_start < b_end and b_start < a_end:      # overlap
        return True
    gap = (b_start - a_end) if b_start >= a_end else (a_start - b_end)
    return gap < min_rest_min


def _spans(start: int, end: int, cross: bool) -> list[tuple[int, int]]:
    """Split a (possibly midnight-wrapping) window into same-day sub-intervals."""
    if cross or end <= start:
        spans = [(start, 1440)]
        if end > 0:
            spans.append((0, end))
        return spans
    return [(start, end)]


def window_overlap(slot_start: int, slot_end: int, slot_cross: bool,
                   win_start: int, win_end: int) -> bool:
    """Does a shift overlap a ratio window? Either side may wrap midnight, so
    both are split into same-day sub-intervals before comparing."""
    win_cross = win_end <= win_start
    for a, b in _spans(slot_start, slot_end, slot_cross):
        for c, d in _spans(win_start, win_end, win_cross):
            if a < d and c < b:
                return True
    return False
